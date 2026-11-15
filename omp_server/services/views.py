import copy
import json
import logging
import os
import uuid

from app_store.new_install_utils import (
    CreateInstallPlan as NewCreateInstallPlan,
    RedisDB,
)
from django.conf import settings
from django.http import Http404
from django.utils import timezone
from django_filters.rest_framework.backends import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import (
    ListModelMixin, RetrieveModelMixin,
    CreateModelMixin
)
from rest_framework.response import Response
from rest_framework.filters import OrderingFilter

from db_models.models import (
    Service, ApplicationHub, MainInstallHistory, Host, ClusterInfo, Product,
    DetailInstallHistory, UploadPackageHistory,
)
from utils.parse_config import BASIC_ORDER
from service_upgrade.update_data_json import DataJsonUpdate
from services.permission import GetDataJsonAuthenticated
from services.tasks import exec_action
from services.services_filters import ServiceFilter
from services.services_serializers import (
    ServiceSerializer, ServiceDetailSerializer,
    ServiceActionSerializer, ServiceDeleteSerializer,
    ServiceStatusSerializer, AppListSerializer
)
from promemonitor.prometheus import Prometheus
from promemonitor.grafana_url import explain_url
from utils.common.exceptions import OperateError
from utils.common.paginations import PageNumberPager
from utils.middleware_handler import get_request_env
from operator import itemgetter
from services.app_check import (
    ConfCheck, ManagerService
)

logger = logging.getLogger('server')


def _build_use_exist_from_dependence(service_dependence):
    """从 Service.service_dependence 反推 _step_2_origin_data.use_exist。

    service_dependence 是 JSON 字符串,格式:
    [{"name": "mysql", "cluster_name": "mysql-cluster", "instance_name": None},
     {"name": "jdk", "cluster_name": None, "instance_name": "jdk-1.8.0-1"}]

    返回 dict,供 _step_2_origin_data.use_exist 使用:
    {"mysql": {"id": 1, "name": "mysql-cluster", "type": "cluster"},
     "jdk":   {"id": 2, "name": "jdk-1.8.0-1",    "type": "single"}}

    注意 value 是单个 dict 不是 list:new_install_utils._get_exist_dep
    (约 L1915)直接 inner.get("type"),所以 use_exist[name] 必须是 dict。
    同名依赖多条时后者覆盖前者(实际场景很少)。

    重装场景下依赖必满足(初始安装成功过),反查不到时跳过该项。
    """
    if not service_dependence:
        return {}
    try:
        dependence_list = json.loads(service_dependence)
    except (ValueError, TypeError):
        return {}
    if not isinstance(dependence_list, list):
        return {}

    use_exist = {}
    for dep in dependence_list:
        if not isinstance(dep, dict):
            continue
        dep_name = dep.get("name")
        if not dep_name:
            continue
        cluster_name = dep.get("cluster_name")
        instance_name = dep.get("instance_name")
        if cluster_name:
            cluster = ClusterInfo.objects.filter(
                cluster_name=cluster_name,
            ).first()
            if cluster:
                use_exist[dep_name] = {
                    "id": cluster.id,
                    "name": cluster.cluster_name,
                    "type": "cluster",
                }
        elif instance_name:
            svc = Service.objects.filter(
                service_instance_name=instance_name,
            ).first()
            if svc:
                use_exist[dep_name] = {
                    "id": svc.id,
                    "name": svc.service_instance_name,
                    "type": "single",
                }
    return use_exist


