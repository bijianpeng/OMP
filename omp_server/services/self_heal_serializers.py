import logging

from rest_framework import serializers
from rest_framework.serializers import ModelSerializer, Serializer
from db_models.models import SelfHealingSetting, SelfHealingHistory
# from rest_framework_bulk import BulkSerializerMixin, BulkListSerializer
from rest_framework.exceptions import ValidationError
from utils.middleware_handler import get_request_env

# 配置日志记录器
logger = logging.getLogger("server")


class SelfHealingSettingSerializer(ModelSerializer):
    """
    自愈策略设置序列化器
    用于处理自愈策略的创建、更新和序列化操作
    """
    # env 只读：归属环境由视图 perform_create/perform_update 以请求
    # 环境上下文钉死，客户端传入值一律忽略（env 唯一约束下也不再触发
    # DRF 自动 UniqueValidator 用客户端值误判——多环境架构 Task 7b）
    env = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = SelfHealingSetting  # 关联的模型类
        fields = "__all__"  # 序列化所有字段
        # list_serializer_class = BulkListSerializer  # 注释掉批量序列化器

    def validate(self, attrs):
        """
        验证方法，用于确保自愈实例不重复且遵循业务规则。
        查重范围限定当前请求环境（每环境独立一份自愈设置，多环境架构
        Task 7b），更新时排除自身行避免自撞。

        Args:
            attrs: 待验证的属性字典

        Returns:
            验证通过的属性字典

        Raises:
            ValidationError: 当验证失败时抛出异常
        """
        env = get_request_env(self.context.get("request"))
        # 每环境至多一行设置（模型层 env 唯一约束）：同环境重复创建
        # 在校验层显式拒绝，避免落库时才触发数据库约束
        if self.instance is None and SelfHealingSetting.objects.filter(
                env=env).exists():
            raise ValidationError(f"当前环境已存在自愈设置，不可重复创建")
        # 获取本环境其它设置行已配置的修复实例列表（排除自身）
        queryset = SelfHealingSetting.objects.filter(env=env)
        if self.instance is not None:
            queryset = queryset.exclude(id=self.instance.id)
        repair_ls = queryset.values_list("repair_instance", flat=True)
        repairs = []
        for _ in repair_ls:
            repairs.extend(_)

        # 检查是否有重复的服务
        repeat = set(repairs) & set(attrs["repair_instance"])
        if repeat:
            raise ValidationError(f"服务不可重复{repeat}")

        # 检查是否已存在"all"服务（本环境内），或本次提交 all 与具体服务混用
        if "all" in repairs or ("all" in attrs["repair_instance"]
                                and len(attrs["repair_instance"]) > 1):
            raise ValidationError(f"all服务不可再次添加其他服务")
        return attrs


class ListSelfHealingHistorySerializer(ModelSerializer):
    """
    自愈历史记录列表序列化器
    用于序列化自愈历史记录的查询结果
    """
    class Meta:
        model = SelfHealingHistory  # 关联的模型类
        fields = "__all__"  # 序列化所有字段


class UpdateSelfHealingHistorySerializer(Serializer):
    """自愈历史记录批量更新"""
    ids = serializers.ListField(help_text="自愈历史记录ID列表", required=True, error_messages={"required": "必须包含ID列表字段"})
    is_read = serializers.IntegerField(help_text="是否已读", required=True, error_messages={"required": "必须包含是否已读字段"})

    def create(self, validated_data):
        """
        创建方法，实际执行批量更新操作（仅当前环境的记录，
        跨环境 id 不产生效果——多环境架构 Task 7b）

        Args:
            validated_data: 验证后的数据

        Returns:
            更新后的数据
        """
        # 批量更新指定ID的记录的已读状态（限当前环境）
        SelfHealingHistory.objects.filter(
            id__in=validated_data.get("ids"),
            env=get_request_env(self.context.get("request"))
        ).update(is_read=validated_data.get("is_read"))
        return validated_data
