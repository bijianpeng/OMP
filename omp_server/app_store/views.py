"""
应用商店相关视图
"""
# 导入操作系统相关功能模块
import os
# 导入 UUID 生成模块
import uuid
# 导入 JSON 数据处理模块
import json
# 导入时间处理模块
import time
# 导入字符串处理模块
import string
# 导入随机数生成模块
import random
# 导入日志记录模块
import logging

# 从 rest_framework 视图集模块导入通用视图集基类
from rest_framework.viewsets import GenericViewSet
# 从 rest_framework 混合类模块导入列表模型混合类和创建模型混合类
from rest_framework.mixins import (
    ListModelMixin, CreateModelMixin
)
# 从 rest_framework 导入响应类
from rest_framework.response import Response
# 从 rest_framework 导入验证异常类
from rest_framework.exceptions import ValidationError
# 从 django 数据库模块导入事务处理模块
from django.db import transaction
# 从 django_filters 的 rest_framework 后端导入过滤器后端类
from django_filters.rest_framework.backends import DjangoFilterBackend

# 从数据库模型模块导入所需的模型类
from db_models.models import (
    Labels, ApplicationHub, Product, ProductHub,
    Host, Service, ServiceConnectInfo,
    DeploymentPlan, ClusterInfo,
    MainInstallHistory, DetailInstallHistory,
    PreInstallHistory, PostInstallHistory,
    UploadPackageHistory, ExecutionRecord)
# 从通用工具模块导入分页器类
from utils.common.paginations import PageNumberPager
# 从 app_store 应用的过滤器模块导入所需的过滤器类
from app_store.app_store_filters import (
    LabelFilter, ComponentFilter, ServiceFilter, UploadPackageHistoryFilter,
    PublishPackageHistoryFilter
)
# 从 app_store 应用的序列化器模块导入所需的序列化器类
from app_store.app_store_serializers import (
    ComponentListSerializer, ServiceListSerializer,
    UploadPackageSerializer, RemovePackageSerializer,
    UploadPackageHistorySerializer, ExecuteLocalPackageScanSerializer,
    PublishPackageHistorySerializer, DeploymentPlanValidateSerializer,
    DeploymentImportSerializer, DeploymentPlanListSerializer,
    ExecutionRecordSerializer, DeleteComponentSerializer,
    DeleteProDuctSerializer, ProductCompositionSerializer
)
# 从备份工具模块导入命令执行函数
from backups.backups_utils import cmd
# 从项目设置模块导入项目根目录
from omp_server.settings import PROJECT_DIR

# 再次从 app_store 应用的序列化器模块导入详情序列化器类
from app_store.app_store_serializers import (
    ProductDetailSerializer, ApplicationDetailSerializer
)
# 从 app_store 应用导入临时执行后台任务模块
from app_store import tmp_exec_back_task

# 从通用异常模块导入操作异常类
from utils.common.exceptions import OperateError
# 从中间件模块导入请求环境上下文获取函数
from utils.middleware_handler import get_request_env
# 从通用视图模块导入基础下载模板视图类
from utils.common.views import BaseDownLoadTemplateView
# 从 app_store 应用的任务模块导入发布入口任务
from app_store.tasks import publish_entry
# 从 rest_framework 导入排序和搜索过滤器类
from rest_framework.filters import OrderingFilter, SearchFilter
# 从配置解析模块导入基础顺序和亲和力字段配置
from utils.parse_config import (
    BASIC_ORDER, AFFINITY_FIELD
)
# 从 app_store 应用的新安装工具模块导入数据 JSON 类
from app_store.new_install_utils import DataJson
# 从 app_store 应用的新安装工具模块导入服务参数端口工具类
from app_store.new_install_utils import ServiceArgsPortUtils

# 配置日志记录器，使用名为 "server" 的日志记录器
logger = logging.getLogger("server")


class AppStoreListView(GenericViewSet, ListModelMixin):
    """ 应用商店 list 视图类 """

    def list(self, request, *args, **kwargs):
        """
        处理获取列表数据的请求，对查询集进行去重处理

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含去重后数据的分页响应
        """
        # 对查询集进行过滤
        queryset = self.filter_queryset(self.get_queryset())
        # 从 kwargs 中获取名称字段
        name_field = kwargs.get("name_field")
        # 初始化结果列表和名称集合，用于去重
        result_ls, name_set = [], set()
        # 遍历查询集
        for obj in queryset:
            # 获取对象的名称字段值
            name = getattr(obj, name_field)
            # 若名称不在集合中，则添加到集合和结果列表
            if name not in name_set:
                name_set.add(name)
                result_ls.append(obj)

        # 对去重后的结果进行分页并序列化
        serializer = self.get_serializer(
            self.paginate_queryset(result_ls), many=True)

        # 返回分页后的响应数据
        return self.get_paginated_response(serializer.data)


class LabelListView(GenericViewSet, ListModelMixin):
    """
        list:
        查询所有标签列表
    """
    # 查询所有标签对象
    queryset = Labels.objects.all()
    # 指定使用的过滤器后端
    filter_backends = (DjangoFilterBackend,)
    # 指定使用的过滤器类
    filter_class = LabelFilter
    # 操作信息描述
    get_description = "查询所有标签列表"

    def list(self, request, *args, **kwargs):
        """
        处理获取标签列表的请求，根据标签类型过滤数据

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含过滤后标签名称列表的响应
        """
        # 获取查询集
        query_set = self.get_queryset()
        # 从请求查询参数中获取标签类型，默认值为 -1
        label_type = request.query_params.get("label_type", -1)
        # 若标签类型为组件类型
        if int(label_type) == Labels.LABEL_TYPE_COMPONENT:
            # 过滤出组件类型的标签
            query_set = Labels.objects.filter(
                applicationhub__app_type=ApplicationHub.APP_TYPE_COMPONENT)
        # 若标签类型为应用类型
        if int(label_type) == Labels.LABEL_TYPE_APPLICATION:
            # 过滤出应用类型的标签
            query_set = Labels.objects.exclude(
                producthub__isnull=True)
        # 对查询集进行排序、去重并提取标签名称
        query_set = query_set.order_by(
            "id").values_list("label_name", flat=True).distinct()
        # 对查询集进行过滤
        queryset = self.filter_queryset(query_set)
        # 返回包含标签名称列表的响应
        return Response(list(queryset))