class ServiceListView(GenericViewSet, ListModelMixin):
    """
        list:
        查询服务列表
    """
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    pagination_class = PageNumberPager
    # 过滤，排序字段
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    filter_class = ServiceFilter
    ordering_fields = ("ip", "service_instance_name")
    # 动态排序字段
    dynamic_fields = ("cpu_usage", "mem_usage")
    # 操作描述信息
    get_description = "查询服务列表"

    def get_queryset(self):
        """ 服务列表按当前环境上下文过滤（Service 自有 env FK，不 join host） """
        return Service.objects.filter(
            env=get_request_env(self.request))

    def list(self, request, *args, **kwargs):
        # 获取序列化数据列表
        queryset = self.filter_queryset(self.get_queryset())
        real_query = queryset

        # 实时获取服务动态git
        prometheus_obj = Prometheus()
        is_success, prometheus_dict = prometheus_obj.get_all_service_status()

        # 当未指定排序字段且查询成功时
        query_field = request.query_params.get("ordering", "")
        if is_success and query_field == "":
            stop_ls = []
            natural_ls = []
            no_monitor_ls = []
            ing_ls = []
            for service in queryset:
                # 当服务状态为 '正常' 和 '异常' 时
                if service.service_status in (Service.SERVICE_STATUS_NORMAL, Service.SERVICE_STATUS_STOP):
                    key_name = f"{service.ip}_{service.service_instance_name}"
                    status = prometheus_dict.get(key_name, None)
                    if status is None:
                        no_monitor_ls.append(service)
                    elif not status:
                        stop_ls.append(service)
                    else:
                        natural_ls.append(service)
                else:
                    ing_ls.append(service)
            real_query = stop_ls + ing_ls + natural_ls + no_monitor_ls

        serializer = self.get_serializer(
            self.paginate_queryset(real_query), many=True)
        serializer_data = serializer.data

        # 若获取成功，则动态覆盖服务状态
        if is_success:
            status_dict = {
                True: "正常",
                False: "停止",
                None: "未监控",
            }
            for service_obj in serializer_data:
                # 如果服务状态为 '正常' 和 '停止' 的服务，通过 Prometheus 动态更新
                if service_obj.get("service_status") in ("正常", "停止"):
                    # 如果是 web 服务，则状态直接置为正常
                    if service_obj.get("is_web"):
                        service_obj["service_status"] = "正常"
                        continue
                    key_name = f"{service_obj.get('ip')}_{service_obj.get('service_instance_name')}"
                    status = prometheus_dict.get(key_name, None)
                    service_obj["service_status"] = status_dict.get(status)

        # 获取监控及日志的url
        serializer_data = explain_url(
            serializer_data, is_service=True)

        serializer_data = prometheus_obj.get_service_info(serializer_data)
        reverse_flag = False
        if query_field.startswith("-"):
            reverse_flag = True
            query_field = query_field[1:]
        # 若排序字段在类视图 dynamic_fields 中，则对根据动态数据进行排序
        none_ls = list(filter(
            lambda x: x.get(query_field) is None,
            serializer_data))
        exists_ls = list(filter(
            lambda x: x.get(query_field) is not None,
            serializer_data))
        if query_field in self.dynamic_fields:
            exists_ls = sorted(
                exists_ls,
                key=lambda x: x.get(query_field),
                reverse=reverse_flag)
        exists_ls.extend(none_ls)
        return self.get_paginated_response(exists_ls)

    @action(
        detail=False, methods=['get'], url_path='get_app_latest_version'
    )
    def get_app_latest_version(self, request):
        """通过 app_name 反查最新已发布的 ApplicationHub 版本。

        服务重装流程第 5.5 步:`localPackageScanResult` 返回结构不含版本号字段,
        扫描完成后必须额外反查一次拿到新版本号。

        反查逻辑:`ApplicationHub.objects.filter(app_name=...).order_by("-id").first()`,
        主键自增保证 id 最大的就是最新扫描出来的记录。**依赖步骤 3 已删旧
        ApplicationHub**,若旧记录未删则可能返回错误版本(已在 spec §10 风险表标注)。

        返回值会被 utils.response_handler.APIRenderer 再包一层
        {code:0, message:"success", data:<本接口返回内容>}。
        """
        app_name = request.query_params.get("app_name")
        if not app_name:
            return Response({
                "code": 1,
                "message": "app_name 必填",
            }, status=400)

        app = ApplicationHub.objects.filter(
            app_name=app_name,
        ).order_by("-id").first()
        if not app:
            return Response({
                "code": 1,
                "message": f"找不到 app_name={app_name} 对应的应用",
            }, status=400)

        if not app.app_package:
            return Response({
                "code": 1,
                "message": f"应用 {app_name}-{app.app_version} 未关联安装包",
            }, status=400)
        if (
            app.app_package.package_status
            != UploadPackageHistory.PACKAGE_STATUS_PUBLISH_SUCCESS
        ):
            return Response({
                "code": 1,
                "message": f"应用 {app_name}-{app.app_version} 包未发布成功",
            }, status=400)

        return Response({
            "app_name": app.app_name,
            "latest_version": app.app_version,
            "app_id": app.id,
        })

    @action(
        detail=False, methods=['post'], url_path='install_with_package'
    )
    def install_with_package(self, request):
        """服务重装核心入口:接收 params 包 + 新版本号,内部调
        new_install_utils.CreateInstallPlan([detail_args], unique_key).run()
        完成服务安装。

        服务重装流程第 6 步。params 来自 install_params 步骤的快照,
        new_version 来自 get_app_latest_version 步骤。本 action 会覆写
        params.detail_install_args.version 为 new_version,然后构造
        新链路入参(list of detail_args)调用
        new_install_utils.CreateInstallPlan,后者内部会自动触发
        install_service 异步任务,无需手动触发。

        为什么走新链路而非老链路(install_utils.CreateInstallPlan):
        老链路内部 DataJson 用 `Service.objects.all()`(包含执行安装链路
        Service),会触发 `'NoneType' object is not iterable` bug;
        新链路 DataJson 用 `Service.split_objects.all()`(排除执行安装链路
        Service),不触发 bug,与 Web UI 走的 CreateInstallPlanView 一致。

        返回值会被 utils.response_handler.APIRenderer 再包一层
        {code:0, message:"success", data:<本接口返回内容>}。
        """
        params = request.data.get("params")
        new_version = request.data.get("new_version")

        if not params or not isinstance(params, dict):
            return Response({
                "code": 1,
                "message": "params 必须是非空 dict",
            }, status=400)
        if not new_version or not isinstance(new_version, str):
            return Response({
                "code": 1,
                "message": "new_version 必须为非空字符串",
            }, status=400)

        # 防御性 deepcopy,避免修改外部传入的 params
        params = copy.deepcopy(params)
        detail_args = params.get("detail_install_args")
        if not detail_args or not isinstance(detail_args, dict):
            return Response({
                "code": 1,
                "message": "params.detail_install_args 必须是非空 dict",
            }, status=400)

        # 校验关键字段:name / ip 必须有;instance 字段二选一(兼容老/新链路 schema)
        app_name = detail_args.get("name")
        ip = detail_args.get("ip")
        if not app_name or not ip:
            return Response({
                "code": 1,
                "message": "detail_install_args 的 name 和 ip 必填",
            }, status=400)
        instance_name = (
            detail_args.get("service_instance_name")
            or detail_args.get("instance_name")
        )
        if not instance_name:
            return Response({
                "code": 1,
                "message": "detail_install_args 必须含 service_instance_name "
                           "或 instance_name 之一",
            }, status=400)

        # 校验新版本对应 ApplicationHub 存在 + 包已发布
        new_app = ApplicationHub.objects.filter(
            app_name=app_name, app_version=new_version,
        ).order_by("-id").first()
        if not new_app:
            return Response({
                "code": 1,
                "message": f"找不到 {app_name}-{new_version} 对应的应用",
            }, status=400)
        if not new_app.app_package or (
            new_app.app_package.package_status
            != UploadPackageHistory.PACKAGE_STATUS_PUBLISH_SUCCESS
        ):
            return Response({
                "code": 1,
                "message": f"包 {app_name}-{new_version} 未发布成功",
            }, status=400)

        # 校验服务走新链路。service_split=1 是老链路 ExecuteInstallView(已弃用),
        # detail_install_args 用老 schema(app_install_args/service_instance_name),
        # 传给 NewCreateInstallPlan 会 KeyError。
        if params.get("service_split") == 1:
            return Response({
                "code": 1,
                "message": "本期不支持老链路(service_split=1)服务重装,仅支持新链路",
            }, status=400)

        # 按 app_type 分支:组件 vs 自研应用。
        # - 组件(APP_TYPE_COMPONENT): install.product = None,无需 _step_3_checked_data
        # - 自研应用(APP_TYPE_SERVICE): install.product = pro_name,
        #   且需多写 _step_3_checked_data(供 create_product_instance 读取,
        #   内部用 Product.objects.get_or_create(product_instance_name=cluster_name,
        #   product=...) 创建/复用实例)。
        if new_app.app_type == ApplicationHub.APP_TYPE_COMPONENT:
            install_product = None
        elif new_app.app_type == ApplicationHub.APP_TYPE_SERVICE:
            # 自研应用必须有 product 关联(指向 ProductHub)
            if not new_app.product:
                return Response({
                    "code": 1,
                    "message": "自研应用缺少 product 关联,无法重装",
                }, status=400)
            install_product = new_app.product.pro_name
        else:
            return Response({
                "code": 1,
                "message": f"未知 app_type={new_app.app_type}",
            }, status=400)

        # 覆写 version 指向新版本
        detail_args["version"] = new_version

        # 生成 operation_uuid(新链路 CreateInstallPlan 期望 unique_key 入参,
        # 不传时 DataJson 会找不到 uuid 对应 json 文件)
        operation_uuid = str(uuid.uuid4())

        # 预填 Redis 数据,让 NewCreateInstallPlan.run() 内部的
        # get_dependence(读 _step_2_origin_data)和 WithServiceUtils(读 _with_ser)
        # 能正确取到数据。Web UI 通过 4 步预处理 serializer 写入,这里基于
        # install_params 快照里的 service_dependence 一次性构造等价数据。
        use_exist = _build_use_exist_from_dependence(
            params.get("service_dependence")
        )
        redis_db = RedisDB()
        # 1. _step_2_origin_data: get_dependence 用。install 只放本次重装的
        #    服务(product: 组件为 None,自研应用为 pro_name);use_exist 把所有
        #    依赖标记为复用已有,让 _get_exist_dep 走 ClusterInfo/Service 反查分支。
        redis_db.set(
            name=f"{operation_uuid}_step_2_origin_data",
            data={
                "install": {
                    app_name: {"version": new_version, "product": install_product},
                },
                "use_exist": use_exist,
            },
        )
        # 2. 自研应用多写 _step_3_checked_data:create_product_instance 用,
        #    遍历 basic 找匹配 pro_name+pro_version 的项,取 cluster_name 做
        #    Product.objects.get_or_create。
        #    cluster_name 取 params["cluster_name"](install_params 卸载前
        #    反查的原 ProductInstance.product_instance_name)。
        #    - 按产品安装场景: cluster_name 非空,get_or_create 复用/重建实例
        #    - 单服务安装场景: cluster_name 为空,basic 留空列表让 for 循环
        #      跳过,避免 get_or_create(null) 创建脏 ProductInstance
        if new_app.app_type == ApplicationHub.APP_TYPE_SERVICE:
            cluster_name = params.get("cluster_name")
            if cluster_name:
                basic = [{
                    "name": new_app.product.pro_name,
                    "version": new_app.product.pro_version,
                    "cluster_name": cluster_name,
                }]
            else:
                basic = []
            redis_db.set(
                name=f"{operation_uuid}_step_3_checked_data",
                data={
                    "unique_key": operation_uuid,
                    "data": {"basic": basic},
                },
            )
        # 3. _with_ser: WithServiceUtils.run 用,重装场景无伴随服务。
        redis_db.set(name=f"{operation_uuid}_with_ser", data=[])
        # 4. unique_key 标志位: get_unique_key 校验存在性。
        redis_db.set(name=operation_uuid, data={})

        # 调用新链路 CreateInstallPlan(spike §1/§3.5 验证可直接实例化调用,
        # 内部 run() 会自动触发 install_service_task.delay)
        plan = NewCreateInstallPlan(
            [detail_args], unique_key=operation_uuid,
        )
        flag, msg = plan.run()
        if not flag:
            return Response({
                "code": 1,
                "message": f"重装失败: {msg}",
            }, status=500)

        # 防御性查询 main_history(用 filter().first() 避免
        # MultipleObjectsReturned,spike §5)
        main = MainInstallHistory.objects.filter(
            operation_uuid=operation_uuid,
        ).order_by("-id").first()
        if not main:
            return Response({
                "code": 1,
                "message": f"找不到 operation_uuid={operation_uuid} 对应的安装记录",
            }, status=500)

        return Response({
            "operation_uuid": operation_uuid,
            "main_history_id": main.id,
        })


