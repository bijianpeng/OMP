# -*- coding: utf-8 -*-
# Project: views_for_install
# Author: omp
# Create time: 2021-10-21 17:59
# IDE: PyCharm
# Version: 1.0
# Introduction: 此模块包含与应用安装相关的视图类，用于处理组件、产品安装入口，执行安装以及获取安装记录等操作

# 从 rest_framework 导入状态码、响应类、视图集基类和模型混合类
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import (
    ListModelMixin, CreateModelMixin
)
# 从 django_filters 的 rest_framework 后端导入过滤器后端类
from django_filters.rest_framework.backends import DjangoFilterBackend

# 从数据库模型模块导入所需的模型类
from db_models.models import (
    ApplicationHub, ProductHub,
    MainInstallHistory, Service
)

# 从 app_store 应用的序列化器模块导入所需的序列化器类
from app_store.app_store_serializers import (
    ComponentEntranceSerializer,
    ProductEntranceSerializer,
    ExecuteInstallSerializer,
    InstallHistorySerializer,
    ServiceInstallHistorySerializer
)

# 从 app_store 应用的过滤器模块导入所需的过滤器类
from app_store.app_store_filters import (
    ComponentEntranceFilter,
    ProductEntranceFilter,
    InstallHistoryFilter,
    ServiceInstallHistoryFilter
)
# 从中间件模块导入请求环境上下文获取函数
from utils.middleware_handler import get_request_env


class ComponentEntranceView(GenericViewSet, ListModelMixin):
    """
        list:
        组件安装入口，用于获取可安装组件的数据列表
    """
    # 查询已发布的组件应用，并按创建时间倒序排列
    queryset = ApplicationHub.objects.filter(
        is_release=True,
        app_type=ApplicationHub.APP_TYPE_COMPONENT
    ).order_by("-created")
    # 指定使用的序列化器类
    serializer_class = ComponentEntranceSerializer
    # 指定使用的过滤器后端
    filter_backends = (DjangoFilterBackend, )
    # 指定使用的过滤器类
    filter_class = ComponentEntranceFilter
    # 接口描述信息
    get_description = "获取组件安装数据入口"

    def list(self, request, *args, **kwargs):
        """
        处理获取组件列表的请求，对返回数据进行后处理

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含处理后组件数据的响应
        """
        # 对查询集进行过滤
        queryset = self.filter_queryset(self.get_queryset())
        # 使用序列化器对查询集进行序列化
        serializer = self.get_serializer(queryset, many=True)
        # 对返回数据重新进行处理，对process_continue字段进行提取
        for el in serializer.data:
            if len(el.get("app_dependence", [])) != 0:
                for item in el.get("app_dependence", []):
                    if "process_continue" in item and \
                            not item["process_continue"] and \
                            el.get("process_continue"):
                        # 若依赖项的 process_continue 为 False，则更新当前组件的对应字段
                        el["process_continue"] = False
                        el["process_message"] = item.get("process_message")
                        break
        return Response(serializer.data)


class ProductEntranceView(GenericViewSet, ListModelMixin):
    """
        list:
        产品、应用安装入口，用于获取可安装产品和应用的数据列表
    """
    # 查询已发布的产品，并按创建时间倒序排列
    queryset = ProductHub.objects.filter(
        is_release=True,
    ).order_by("-created")
    # 指定使用的序列化器类
    serializer_class = ProductEntranceSerializer
    # 指定使用的过滤器后端
    filter_backends = (DjangoFilterBackend, )
    # 指定使用的过滤器类
    filter_class = ProductEntranceFilter
    # 接口描述信息
    get_description = "获取产品应用安装数据入口"


class ExecuteInstallView(GenericViewSet, CreateModelMixin):
    """
        create:
        执行安装入口接口，用于处理执行安装的请求
    """
    # 指定使用的序列化器类
    serializer_class = ExecuteInstallSerializer
    # 接口描述信息
    post_description = "执行安装入口接口"

    def create(self, request, *args, **kwargs):
        """
            post:
            执行安装按钮接口，验证请求数据并返回成功响应

            :param request: 请求对象，包含安装相关数据
            :param args: 可变位置参数
            :param kwargs: 可变关键字参数
            :return: 包含验证后数据的成功响应
        """
        # 使用序列化器对请求数据进行验证
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # 获取成功响应的头部信息
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )


class InstallHistoryView(GenericViewSet, ListModelMixin):
    """
        list:
        获取安装记录，用于获取所有安装历史的数据列表
    """
    # 查询所有安装历史记录，并按创建时间倒序排列
    queryset = MainInstallHistory.objects.all().order_by("-created")
    # 指定使用的序列化器类
    serializer_class = InstallHistorySerializer
    # 指定使用的过滤器后端
    filter_backends = (DjangoFilterBackend,)
    # 指定使用的过滤器类
    filter_class = InstallHistoryFilter
    # 接口描述信息
    get_description = "获取安装历史数据入口"

    def get_queryset(self):
        # 安装历史列表按当前环境上下文过滤（多环境架构 Task 14）
        return super(InstallHistoryView, self).get_queryset().filter(
            env=get_request_env(self.request))


class ServiceInstallHistoryDetailView(GenericViewSet, ListModelMixin):
    """
        list:
        获取安装记录，用于获取单个服务的安装记录数据列表
    """
    # 查询所有服务记录，并按创建时间倒序排列
    queryset = Service.objects.all().order_by("-created")
    # 指定使用的序列化器类
    serializer_class = ServiceInstallHistorySerializer
    # 指定使用的过滤器后端
    filter_backends = (DjangoFilterBackend,)
    # 指定使用的过滤器类
    filter_class = ServiceInstallHistoryFilter
    # 接口描述信息
    get_description = "获取单个服务安装记录"

    def get_queryset(self):
        # 服务安装记录列表按当前环境上下文过滤（多环境架构 Task 14）
        return super(ServiceInstallHistoryDetailView, self).get_queryset(
        ).filter(env=get_request_env(self.request))