class ComponentListView(AppStoreListView):
    """
        list:
        查询所有基础组件列表
    """
    # 查询已发布的基础组件对象，并按创建时间倒序排列
    queryset = ApplicationHub.objects.filter(
        app_type=ApplicationHub.APP_TYPE_COMPONENT,
        is_release=True,
    ).order_by("-created")
    # 指定使用的序列化器类
    serializer_class = ComponentListSerializer
    # 指定使用的分页器类
    pagination_class = PageNumberPager
    # 指定使用的过滤器后端
    filter_backends = (DjangoFilterBackend,)
    # 指定使用的过滤器类
    filter_class = ComponentFilter
    # 操作信息描述
    get_description = "查询所有基础组件列表"

    def list(self, request, *args, **kwargs):
        """
        处理获取基础组件列表的请求，调用父类方法进行去重处理

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含去重后基础组件数据的分页响应
        """
        # 调用父类的 list 方法，传递名称字段参数
        return super(ComponentListView, self).list(
            request, name_field="app_name", *args, **kwargs)


class ServiceListView(AppStoreListView):
    """
        list:
        查询所有应用服务列表
    """
    # 查询已发布的产品对象，并按创建时间倒序排列
    queryset = ProductHub.objects.filter(
        is_release=True).order_by("-created")
    # 指定使用的序列化器类
    serializer_class = ServiceListSerializer
    # 指定使用的分页器类
    pagination_class = PageNumberPager
    # 指定使用的过滤器后端
    filter_backends = (DjangoFilterBackend,)
    # 指定使用的过滤器类
    filter_class = ServiceFilter
    # 操作信息描述
    get_description = "查询所有应用服务列表"

    def list(self, request, *args, **kwargs):
        """
        处理获取应用服务列表的请求，调用父类方法进行去重处理

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含去重后应用服务数据的分页响应
        """
        # 调用父类的 list 方法，传递名称字段参数
        return super(ServiceListView, self).list(
            request, name_field="pro_name", *args, **kwargs)


class UploadPackageView(GenericViewSet, CreateModelMixin):
    """
        create:
        上传安装包
    """
    # 查询所有上传包历史记录对象
    queryset = UploadPackageHistory.objects.all()
    # 指定使用的序列化器类
    serializer_class = UploadPackageSerializer
    # 操作信息描述
    post_description = "上传安装包"


class RemovePackageView(GenericViewSet, CreateModelMixin):
    """
        post:
        批量移除安装包
    """
    # 查询所有上传包历史记录对象
    queryset = UploadPackageHistory.objects.all()
    # 指定使用的序列化器类
    serializer_class = RemovePackageSerializer
    # 操作信息描述
    post_description = "移除安装包"


class ComponentDetailView(GenericViewSet, ListModelMixin):
    """
    查询组件详情
    """
    # 指定使用的序列化器类
    serializer_class = ApplicationDetailSerializer

    # 操作信息描述
    get_description = "查询组件详情"

    def list(self, request, *args, **kwargs):
        """
        处理获取组件详情的请求，根据组件名称查询并返回详情数据

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含组件详情的响应
        """
        # 从请求参数中获取组件名称
        arg_app_name = request.GET.get('app_name')

        # 根据组件名称查询组件对象，并按创建时间排序
        queryset = ApplicationHub.objects.filter(
            app_name=arg_app_name).order_by("created")
        # 对查询集进行序列化
        serializer = self.get_serializer(queryset, many=True)
        # 构建响应结果字典
        result = dict()
        result.update(
            {
                "app_name": arg_app_name,
                "versions": list(serializer.data)
            }
        )
        # 返回包含组件详情的响应
        return Response(result)


class ServiceDetailView(GenericViewSet, ListModelMixin):
    """
    查询服务详情
    """
    # 指定使用的序列化器类
    serializer_class = ProductDetailSerializer

    # 操作信息描述
    get_description = "查询服务详情"

    def list(self, request, *args, **kwargs):
        """
        处理获取服务详情的请求，根据服务名称查询并返回详情数据

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含服务详情的响应
        """
        # 从请求参数中获取服务名称
        arg_pro_name = request.GET.get('pro_name')

        # 根据服务名称查询服务对象，并按创建时间排序
        queryset = ProductHub.objects.filter(
            pro_name=arg_pro_name).order_by("created")
        # 对查询集进行序列化
        serializer = self.get_serializer(queryset, many=True)
        # 构建响应结果字典
        result = dict()
        result.update(
            {
                "pro_name": arg_pro_name,
                "versions": list(serializer.data)
            }
        )
        # 返回包含服务详情的响应
        return Response(result)


class ServicePackPageVerificationView(GenericViewSet, ListModelMixin):
    """
    查询服务包页面验证结果列表
    """
    # 查询未删除且没有父包的上传包历史记录对象
    queryset = UploadPackageHistory.objects.filter(
        is_deleted=False, package_parent__isnull=True)
    # 指定使用的序列化器类
    serializer_class = UploadPackageHistorySerializer
    # 指定使用的过滤器后端
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    # 指定使用的过滤器类
    filter_class = UploadPackageHistoryFilter