class ServiceDetailView(GenericViewSet, RetrieveModelMixin):
    """
        read:
        查询服务详情
    """
    queryset = Service.objects.all()
    serializer_class = ServiceDetailSerializer
    # 操作描述信息
    get_description = "查询服务详情"

    def get_queryset(self):
        """ 服务详情按当前环境上下文过滤（跨环境服务不可见，伪造 id 404） """
        return Service.objects.filter(
            env=get_request_env(self.request))

    @action(detail=True, methods=['get'], url_path='install_params')
    def install_params(self, request, pk=None):
        """获取服务重装所需的参数包。

        服务重装流程第 1 步:返回 service + ApplicationHub +
        DetailInstallHistory 的关键参数,供 AI 后续透传给
        install_with_package。

        状态校验:服务处于 installing/deleting/upgrade/rollback 状态时拒绝。
        返回值会被 utils.response_handler.APIRenderer 再包一层
        {code:0, message:"success", data:<本接口返回内容>}。
        """
        # 显式按 pk 反查(走环境过滤后的 queryset,跨环境服务等价不存在);
        # 未找到返回 400(全局 exception_handler 会把 Http404 转成 200 body,
        # 不符合调用方语义)。
        service = self.get_queryset().filter(id=pk).first()
        if service is None:
            return Response({
                "code": 1,
                "message": f"服务(id={pk})不存在",
            }, status=400)

        # 状态校验
        forbidden_statuses = (
            Service.SERVICE_STATUS_INSTALLING,    # 6
            Service.SERVICE_STATUS_DELETING,      # 9
            Service.SERVICE_STATUS_UPGRADE,       # 10
            Service.SERVICE_STATUS_ROLLBACK,      # 11
        )
        if service.service_status in forbidden_statuses:
            return Response({
                "code": 1,
                "message": f"服务处于状态 {service.service_status},无法重装",
            }, status=400)

        # 反查 DetailInstallHistory(取最后一条成功的)
        detail = DetailInstallHistory.objects.filter(
            service=service,
            install_step_status=DetailInstallHistory.INSTALL_STATUS_SUCCESS,
        ).order_by("-id").first()
        if not detail:
            return Response({
                "code": 1,
                "message": "找不到原始安装记录,无法重装",
            }, status=400)

        # 构造 params 包
        app = service.service  # ApplicationHub
        package = app.app_package if app else None
        main = detail.main_install_history

        # cluster_name: 自研应用按产品维度安装时,反查原 ProductInstance.
        # product_instance_name,作为 _step_3_checked_data.basic[].cluster_name
        # 的真实值(create_product_instance 把它读作 product_instance_name 做
        # get_or_create)。若原服务是单服务安装(无 ProductInstance),返回 None,
        # install_with_package 会让 create_product_instance 静默跳过。
        cluster_name = None
        if app and app.product:
            # 按服务所属环境反查产品实例（多环境：跨环境实例名
            # 互不可见，避免重装时复制出错误环境的实例）
            existing_pi = Product.objects.filter(
                product=app.product,
                env=service.env,
            ).order_by("-id").first()
            if existing_pi:
                cluster_name = existing_pi.product_instance_name

        return Response({
            "service_id": service.id,
            "service_instance_name": service.service_instance_name,
            "ip": service.ip,
            "app_name": app.app_name if app else None,
            "app_version": app.app_version if app else None,
            "package_name": package.package_name if package else None,
            "env_id": service.env_id,
            "cluster_id": service.cluster_id,
            "service_port": service.service_port,
            "service_controllers": service.service_controllers,
            "main_install_args": main.install_args if main else None,
            "detail_install_args": detail.install_detail_args,
            # service_dependence: JSON 字符串或 null。install_with_package
            # 会解析它反推 _step_2_origin_data.use_exist,让 get_dependence
            # 走 _get_exist_dep 分支(复用已存在的依赖实例)。
            "service_dependence": service.service_dependence,
            # service_split: 1=老链路(ExecuteInstallView,已弃用),
            # 2=新链路(CreateInstallPlanView,生产路径)。install_with_package
            # 仅支持新链路重装。
            "service_split": service.service_split,
            # cluster_name: 见上方反查逻辑,自研应用按产品安装时非空,
            # 单服务安装或组件为 None。
            "cluster_name": cluster_name,
            "snapshot_time": timezone.now().isoformat(),
        })


