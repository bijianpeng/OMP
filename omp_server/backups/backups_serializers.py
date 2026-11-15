# !/usr/bin/python3
# 指定使用 Python 3 解释器
# -*-coding:utf-8-*-
# 指定文件编码格式为 UTF-8
import logging
import os
# 从 Django REST framework 导入模型序列化器类
from rest_framework.serializers import ModelSerializer
# 从 Django REST framework 导入序列化器模块
from rest_framework import serializers
# 从 Django REST framework 导入验证错误异常类
from rest_framework.exceptions import ValidationError
# 从自定义工具模块导入正则验证器
from utils.common.validators import ReValidator
# 从数据库模型模块导入备份历史、备份设置和备份自定义参数模型
from db_models.models import BackupHistory, BackupSetting, BackupCustom
from utils.middleware_handler import get_request_env

# 获取名为 "server" 的日志记录器
logger = logging.getLogger("server")


class BackupHistoryIdsSerializer(ModelSerializer):
    """
    备份历史记录 ID 序列化器，用于验证和处理主机 ID 列表。
    """
    ids = serializers.ListField(
        child=serializers.IntegerField(),  # 列表元素为整数类型
        help_text="主机id列表",  # 字段帮助文本
        required=True,  # 该字段为必填项
        write_only=True,  # 该字段仅用于写入操作
        source="id",  # 映射到模型的 id 字段
        error_messages={"required": "必须包含[ids]字段"}  # 自定义错误信息
    )

    def validate(self, attrs):
        """
        验证传入的主机 ID 列表，确保所有 ID 都存在于备份历史记录中
        （仅限当前请求环境，跨环境 id 视为不存在——多环境架构 Task 7b）。

        :param attrs: 包含验证数据的字典
        :return: 验证通过后的数据
        """
        # 过滤出存在于备份历史记录中的 ID 对应的对象（限当前环境）
        backup_obj = BackupHistory.objects.filter(
            id__in=attrs["id"],
            env=get_request_env(self.context.get("request")))
        if len(backup_obj) != len(attrs["id"]):
            # 若存在不存在的 ID，抛出验证错误
            raise ValidationError(f"id不存在")
        attrs["id"] = backup_obj  # 将验证通过的对象赋值给 id 字段
        return attrs

    class Meta:
        model = BackupHistory  # 指定关联的模型为 BackupHistory
        fields = ("ids",)  # 指定序列化的字段为 ids


class BackupHistorySerializer(ModelSerializer):
    """
    备份历史记录序列化器，用于序列化备份历史记录的所有字段。
    """
    class Meta:
        model = BackupHistory  # 指定关联的模型为 BackupHistory
        fields = "__all__"  # 序列化模型的所有字段
        write_only_fields = ("id",)  # 仅用于写入操作的字段为 id


class BackupCustomSerializer(ModelSerializer):
    """
    备份自定义参数序列化器，用于验证和处理备份自定义参数。
    """
    notes = serializers.CharField(
        help_text="备注信息",  # 字段帮助文本
        required=False, default="",  # 该字段非必填，默认值为空字符串
        allow_null=True, allow_blank=True  # 允许值为 None 或空字符串
    )

    def validate(self, attrs):
        """
        验证传入的自定义参数，确保 field_k 和 field_v 的组合不重复。

        :param attrs: 包含验证数据的字典
        :return: 验证通过后的数据
        """
        # 统计 field_k 和 field_v 组合相同的自定义参数数量
        backup_obj = BackupCustom.objects.filter(
            field_k=attrs["field_k"], field_v=attrs["field_v"]).count()
        if backup_obj != 0:
            # 若组合已存在，抛出验证错误
            raise ValidationError(f"自定义参数不可重复")
        return attrs

    class Meta:
        model = BackupCustom  # 指定关联的模型为 BackupCustom
        fields = "__all__"  # 序列化模型的所有字段


class BackupCustomRepeatSerializer(ModelSerializer):
    """
    备份自定义参数重复检查序列化器，用于获取关联备份设置的实例名称。
    """
    name = serializers.SerializerMethodField()  # 自定义序列化字段

    def get_name(self, obj):
        """
        获取关联备份设置的所有实例名称，并去重后用逗号连接。

        :param obj: BackupCustom 模型实例
        :return: 去重后的实例名称字符串
        """
        instance_ls = []
        # 遍历关联的所有备份设置实例
        for instance in obj.backupsetting_set.all():
            instance_ls.extend(instance.backup_instances)
        return ",".join(set(instance_ls))  # 去重后用逗号连接

    class Meta:
        model = BackupCustom  # 指定关联的模型为 BackupCustom
        fields = ("name",)  # 指定序列化的字段为 name


class BackupSettingSerializer(ModelSerializer):
    """
    备份设置序列化器，用于验证和处理备份设置相关字段。
    """
    backup_instances = serializers.ListField(
        help_text="备份服务实例名称",  # 字段帮助文本
        required=True,  # 该字段为必填项
        error_messages={"required": "备份服务需必填"}  # 自定义错误信息
    )
    crontab_detail = serializers.DictField(
        help_text="定时任务详情",  # 字段帮助文本
        required=True,  # 该字段为必填项
        error_messages={"required": "请填写备份策略"}  # 自定义错误信息
    )
    retain_day = serializers.IntegerField(help_text="文件保存天数", default=1)  # 文件保存天数，默认值为 1
    retain_path = serializers.CharField(
        help_text="文件保存路径",  # 字段帮助文本
        default="/data/omp/data/backup/",  # 默认保存路径
        min_length=2,  # 最小长度为 2
        error_messages={
            "required": "必须包含[retain_path]字段",
            "min_length": "用户名长度需小于{min_length}"
        },  # 自定义错误信息
        validators=[
            ReValidator(regex=r"^/[-_/a-zA-Z0-9]+$"),  # 使用正则验证器验证路径格式
        ]
    )
    backup_custom = BackupCustomSerializer(many=True, required=False)  # 关联备份自定义参数序列化器

    def validate_retain_path(self, retain_path):  # NOQA
        """
        验证备份文件保存路径是否可读写，若不存在则尝试创建。

        :param retain_path: 备份文件保存路径
        :return: 验证通过的路径
        """
        try:
            folder = os.path.exists(retain_path)  # 检查路径是否存在
            if not folder:
                os.makedirs(retain_path)  # 若不存在则创建路径
            file_path = os.path.join(retain_path, 'test.txt')  # 拼接测试文件路径
            create_file = open(file_path, "w")  # 尝试创建测试文件
            create_file.close()  # 关闭测试文件
        except Exception as e:
            # 记录校验失败日志并抛出验证错误
            logger.info(f"校验文件夹权限失败：{str(e)}")
            raise ValidationError(f"请确定程序对备份文件保存文件夹{retain_path}有读写权限！")
        return retain_path

    def validate_crontab_detail(self, crontab_detail):  # NOQA
        """
        验证定时任务详情，目前暂时不进行校验，但有校验的必要。

        :param crontab_detail: 定时任务详情
        :return: 传入的定时任务详情
        """
        #
        # ToDo暂时不校验但有校验的必要
        return crontab_detail

    class Meta:
        model = BackupSetting  # 指定关联的模型为 BackupSetting
        fields = (
            "id", "backup_instances", "crontab_detail", "retain_day",
            "retain_path", "backup_custom", "is_on"
        )  # 指定序列化的字段