class PublishViewSet(ListModelMixin, CreateModelMixin, GenericViewSet):
    """
        create:
        发布接口
    """

    # 查询未删除、没有父包且包状态为 3、4、5 的上传包历史记录对象
    queryset = UploadPackageHistory.objects.filter(is_deleted=False,
                                                   package_parent__isnull=True,
                                                   package_status__in=[3, 4, 5])
    # 指定使用的序列化器类
    serializer_class = PublishPackageHistorySerializer
    # 指定使用的过滤器后端
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    # 指定使用的过滤器类
    filter_class = PublishPackageHistoryFilter
    # 操作信息描述
    post_description = "上传应用商店安装包发布"

    def create(self, request, *args, **kwargs):
        """
        处理发布请求，异步调用发布任务

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含发布任务下发状态的响应
        """
        # 获取请求数据
        params = request.data
        # 从请求数据中获取 uuid
        uuid = params.pop('uuid', None)
        # 若未传入 uuid，抛出操作异常
        if not uuid:
            raise OperateError("请传入uuid")
        # 异步调用发布入口任务
        publish_entry.delay(uuid)
        # 返回发布任务下发成功的响应
        return Response({"status": "发布任务下发成功"})


class ExecuteLocalPackageScanView(GenericViewSet, CreateModelMixin):
    """
        post:
        扫描服务端执行按钮
    """
    # 指定使用的序列化器类
    serializer_class = ExecuteLocalPackageScanSerializer
    # 操作信息描述
    post_description = "扫描本地安装包"

    def create(self, request, *args, **kwargs):
        """
            post:
            扫描服务端执行按钮
        """
        # 调用后台验证初始化函数，获取 uuid 和包名列表
        _uuid, _package_name_lst = tmp_exec_back_task.back_end_verified_init(
            operation_user=request.user.username
        )
        # 构建响应数据字典
        ret_data = {
            "uuid": _uuid,
            "package_names": _package_name_lst
        }

        # 返回包含 uuid 和包名列表的响应
        return Response(ret_data)


class LocalPackageScanResultView(GenericViewSet, ListModelMixin):
    """
        list:
        扫描服务端执行结果查询接口
        参数:
            uuid: 操作唯一uuid
            package_names: 安装包名称组成的字符串，英文逗号分隔
    """

    @staticmethod
    def get_res_data(operation_uuid, package_names):
        """
        获取安装包扫描状态

        :param operation_uuid: 唯一操作uuid
        :param package_names: 安装包名称组成的字符串
        :return: 包含扫描状态、消息和包详情的字典
        """
        # 将安装包名称字符串拆分为列表
        package_names_lst = package_names.split(",")
        # 确定当前安装包状态
        if UploadPackageHistory.objects.filter(
                operation_uuid=operation_uuid,
                package_name__in=package_names_lst,
                package_status=1
        ).count() == len(package_names_lst):
            # 当全部安装包的状态为 1 - 校验失败 时，整个流程结束
            stage_status = "check_all_failed"
        elif UploadPackageHistory.objects.filter(
                operation_uuid=operation_uuid,
                package_name__in=package_names_lst,
                package_status__gt=2
        ).exists():
            # 当有安装包进入到分布流程时，整个流程进入到发布流程
            if UploadPackageHistory.objects.filter(
                    operation_uuid=operation_uuid,
                    package_name__in=package_names_lst,
                    package_status=5
            ).exists():
                # 如果有安装包处于发布中状态，那么整个流程处于发布中状态
                stage_status = "publishing"
            else:
                stage_status = "published"
        else:
            # 校验中
            stage_status = "checking"
        # 初始化安装包信息字典
        package_info_dic = {
            el: {
                "status": 2, "message": ""
            } for el in package_names_lst
        }
        # 查询指定 uuid 和包名的上传包历史记录对象
        queryset = UploadPackageHistory.objects.filter(
            operation_uuid=operation_uuid,
            package_name__in=package_names_lst,
        )
        # 发布安装包状态及error信息提取
        for item in queryset:
            # 更新安装包信息字典中的状态和错误信息
            package_info_dic[item.package_name]["status"] = item.package_status
            package_info_dic[item.package_name]["message"] = item.error_msg
        if stage_status == "checking":
            # 计算正在解析的安装包数量
            count = UploadPackageHistory.objects.filter(
                operation_uuid=operation_uuid,
                package_name__in=package_names_lst,
                package_status=UploadPackageHistory.PACKAGE_STATUS_PARSING
            ).count()
            # 构建校验中的提示信息
            message = f"共扫描到 {len(package_names_lst)} 个安装包，" \
                      f"正在校验中..." \
                      f"({len(package_names_lst) - count}/{len(package_names_lst)})"
        elif stage_status == "check_all_failed":
            # 构建全部校验失败的提示信息
            message = f"共计 {len(package_names_lst)} 个安装包校验失败!"
        elif stage_status == "publishing":
            # 计算正在发布的安装包数量
            _count = UploadPackageHistory.objects.filter(
                operation_uuid=operation_uuid,
                package_name__in=package_names_lst,
                package_status__gt=2
            ).count()
            # 构建发布中的提示信息
            message = f"本次共发布 {_count} 个安装包，正在发布中..."
        elif stage_status == "published":
            # 计算发布成功的安装包数量
            _count = UploadPackageHistory.objects.filter(
                operation_uuid=operation_uuid,
                package_name__in=package_names_lst,
                package_status=3
            ).count()
            # 构建发布完成的提示信息
            message = \
                f"本次共发布成功 {_count} 个安装包，" \
                f"发布失败 {len(package_names_lst) - _count} 个安装包!"
        else:
            message = ""
        # 初始化安装包详情列表
        package_detail_lst = list()
        for item in package_names_lst:
            # 将安装包信息添加到详情列表中
            package_detail_lst.append(package_info_dic[item])
        # 构建响应结果字典
        ret_dic = {
            "uuid": operation_uuid,
            "package_names_lst": package_names_lst,
            "package_detail": package_detail_lst,
            "message": message,
            "stage_status": stage_status
        }
        return ret_dic

    @staticmethod
    def check_request_param(operation_uuid, package_names):
        """
        校验参数

        :param operation_uuid: 唯一uuid
        :param package_names: 安装包名称
        :return: 无，若参数不合法则抛出验证异常
        """
        if not operation_uuid:
            # 若未传入 uuid，抛出验证异常
            raise ValidationError({"uuid": "请求参数中必须包含 [uuid] 字段"})
        if not package_names:
            # 若未传入安装包名称，抛出验证异常
            raise ValidationError(
                {"package_names": "请求参数中必须包含 [package_names] 字段"})

    def list(self, request, *args, **kwargs):
        """
        处理获取扫描结果的请求，校验参数并返回结果

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含扫描结果的响应
        """
        # 从请求查询参数中获取 uuid
        operation_uuid = request.query_params.get("uuid", "")
        # 从请求查询参数中获取安装包名称
        package_names = request.query_params.get("package_names", "")
        # 校验请求参数
        self.check_request_param(operation_uuid, package_names)
        # 获取安装包扫描结果数据
        res = self.get_res_data(operation_uuid, package_names)
        # 返回包含扫描结果的响应
        return Response(res)