class ServiceActionView(GenericViewSet, CreateModelMixin):
    """
        create:
        服务启停删除
    """
    queryset = Service.objects.all()
    serializer_class = ServiceActionSerializer
    post_description = "执行启动停止或卸载操作"

    def create(self, request, *args, **kwargs):
        many_data = self.request.data.get('data')
        # 按 id 定位服务执行启停/卸载：仅允许本环境服务（跨环境 id
        # 视为越权操作直接拒绝，多环境架构 Task 7b）；exec_action 任务
        # 只会收到视图闸门放行的本环境服务 id，任务侧按 service.env 执行
        env = get_request_env(request)
        for data in many_data:
            action = data.get("action")
            instance = data.get("id")
            operation_user = data.get("operation_user")
            del_file = data.get("del_file", True)
            service_obj = Service.objects.filter(id=instance).first()
            if service_obj is not None and service_obj.env_id != env.id:
                return Response(
                    data={"code": 1, "message": f"服务实例{instance}不属于当前环境"})
            need_split = ["hadoop"]
            if service_obj and service_obj.service.app_name in need_split and action == 4:
                delete_objs = Service.objects.filter(ip=service_obj.ip, service__app_name="hadoop")
                status = service_obj.service_status
                delete_objs.update(service_status=Service.SERVICE_STATUS_DELETING)
                if status != Service.SERVICE_STATUS_DELETING \
                        and delete_objs.first().id == service_obj.id:
                    del_file = True
                else:
                    del_file = False
            if action and instance and operation_user:
                if action == 4:
                    try:
                        service_obj.service_status = Service.SERVICE_STATUS_DELETING
                        service_obj.save()
                    except Exception as e:
                        logger.error(f"service实例id，不存在{instance}:{e}")
                        return Response("执行异常")
                exec_action.delay(action, instance, operation_user, del_file)
            else:
                raise OperateError("请输入action或id")
        return Response("执行成功")


