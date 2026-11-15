import logging
import json

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from rest_framework.viewsets import GenericViewSet
from rest_framework.response import Response
from rest_framework.mixins import CreateModelMixin, ListModelMixin, DestroyModelMixin, UpdateModelMixin
from services.self_heal_serializers import SelfHealingSettingSerializer, ListSelfHealingHistorySerializer, \
    UpdateSelfHealingHistorySerializer
from services.self_heal_filter import SelfHealingTimeFilter, SelfHealingHistoryFilter
from db_models.models import SelfHealingSetting, SelfHealingHistory
from utils.common.paginations import PageNumberPager
from utils.middleware_handler import get_request_env
from services.self_healing import get_enable_health
# from rest_framework_bulk import BulkUpdateAPIView

# 配置日志记录器
logger = logging.getLogger("server")


class SelfHealingSettingView(GenericViewSet, ListModelMixin, CreateModelMixin, DestroyModelMixin, UpdateModelMixin):
    """
    自愈策略视图类
    提供自愈策略的CRUD操作接口
    
    继承:
        GenericViewSet: 提供通用视图集功能
        ListModelMixin: 提供列表查询功能
        CreateModelMixin: 提供创建功能
        DestroyModelMixin: 提供删除功能
        UpdateModelMixin: 提供更新功能
    """
    queryset = SelfHealingSetting.objects.all()  # 查询集
    serializer_class = SelfHealingSettingSerializer  # 序列化器类

    # 操作信息描述
    get_description = "自愈策略"
    post_description = "自愈策略"

    def get_queryset(self):
        """ 自愈策略设置行按当前环境上下文过滤（per-env 配置，读写同源） """
        return SelfHealingSetting.objects.filter(
            env=get_request_env(self.request))

    def list(self, request, *args, **kwargs):
        """
        重写列表查询方法
        支持查询可用于自愈的服务列表

        Args:
            request: HTTP请求对象

        Returns:
            Response: 包含查询结果的响应对象
        """
        # 检查是否需要查询可用服务列表
        query_field = request.query_params.get("instance", False)
        if query_field:
            # 获取已配置的修复实例列表
            repair_ls = self.get_queryset().values_list("repair_instance", flat=True)
            repairs = []
            for _ in repair_ls:
                repairs.extend(_)

            # 根据是否包含"all"服务返回不同的结果
            if "all" in repairs:
                data = {
                    "all": False,
                    "service_name": []
                }
            else:
                data = {
                    "all": False if repairs else True,
                    "service_name": get_enable_health(repairs)
                }
            return Response(data)
        else:
            # 当前环境无设置行时按当前环境 get_or_create 默认行，
            # 保证每个环境读到独立的策略配置；repair_instance 显式传
            # list（模型 default=dict 与前端/序列化器的 list 语义不一致）
            SelfHealingSetting.objects.get_or_create(
                env=get_request_env(request),
                defaults={"repair_instance": []})
            # 返回默认的列表查询结果
            return super(SelfHealingSettingView, self).list(request, *args, **kwargs)

    def perform_create(self, serializer):
        """ 自愈策略行强制继承请求环境（不接受客户端 env 值） """
        serializer.save(env=get_request_env(self.request))

    def perform_update(self, serializer):
        """ 更新时钉住当前环境，防止把设置行迁移到其他环境 """
        serializer.save(env=get_request_env(self.request))


class ListSelfHealingHistoryView(GenericViewSet, ListModelMixin):
    """
    自愈历史记录列表视图类
    提供自愈历史记录的查询功能
    
    继承:
        GenericViewSet: 提供通用视图集功能
        ListModelMixin: 提供列表查询功能
    """
    # 配置查询集，按告警时间和结束时间倒序排序
    queryset = SelfHealingHistory.objects.all().order_by("-alert_time", "-end_time")
    serializer_class = ListSelfHealingHistorySerializer  # 序列化器类
    pagination_class = PageNumberPager  # 分页器类

    def get_queryset(self):
        """ 自愈历史记录按当前环境上下文过滤 """
        return SelfHealingHistory.objects.filter(
            env=get_request_env(self.request)
        ).order_by("-alert_time", "-end_time")
    
    # 过滤器配置
    filter_backends = (
        DjangoFilterBackend,  # Django过滤器后端
        OrderingFilter,  # 排序过滤器
        SelfHealingTimeFilter,  # 自定义时间过滤器
    )
    filter_class = SelfHealingHistoryFilter  # 过滤器类
    
    # 可排序字段
    ordering_fields = ("host_ip", "instance_name", "state", "alert_time", "end_time")


class UpdateSelfHealingHistoryView(CreateModelMixin, GenericViewSet):
    """
    更新自愈历史记录视图类
    提供自愈历史记录的更新功能
    
    继承:
        CreateModelMixin: 提供创建功能（这里用于实现更新操作）
        GenericViewSet: 提供通用视图集功能
    """
    serializer_class = UpdateSelfHealingHistorySerializer  # 序列化器类
    queryset = SelfHealingHistory.objects.all().order_by("id")  # 查询集
    post_description = "更新自愈历史记录（已读/未读）"  # 操作描述