class ApplicationTemplateView(BaseDownLoadTemplateView):
    """
        list:
        获取应用商店下载模板
    """
    # 操作描述信息
    get_description = "应用商店下载组件模板"

    def list(self, request, *args, **kwargs):
        """
        处理获取应用商店下载模板的请求，调用父类方法

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含应用商店下载模板的响应
        """
        # 调用父类的 list 方法，传递模板文件名参数
        return super(ApplicationTemplateView, self).list(
            request, template_file_name="app_publish_readme.md",
            *args, **kwargs)


class DeploymentOperableView(GenericViewSet, ListModelMixin):
    """
        list:
        部署计划是否可操作
    """
    # 查询非基础环境的服务对象
    queryset = Service.objects.filter(
        service__is_base_env=False)
    # 操作描述信息
    get_description = "查看部署计划"

    def get_queryset(self):
        # 仅统计当前环境已安装的非基础环境服务（多环境架构 Task 14）
        return super(DeploymentOperableView, self).get_queryset().filter(
            env=get_request_env(self.request))

    def list(self, request, *args, **kwargs):
        """
        处理获取部署计划可操作状态的请求

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含部署计划是否可操作的布尔值响应
        """
        # 返回部署计划是否可操作的布尔值响应
        return Response(not self.get_queryset().exists())


class DeploymentTemplateView(BaseDownLoadTemplateView):
    """
          list:
          获取部署计划模板
      """
    # 操作描述信息
    get_description = "获取部署计划模板"

    def list(self, request, *args, **kwargs):
        """
        处理获取部署计划模板的请求，调用父类方法

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含部署计划模板的响应
        """
        # 调用父类的 list 方法，传递模板文件名参数
        return super(DeploymentTemplateView, self).list(
            request, template_file_name="deployment.xlsx",
            *args, **kwargs)


class DeploymentPlanListView(GenericViewSet, ListModelMixin):
    """
        list:
        查看部署计划
    """
    # 查询所有部署计划对象，并按创建时间倒序排列
    queryset = DeploymentPlan.objects.all().order_by("-created")
    # 指定使用的序列化器类
    serializer_class = DeploymentPlanListSerializer
    # 指定使用的分页器类
    pagination_class = PageNumberPager
    # 操作描述信息
    get_description = "查看部署计划"

    def get_queryset(self):
        # 部署方案列表按当前环境上下文过滤（多环境架构 Task 14）
        return super(DeploymentPlanListView, self).get_queryset().filter(
            env=get_request_env(self.request))


class DeploymentPlanValidateView(GenericViewSet, CreateModelMixin):
    """
        create:
        校验部署计划服务数据
    """
    # 指定使用的序列化器类
    serializer_class = DeploymentPlanValidateSerializer
    # 操作描述信息
    post_description = "校验部署计划服务数据"

    def create(self, request, *args, **kwargs):
        """
        处理校验部署计划服务数据的请求

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含验证后数据的响应
        """
        # 使用序列化器对请求数据进行验证
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # 若数据验证失败，记录错误日志并抛出验证异常
            logger.error(f"deployment plan validate failed:{request.data}")
            raise ValidationError("数据格式错误")
        # 返回验证后的数据
        return Response(serializer.validated_data.get("result_dict"))