class ServiceDeleteView(GenericViewSet, CreateModelMixin):
    """
        create:
        服务删除校验
    """
    queryset = Service.objects.all()
    serializer_class = ServiceDeleteSerializer
    post_description = "查看服务删除校验依赖"

    def create(self, request, *args, **kwargs):
        """
        检查被依赖关系，包含多服务匹配
        例如 jdk-1.8和 test-app被同时标记删除
        test-app依赖jdk-1.8，同时标记则不显示依赖。单选jdk1.8则会显示。
        """
        many_data = self.request.data.get('data')
        # 依赖校验只在当前环境内解析：跨环境服务 id 视为不存在，
        # 不泄露其它环境的依赖关系（多环境架构 Task 7b）
        service_objs = Service.objects.filter(
            env=get_request_env(self.request))
        app_objs = ApplicationHub.objects.all()
        service_json = {}
        dependence_dict = []
        # 存在的service key
        for i in service_objs:
            service_key = f"{i.service.app_name}-{i.service.app_version}"
            service_json[i.id] = service_key
        # 全量app的dependence反向
        for app in app_objs:
            if app.app_dependence:
                for i in json.loads(app.app_dependence):
                    dependence_dict.append(
                        {f"{i.get('name')}-{i.get('version')}": f"{app.app_name}-{app.app_version}"}
                    )
        exist_service = set()
        # 过滤存在的实例所属app的key
        for data in many_data:
            instance = int(data.get("id"))
            filter_list = service_json.get(instance)
            exist_service.add(filter_list)
        # 查看存在的服务有没有被依赖的，做set去重
        res = set()
        for i in exist_service:
            for j in dependence_dict:
                if j.get(i):
                    res.add(j.get(i))
        res = res - exist_service
        # 查看是否需要被依赖的是否已不存在
        res = res & set(service_json.values())
        res = "存在依赖信息:" + ",".join(res) if res else "无依赖信息"
        return Response(res)