class DeploymentPlanImportView(GenericViewSet, CreateModelMixin):
    """
        create:
        部署计划导入，服务数据入库
    """
    # 指定使用的序列化器类
    serializer_class = DeploymentImportSerializer
    # 操作描述信息
    post_description = "部署计划导入，服务数据入库"

    @staticmethod
    def _get_app_pro_queryset(service_name_ls):
        """
        获取最新的 app 和 pro 查询集

        :param service_name_ls: 服务名称列表
        :return: 包含最新 app 和 pro 查询集的元组
        """
        # 查询所有 application 信息
        _queryset = ApplicationHub.objects.filter(
            app_name__in=service_name_ls, is_release=True)
        # 所有 application 默认取最新
        new_app_id_list = []
        for app in _queryset:
            # 获取该应用名称下最新版本的应用对象
            new_version = _queryset.filter(
                app_name=app.app_name
            ).order_by("-created").first().app_version
            if new_version == app.app_version:
                new_app_id_list.append(app.id)
        # 过滤出最新版本的应用对象，并关联查询其产品对象
        app_queryset = _queryset.filter(
            id__in=new_app_id_list, is_release=True
        ).select_related("product")

        # 获取 application 对应的 product 信息
        app_now = app_queryset.exclude(product__isnull=True)
        # 获取应用对应的产品 ID 列表
        pro_id_list = app_now.values_list("product_id", flat=True).distinct()
        # 验证 product 的依赖项均已包含
        pro_queryset = ProductHub.objects.filter(id__in=pro_id_list)
        return app_queryset, pro_queryset

    @staticmethod
    def _add_service(service_obj_ls, host_obj, app_obj, env_obj, only_dict,
                     cluster_dict, product_dict, service_set,
                     is_base_env=False, vip=None, role=None):
        """
        添加服务到服务对象列表

        :param service_obj_ls: 服务对象列表
        :param host_obj: 主机对象
        :param app_obj: 应用对象
        :param env_obj: 兜底环境对象（主机无环境时使用，通常为请求环境）
        :param only_dict: 单实例服务字典
        :param cluster_dict: 集群服务字典
        :param product_dict: 产品信息字典
        :param service_set: 服务实例名称集合，用于去重
        :param is_base_env: 是否为基础环境服务，默认为 False
        :param vip: 虚拟 IP 地址，默认为 None
        :param role: 服务角色，默认为 None
        :return: 无
        """
        # 切分 ip 字段，构建服务实例名
        ip_split_ls = host_obj.ip.split(".")
        service_name = app_obj.app_name
        service_instance_name = f"{service_name}-{ip_split_ls[-2]}-{ip_split_ls[-1]}"

        # 当服务实例已经存在，则跳过
        if service_instance_name in service_set:
            return
        service_set.add(service_instance_name)

        # 服务端口
        service_port = json.dumps(ServiceArgsPortUtils().get_app_port(app_obj))
        if not service_port:
            service_port = json.dumps([])

        # 获取服务的基础目录、用户名、密码、密文
        base_dir = "/data"
        username, password, password_enc = "", "", ""
        app_install_args = ServiceArgsPortUtils().get_app_install_args(app_obj)
        for item in app_install_args:
            if item.get("key") == "base_dir":
                base_dir = os.path.join(
                    host_obj.data_folder,
                    item.get("default", "").lstrip("/")
                )
            elif item.get("key") == "username":
                username = item.get("default")
            elif item.get("key") == "password":
                password = item.get("default")
            elif item.get("key") == "password_enc":
                password_enc = item.get("default")
            else:
                pass

        # 拼接服务的控制脚本
        service_controllers = {}
        app_controllers = json.loads(app_obj.app_controllers)
        for k, v in app_controllers.items():
            if v != "":
                service_controllers[k] = f"{base_dir}/{v}"
        if "post_action" in app_obj.extend_fields:
            service_controllers["post_action"] = os.path.join(
                base_dir, app_obj.extend_fields.get("post_action")
            )

        # 创建服务连接信息表
        connection_obj = None
        if any([username, password, password_enc]):
            connection_obj, _ = ServiceConnectInfo.objects.get_or_create(
                service_name=service_name,
                service_username=username,
                service_password=password,
                service_password_enc=password_enc,
                service_username_enc="",
            )

        # 集群信息
        cluster_id = None
        if not is_base_env:
            if service_name in only_dict:
                # 存在于单实例字典中，删除单实例字典中数据，创建集群
                only_dict.pop(service_name)
                upper_key = ''.join(random.choice(
                    string.ascii_uppercase) for _ in range(7))
                cluster_obj = ClusterInfo.objects.create(
                    cluster_service_name=service_name,
                    cluster_name=f"{service_name}-cluster-{upper_key}",
                    service_connect_info=connection_obj,
                )
                # 写入集群字典，记录 id
                cluster_dict[service_name] = (
                    cluster_obj.id, cluster_obj.cluster_name)
            elif service_name in cluster_dict:
                # 存在于集群字典中
                pass
            else:
                # 尚未记录，加入单实例字典
                only_dict[service_name] = service_instance_name

        # 如果产品信息不再字典中，将其添加至字典
        if app_obj.product and \
                app_obj.product.pro_name not in product_dict:
            product_dict[app_obj.product.pro_name] = app_obj.product

        # 添加服务到列表中
        service_obj_ls.append(Service(
            ip=host_obj.ip,
            service_instance_name=service_instance_name,
            service=app_obj,
            service_port=service_port,
            service_controllers=service_controllers,
            service_status=Service.SERVICE_STATUS_READY,
            # 服务继承主机环境（spec #10），主机无环境时回退导入请求环境
            env=host_obj.env or env_obj,
            service_connect_info=connection_obj,
            cluster_id=cluster_id,
            vip=vip,
            service_role=role,
        ))

    def create(self, request, *args, **kwargs):
        # 信任数据，只进行格式校验
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # 记录主机批量导入失败的日志
            logger.error(f"host batch import failed:{request.data}")
            # 若数据格式校验失败，抛出验证异常
            raise ValidationError("数据格式错误")

        # 获取当前请求环境上下文（多环境架构 Task 14）：
        # 部署方案/主安装历史按此环境落库，导入主机候选亦按此环境过滤
        request_env = get_request_env(request)

        # 从序列化数据中获取实例信息列表、实例名称列表、服务数据列表和服务名称列表
        instance_info_ls = serializer.data.get("instance_info_ls")
        instance_name_ls = list(
            map(lambda x: x.get("instance_name"), instance_info_ls))
        service_data_ls = serializer.data.get("service_data_ls")
        service_name_ls = list(
            map(lambda x: x.get("service_name"), service_data_ls))

        # 获取亲和力 tengine 字段，若配置中不存在则默认为 "tengine"
        tengine_name = AFFINITY_FIELD.get("tengine", "tengine")

        # 获取主机和基础环境的查询集，主机根据实例名称过滤（仅当前
        # 环境内的主机可见，跨环境主机按未纳管处理），基础环境为标记
        # 为基础环境的应用
        host_queryset = Host.objects.filter(
            instance_name__in=instance_name_ls, env=request_env)
        base_env_queryset = ApplicationHub.objects.filter(is_base_env=True)
        # 获取应用和产品的查询集，调用 _get_app_pro_queryset 方法
        app_queryset, pro_queryset = self._get_app_pro_queryset(
            service_name_ls)
        # 如果主机查询集为空，说明主机未纳管，抛出操作异常
        if not host_queryset.exists():
            raise OperateError("导入失败，主机未纳管")
        # 构建操作 UUID，若序列化数据中未提供则生成一个新的 UUID
        operation_uuid = serializer.data.get("operation_uuid") if \
            serializer.data.get("operation_uuid") else uuid.uuid4()

        # 记录真实使用的主机实例集合，过滤出实际使用的主机查询集
        service_instance_set = set(
            map(lambda x: x.get("instance_name"), service_data_ls))
        use_host_queryset = host_queryset.filter(
            instance_name__in=service_instance_set)

        try:
            # 初始化服务对象列表、基础环境字典、产品信息字典、单实例和集群服务字典、tengine 所在主机对象字典
            service_obj_ls = []
            base_env_dict = {}
            product_dict = {}
            only_dict, cluster_dict = {}, {}
            tengine_host_obj_dict = {}

            # 服务实例唯一集合，用于避免重复添加服务
            service_set = set()

            # 遍历服务数据列表，处理每个服务的安装信息
            for service_data in service_data_ls:
                instance_name = service_data.get("instance_name")
                service_name = service_data.get("service_name")
                # 获取服务的虚拟 IP 和角色
                vip = service_data.get("vip")
                role = service_data.get("role")
                # 获取主机和应用对象
                host_obj = use_host_queryset.filter(
                    instance_name=instance_name).first()
                app_obj = app_queryset.filter(app_name=service_name).first()

                # 亲和力为 tengine 字段 (Web 服务) 跳过，后续按照 product 维度补充
                if app_obj.extend_fields.get("affinity") == tengine_name and app_obj.app_type == ApplicationHub.APP_TYPE_SERVICE:
                    continue
                # 如果服务为 tengine 时，记录其所在节点
                if app_obj.app_name == tengine_name:
                    tengine_host_obj_dict[host_obj.ip] = host_obj

                # 检查服务依赖
                if app_obj.app_dependence:
                    dependence_list = json.loads(app_obj.app_dependence)
                    for dependence in dependence_list:
                        app_name = dependence.get("name")
                        # 从基础环境查询集中获取依赖的基础环境对象
                        base_env_obj = base_env_queryset.filter(
                            app_name=app_name).order_by("-created").first()
                        # 如果服务的依赖中有 base_env，并且对应 ip 上不存在则写入
                        if base_env_obj and \
                                app_name not in base_env_dict.get(host_obj.ip, []):
                            # 调用 _add_service 方法添加基础环境服务
                            self._add_service(
                                service_obj_ls, host_obj, base_env_obj, request_env,
                                only_dict, cluster_dict, product_dict, service_set,
                                is_base_env=True)
                            # 以 ip 为维度记录，避免重复
                            if host_obj.ip not in base_env_dict:
                                base_env_dict[host_obj.ip] = []
                            base_env_dict[host_obj.ip].append(app_name)

                # 添加当前服务
                self._add_service(
                    service_obj_ls, host_obj, app_obj, request_env,
                    only_dict, cluster_dict, product_dict, service_set,
                    vip=vip, role=role)

            # 获取亲和力为 tengine 字段 (Web 服务) 的应用列表
            app_target = ApplicationHub.objects.filter(
                product__in=pro_queryset)
            tengine_app_list = list(filter(
                lambda x: x.extend_fields.get("affinity") == tengine_name, app_target))

            # 为所有 tengine 节点添加亲和力服务
            for tengine_ip, host_obj in tengine_host_obj_dict.items():
                for app_obj in tengine_app_list:
                    self._add_service(
                        service_obj_ls, host_obj, app_obj, request_env,
                        only_dict, cluster_dict, product_dict, service_set)

            # 获取服务实例名称列表
            service_instance_name_ls = list(map(
                lambda x: x.service_instance_name, service_obj_ls))
            # 初始化 run_user 字典，记录每个实例的运行用户
            run_user_dict = {}
            for instance_info in instance_info_ls:
                if instance_info.get("run_user", "") != "":
                    run_user_dict[
                        instance_info.get("instance_name")
                    ] = instance_info.get("run_user")

            # 初始化服务 memory 字典，记录每个服务的内存配置
            service_memory_dict = {}
            for service_data in service_data_ls:
                if service_data.get("memory", "") != "":
                    service_memory_dict[
                        service_data.get("service_name")
                    ] = service_data.get("memory")

            # 数据库入库操作，使用事务保证数据一致性
            with transaction.atomic():

                # 已安装产品信息，批量创建产品实例（绑定当前环境，
                # 应用商店"已安装数量"按环境隔离统计）
                product_obj_ls = []
                for pro_name, pro_obj in product_dict.items():
                    upper_key = ''.join(random.choice(
                        string.ascii_uppercase) for _ in range(7))
                    product_obj_ls.append(Product(
                        product_instance_name=f"{pro_name}-{upper_key}",
                        product=pro_obj,
                        env=request_env
                    ))
                Product.objects.bulk_create(product_obj_ls)

                # 批量创建 service，return 无 id，需重查获取
                Service.objects.bulk_create(service_obj_ls)

                # 为所有服务统一补充集群信息
                for k, v in cluster_dict.items():
                    Service.objects.filter(
                        service__app_name=k
                    ).update(cluster_id=v[0])

                # 获取所有服务对象（服务实例名 app-IP尾段 跨环境可
                # 重名，须限定本次导入环境，避免 data.json 混入其它
                # 环境服务——本次导入创建的服务 env 均为 request_env）
                service_queryset = Service.objects.filter(
                    service_instance_name__in=service_instance_name_ls,
                    env=request_env
                ).select_related("service")

                # 遍历服务，如果存在依赖信息则补充
                for service_obj in service_queryset:
                    service_dependence_list = []
                    if service_obj.service.app_dependence:
                        dependence_list = json.loads(
                            service_obj.service.app_dependence)
                        for dependence in dependence_list:
                            app_name = dependence.get("name")
                            item = {
                                "name": app_name,
                                "cluster_name": None,
                                "instance_name": None,
                            }

                            if app_name in only_dict:
                                item["instance_name"] = only_dict.get(app_name)
                            elif app_name in cluster_dict:
                                item["cluster_name"] = cluster_dict.get(
                                    app_name)[1]
                            else:
                                # base_env 不在单实例和集群列表中
                                ip_split_ls = service_obj.ip.split(".")
                                service_instance_name = f"{app_name}-{ip_split_ls[-2]}-{ip_split_ls[-1]}"
                                item["instance_name"] = service_instance_name
                            service_dependence_list.append(item)
                    service_obj.service_dependence = json.dumps(
                        service_dependence_list)
                    service_obj.save()

                # 更新主机非base_env服务数量
                for host_obj in use_host_queryset:
                    obj_service_num = service_queryset.filter(
                        ip=host_obj.ip).exclude(service__is_base_env=True).count()
                    Host.objects.filter(
                        id=host_obj.id
                    ).update(service_num=obj_service_num)

                # 创建主安装记录表和后续任务记录表（绑定当前环境）
                main_history_obj = MainInstallHistory.objects.create(
                    operator=request.user.username,
                    operation_uuid=operation_uuid,
                    env=request_env,
                )
                PostInstallHistory.objects.create(
                    main_install_history=main_history_obj,
                )

                # 主机层安装记录表
                pre_install_obj_ls = []
                for host_obj in use_host_queryset:
                    pre_install_obj_ls.append(PreInstallHistory(
                        main_install_history=main_history_obj,
                        ip=host_obj.ip,
                    ))
                PreInstallHistory.objects.bulk_create(pre_install_obj_ls)

                # 构建基础组件多维列表，用于按顺序记录安装详情
                component_order_ls = [[] for _ in range(len(BASIC_ORDER))]
                for k, v in BASIC_ORDER.items():
                    for i in range(len(v)):
                        component_order_ls[k].append([])

                # 用于详情表排序的列表
                component_last_ls = []
                service_order_ls = []
                service_last_ls = []

                # 安装详情表
                for service_obj in service_queryset:
                    # 获取主机对象
                    host_obj = use_host_queryset.filter(
                        ip=service_obj.ip).first()

                    app_args = ServiceArgsPortUtils().get_app_install_args(
                        service_obj.service
                    )
                    # 获取服务对应的 run_user 和 memory
                    run_user = run_user_dict.get(host_obj.instance_name, None)
                    memory = service_memory_dict.get(
                        service_obj.service.app_name, None)
                    # 如果用户自定义 run_user、memory 需覆盖写入 install_args
                    if run_user:
                        for i in app_args:
                            if i.get("key") == "run_user":
                                i["default"] = run_user
                                break
                        else:
                            app_args.append({
                                "name": "安装用户",
                                "key": "run_user",
                                "default": run_user,
                            })
                    if memory:
                        for i in app_args:
                            if i.get("key") == "memory":
                                i["default"] = memory
                                break
                        else:
                            app_args.append({
                                "name": "运行内存",
                                "key": "memory",
                                "default": memory,
                            })

                    # {data_path} 占位符替换
                    for i in app_args:
                        if "dir_key" in i:
                            i["default"] = os.path.join(
                                host_obj.data_folder,
                                i.get("default", "").lstrip("/")
                            )

                    # 标记服务是否需要 post
                    post_action_flag = 4
                    if service_obj.service.extend_fields.get(
                            "post_action", "") != "":
                        post_action_flag = 0

                    # 服务端口
                    service_port = ServiceArgsPortUtils().get_app_port(
                        service_obj.service
                    )
                    # 构建 detail_install_args
                    detail_install_args = {
                        "ip": service_obj.ip,
                        "name": service_obj.service.app_name,
                        "ports": service_port,
                        "version": service_obj.service.app_version,
                        "run_user": "",
                        "data_folder": host_obj.data_folder,
                        "cluster_name": None,
                        "install_args": app_args,
                        "instance_name": service_obj.service_instance_name
                    }

                    detail_obj = DetailInstallHistory(
                        service=service_obj,
                        main_install_history=main_history_obj,
                        install_detail_args=detail_install_args,
                        post_action_flag=post_action_flag,
                    )

                    # 安装详情表按顺序录入
                    app_type = service_obj.service.app_type
                    # 公共组件
                    if app_type == ApplicationHub.APP_TYPE_COMPONENT:
                        for k, v in BASIC_ORDER.items():
                            if service_obj.service.app_name in v:
                                # 动态根据层级插入数据
                                target = v.index(service_obj.service.app_name)
                                component_order_ls[k][target].append(
                                    detail_obj)
                                break
                        else:
                            component_last_ls.append(detail_obj)

                    elif app_type == ApplicationHub.APP_TYPE_SERVICE:
                        app_level_str = service_obj.service.extend_fields.get(
                            "level", "")
                        if app_level_str == "":
                            service_last_ls.append(detail_obj)
                        else:
                            k = int(app_level_str)
                            # 动态根据层级索引创建空列表
                            if len(service_order_ls) <= k:
                                for i in range(len(service_order_ls), k + 1):
                                    service_order_ls.append([])
                            service_order_ls[k].append(detail_obj)
                    else:
                        pass

                # 合并多维列表和后置列表
                detail_history_obj_ls = []
                for child_ls in component_order_ls:
                    for i in child_ls:
                        if len(i) != 0:
                            detail_history_obj_ls += i
                detail_history_obj_ls += component_last_ls
                for i in service_order_ls:
                    detail_history_obj_ls += i
                detail_history_obj_ls += service_last_ls

                DetailInstallHistory.objects.bulk_create(detail_history_obj_ls)

                # 部署计划表（绑定当前环境，多环境架构 Task 14）
                DeploymentPlan.objects.create(
                    plan_name=f"快速部署-{str(int(round(time.time() * 1000)))}",
                    host_num=use_host_queryset.count(),
                    product_num=pro_queryset.count(),
                    service_num=len(service_data_ls),
                    create_user=request.user.username,
                    operation_uuid=operation_uuid,
                    env=request_env,
                )

                # 生成 data.json
                data_json = DataJson(
                    operation_uuid=str(operation_uuid),
                    service_obj=service_queryset)
                data_json.run()

        except Exception as err:
            # 记录导入执行计划失败的错误日志
            logger.error(f"import deployment plan err: {err}")
            import traceback
            logger.error(traceback.print_exc())
            # 若出现异常，抛出操作异常
            raise OperateError(f"导入执行计划失败: {err}")

        # 返回包含操作 UUID、主机数量、产品数量和服务数量的响应
        return Response({
            "operation_uuid": operation_uuid,
            "host_num": host_queryset.count(),
            "product_num": pro_queryset.count(),
            "service_num": len(service_data_ls),
        })


class ExecutionRecordAPIView(GenericViewSet, ListModelMixin):
    queryset = ExecutionRecord.objects.exclude(count=0).all()
    pagination_class = PageNumberPager
    filter_backends = (OrderingFilter, SearchFilter)
    search_fields = ("module",)
    ordering_fields = ("created",)
    ordering = ('-created',)
    serializer_class = ExecutionRecordSerializer
    # 操作信息描述
    get_description = "查询执行记录"

    def get_queryset(self):
        # 执行记录列表按当前环境上下文过滤（多环境架构 Task 14）
        return super(ExecutionRecordAPIView, self).get_queryset().filter(
            env=get_request_env(self.request))


class ProductCompositionView(GenericViewSet, ListModelMixin,
                             CreateModelMixin):
    serializer_class = ProductCompositionSerializer
    # 关闭权限、认证设置
    authentication_classes = ()
    permission_classes = ()

    get_description = "查询产品信息"
    post_description = "修改产品包含服务信息"

    def get_queryset(self):
        return ProductHub.objects.filter(**self.request.query_params.dict())

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        for data in serializer.data:
            data["pro_services"] = json.loads(data.get("pro_services"))
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        pro_services = json.dumps(request.data.get("pro_services", []), ensure_ascii=False)
        request.data["pro_services"] = pro_services

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = request.data
        pro_obj = ProductHub.objects.filter(
            pro_name=params.get('pro_name'), pro_version=params.get('pro_version')
        ).first()
        pro_obj.pro_services = pro_services
        pro_obj.save()

        return Response("修改成功")