class ServiceStatusView(GenericViewSet, ListModelMixin):
    """
        list:
        查询服务列表
    """
    queryset = Service.objects.filter(
        service__is_base_env=False)
    serializer_class = ServiceStatusSerializer
    authentication_classes = ()
    permission_classes = ()
    # 操作描述信息
    get_description = "查询服务状态"

    def list(self, request, *args, **kwargs):
        # 获取序列化数据列表
        queryset = self.get_queryset()
        real_query = queryset
        # 实时获取服务动态git
        prometheus_obj = Prometheus()
        is_success, prometheus_dict = prometheus_obj.get_all_service_status()
        if is_success:
            stop_ls = []
            natural_ls = []
            no_monitor_ls = []
            ing_ls = []
            for service in queryset:
                # 当服务状态为 '正常' 和 '异常' 时
                if service.service_status in (Service.SERVICE_STATUS_NORMAL, Service.SERVICE_STATUS_STOP):
                    key_name = f"{service.ip}_{service.service_instance_name}"
                    status = prometheus_dict.get(key_name, None)
                    if status is None:
                        no_monitor_ls.append(service)
                    elif not status:
                        stop_ls.append(service)
                    else:
                        natural_ls.append(service)
                else:
                    ing_ls.append(service)
            real_query = stop_ls + ing_ls + natural_ls + no_monitor_ls

        serializer = self.get_serializer(real_query, many=True)
        serializer_data = serializer.data

        # 若获取成功，则动态覆盖服务状态
        if is_success:
            for service_obj in serializer_data:
                # 如果服务状态为 '正常' 和 '停止' 的服务，通过 Prometheus 动态更新
                if service_obj.get("service_status") in ("正常", "停止"):
                    # 如果是 web 服务，则状态直接置为正常
                    if service_obj.get("is_web"):
                        service_obj["service_status"] = True
                        continue
                    key_name = f"{service_obj.get('ip')}_{service_obj.get('service_instance_name')}"
                    status = prometheus_dict.get(key_name, None)
                    service_obj["service_status"] = status
        return Response(serializer_data)