class DeleteAppStorePackageView(GenericViewSet, ListModelMixin, CreateModelMixin):
    """
        get:
        查看应用商店
    """
    get_description = "查看应用商店"
    post_description = "删除应用商店"

    def get_queryset(self):
        if self.request.query_params.get('type') == "component":
            return ApplicationHub.objects.filter(
                app_type=ApplicationHub.APP_TYPE_COMPONENT).order_by("-created")
        else:
            return ProductHub.objects.all().order_by("-created")

    def get_serializer_class(self):
        if self.request.query_params.get('type') == "component":
            return DeleteComponentSerializer
        return DeleteProDuctSerializer

    def list(self, request, *args, **kwargs):
        app_type = request.GET.get("type")
        if not app_type or app_type not in ["component", "product"]:
            raise OperateError("请传入type或合法type")
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        app_name_dc = {}
        for _ in serializer.data:
            app_name_dc.setdefault(_["name"], []).extend(_["versions"])
        res_ls = []
        for name, versions in app_name_dc.items():
            res_ls.append({"name": name, "versions": versions})
        return Response(
            {"data": res_ls,
             "type": app_type}
        )

    @staticmethod
    def explain_info():
        app_ls = ApplicationHub.objects.all().values_list(
            "id", "app_name", "app_version", "product")
        pro_ls = ProductHub.objects.all().values_list("id", "pro_name", "pro_version")
        app_dc = {}
        pro_id_app_count = {}
        for app in app_ls:
            app_dc[f"{app[1]}|{app[2]}"] = app[0]
            if app[3]:
                pro_id_app_count[app[3]] = pro_id_app_count.get(app[3], 0) + 1
        pro_id_count = {}
        for pro in pro_ls:
            if pro_id_app_count.get(pro[0]):
                pro_id_count[f"{pro[1]}|{pro[2]}"] = [
                    pro_id_app_count[pro[0]], pro[0]]
            else:
                pro_id_count[f"{pro[1]}|{pro[2]}"] = [0, pro[0]]
        return pro_id_count, app_dc

    def check_service(self, params):
        pro_id_count, app_dc = self.explain_info()
        ser_id = []
        pro_dc = {}
        for info in params["data"]:
            if params['type'] == "component":
                for version in info["versions"]:
                    app_id = app_dc.get(f'{info["name"]}|{version}')
                    if app_id:
                        ser_id.append(app_id)
            else:
                # 查询选择的产品是不是勾选全部
                pro_info = pro_id_count[info["name"]]
                # 确定就是产品删除
                if pro_info[0] == len(info["versions"]):
                    pro_dc[pro_info[1]] = info["name"]
                for _ in info["versions"]:
                    app_id = app_dc.get(_)
                    if app_id:
                        ser_id.append(app_id)
        ser_name = Service.objects.filter(
            service__in=ser_id).values_list('service_instance_name', flat=True)
        if ser_name:
            raise OperateError(f'存在已安装的服务{",".join(ser_name)}')
        return ser_id, pro_dc

    @staticmethod
    def del_file(file_path):
        logger.info(f"应用包可能删除的路径 {file_path}")
        if file_path and len(file_path) > 28:
            _out, _err, _code = cmd(f"/bin/rm -rf {file_path}")
            if _code != 0:
                raise OperateError(f'执行cmd异常,删除路径失败{file_path}:{_err},{_out}')

    def del_database(self, ser_id, pro_dc):
        app_objs = ApplicationHub.objects.filter(id__in=ser_id)
        del_ser_file = []
        for app in app_objs:
            if app.app_package.package_name:
                del_ser_file.append(os.path.join(
                    PROJECT_DIR, "package_hub", app.app_package.package_path,
                    app.app_package.package_name,
                ))
        self.del_file(" ".join(del_ser_file))
        app_objs.delete()
        if pro_dc:
            del_pro_file = []
            for pro_id, pro_info in pro_dc.items():
                pro_info = pro_info.replace("|", "-")
                if pro_info:
                    del_pro_file.append(
                        os.path.join(PROJECT_DIR, f"package_hub/verified/{pro_info}"))
            self.del_file(" ".join(del_pro_file))
            ProductHub.objects.filter(id__in=list(pro_dc)).delete()

    def create(self, request, *args, **kwargs):
        params = request.data
        app_type = params.get('type', None)
        if not app_type:
            raise OperateError("请传入类型")
        ser_id, pro_dc = self.check_service(params)
        self.del_database(ser_id, pro_dc)
        return Response({"status": "删除成功"})