class ServiceDataJsonView(APIView):
    # for automated testing
    permission_classes = (GetDataJsonAuthenticated,)

    def get(self, request):
        main_install = MainInstallHistory.objects.order_by("-id").first()
        if not main_install:
            raise Http404('No install history matches the given query.')
        json_path = os.path.join(
            settings.PROJECT_DIR,
            f"package_hub/data_files/{main_install.operation_uuid}.json"
        )
        if not os.path.exists(json_path):
            # data.json 按主安装记录所属环境过滤（多环境隔离）
            DataJsonUpdate(
                main_install.operation_uuid,
                env_id=main_install.env_id).create_json_file()
        with open(json_path, "r") as f:
            json_data = json.load(f)
        return Response({"json_data": json_data})


class AppListView(GenericViewSet, ListModelMixin, CreateModelMixin):
    queryset = ApplicationHub.objects.all().exclude(app_name__in=["hadoop", "doim"])
    serializer_class = AppListSerializer
    get_description = "应用列表查询"
    post_description = "列表合法性校验"
    need_key = ['base_dir', 'run_user', 'service_port', 'data_dir', 'log_dir']

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        app_dc = {}
        app_ls = []
        for query in queryset:
            if query.pro_info:
                pro_name = query.pro_info["pro_name"]
                pro_version = query.pro_info["pro_version"]
                app_dc.setdefault(pro_name, {})
                app_dc[pro_name].setdefault("version", [])
                if pro_version not in app_dc[pro_name]["version"]:
                    app_dc[pro_name]["version"].append(pro_version)
                app_dc[pro_name].setdefault("child", {})
                app_dc[pro_name]["child"].setdefault(pro_version, []).append(
                    {"name": query.app_name, "version": query.app_version})
            else:
                app_dc.setdefault(query.app_name, {})
                app_dc[query.app_name].setdefault("version", []).append(query.app_version)

        basic_ls = [list() for _ in range(len(BASIC_ORDER))]
        pro_ls = []
        for name, info in app_dc.items():
            tmp_dc = {
                "name": name,
                "version": info["version"]
            }
            if info.get("child"):
                tmp_dc.update({"child": info.get("child")})
                pro_ls.append(tmp_dc)
            else:
                for index, name_ls in BASIC_ORDER.items():
                    if name in name_ls:
                        basic_ls[index].append(tmp_dc)
        for i in basic_ls:
            app_ls.extend(i)
        app_ls.extend(pro_ls)
        return Response(app_ls)

    def check_repeat(self, app_data):
        """
        查询重复
        """
        for info in app_data:
            if len(info.get("version", [])) != 1:
                info.setdefault("error", f"{info.get('name')}不允许纳管不同版本")
                self.error = True
            if info.get("child"):
                app_names = []
                for app_info in list(info["child"].values())[0]:
                    app_name = app_info.get("name")
                    if app_name not in app_names:
                        app_names.append(app_name)
                    else:
                        info.setdefault("error", f"{info.get('name')}产品下{app_name}服务只允许选其中一个")
                        self.error = True

    @staticmethod
    def check_dependence_one(dependence_dc, installed_ser_all):
        """
        检查单个服务依赖是否存在
        """
        lost_ser = []
        for dependence in dependence_dc:
            dependence_ser = f'{dependence.get("name")}:{dependence.get("version")}'
            if dependence_ser not in installed_ser_all:
                lost_ser.append(dependence_ser)
        return lost_ser

    def check_dependence(self, dependence_dc, app_dc, app_data):
        """
        查询依赖初次筛选。仅对照应用商店实例，不对照具体实例依赖,并追加参数
        """
        if self.error:
            return
        # 查询当前所有服务的name:version,过滤状态异常的服务
        ser_name_version = Service.objects.filter(service_status__in=range(0, 5)).values_list(
            "service__app_name", "service__app_version")
        installed_ser = []
        for ser in ser_name_version:
            installed_ser.append(f"{ser[0]}:{ser[1].split('.')[0]}")

        for info in app_data:
            lost_ser_set = set()
            if info.get("child") and list(info["child"].values())[0]:
                for app in list(info["child"].values())[0]:
                    app_key = f"{app['name']}:{app['version']}"
                    lost_ser = self.check_dependence_one(dependence_dc.get(app_key), installed_ser)
                    lost_ser_set.update(set(lost_ser))
                    has_install_app_args = dict(zip(self.need_key, app_dc.get(app_key))) if app_dc.get(
                        app_key) else dict(zip(self.need_key, [""] * len(self.need_key)))
                    app.update(has_install_app_args)
            else:
                app_key = f'{info.get("name", "")}:{info.get("version", ["0"])[0]}'
                lost_ser = self.check_dependence_one(dependence_dc.get(app_key), installed_ser)
                lost_ser_set.update(set(lost_ser))
                has_install_app_args = dict(zip(self.need_key, app_dc.get(app_key))) if app_dc.get(
                    app_key) else dict(zip(self.need_key, [""] * len(self.need_key)))
                info.update(has_install_app_args)
            if lost_ser_set:
                info.update({"error": f'缺失依赖:{",".join(list(lost_ser_set))}'})
                self.error = True

    @staticmethod
    def explain_json(text):
        if text:
            return json.loads(text)
        return []

    @classmethod
    def gets_app_list(cls):
        """
        获取app列表信息
        """
        app_ls = ApplicationHub.objects.all(). \
            values_list("app_name", "app_version", "app_install_args",
                        "app_port", "app_dependence")
        app_dc = {}
        dependence_dc = {}
        for app in app_ls:
            app_install_port = {}
            for install in cls.explain_json(app[2]):
                app_install_port[install.get('key')] = install.get('default')
            for port in cls.explain_json(app[3]):
                app_install_port[port.get('key')] = port.get('default')
            for key in cls.need_key:
                app_install_port.setdefault(key, "")
            app_dc[f"{app[0]}:{app[1]}"] = itemgetter(*cls.need_key)(app_install_port)
            dependence_dc[f"{app[0]}:{app[1]}"] = cls.explain_json(app[4])
        return app_dc, dependence_dc

    def create(self, request, *args, **kwargs):
        if not hasattr(self, "error"):
            setattr(self, "error", False)
        app_data = self.request.data.get("data", [])
        # 查询是否勾选想通服务多版本情况
        self.check_repeat(app_data)
        # 查询安装参数及依赖
        app_dc, dependence_dc = self.gets_app_list()
        # 检查依赖是否存在
        self.check_dependence(dependence_dc, app_dc, app_data)
        res_dc = {"service": app_data, "is_continue": False if self.error else True}
        hosts_info = Host.objects.filter(
            host_agent=Host.AGENT_RUNNING).values_list("ip", "agent_dir")
        res_dc["ips"] = dict(hosts_info)
        return Response(res_dc)


class AppConfCheckView(GenericViewSet, CreateModelMixin):
    queryset = ApplicationHub.objects.all()
    serializer_class = AppListSerializer
    post_description = "校验列表问题"

    def create(self, request, *args, **kwargs):
        """
        传uuid和不传uuid
        """
        app_data = self.request.data.get("data")
        if not app_data.get("uuid"):
            if not app_data.pop("is_continue"):
                raise OperateError("存在不允许继续纳管的服务")
            app_data = ConfCheck(app_data).run()
        else:
            app_data = ManagerService(app_data).run()
        return Response(app_data)
