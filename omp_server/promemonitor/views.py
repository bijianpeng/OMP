# Create your views here.
"""
监控相关视图
"""
# 导入 JSON 处理模块，用于处理 JSON 数据
import json
# 导入日志记录模块，用于记录程序运行信息
import logging
# 导入异常堆栈跟踪模块，用于获取详细的异常信息
import traceback

# 导入 requests 库，用于发送 HTTP 请求
import requests
# 从 Django 核心验证器模块导入邮箱验证器
from django.core.validators import EmailValidator
# 从 Django 数据库模块导入事务处理功能
from django.db import transaction
# 从 Django 数据库模型模块导入 F 对象，用于数据库字段的操作
from django.db.models import F
# 从 Django 快捷工具模块导入 get_object_or_404 函数，用于获取对象或返回 404 错误
from django.shortcuts import get_object_or_404
# 从 Django Filter 库的 REST framework 模块导入 Django 过滤后端
from django_filters.rest_framework import DjangoFilterBackend
# 从 REST framework 装饰器模块导入 action 装饰器，用于自定义视图集动作
from rest_framework.decorators import action
# 从 REST framework 过滤模块导入排序过滤器
from rest_framework.filters import OrderingFilter
# 从 REST framework 混合类模块导入多个混合类，用于快速构建视图集
from rest_framework.mixins import (
    ListModelMixin, CreateModelMixin, DestroyModelMixin, UpdateModelMixin
)
# 从 REST framework 响应模块导入 Response 类，用于返回 HTTP 响应
from rest_framework.response import Response
# 从 REST framework 序列化器模块导入 Serializer 类，用于数据序列化
from rest_framework.serializers import Serializer
# 从 REST framework 视图集模块导入 GenericViewSet 类，用于构建通用视图集
from rest_framework.viewsets import GenericViewSet

# 从数据库模型模块导入多个模型类
from db_models.models import (
    Host, MonitorUrl,
    Alert, Maintain, ApplicationHub, Service, EmailSMTPSetting,
    AlertSendWaySetting, HostThreshold, ServiceThreshold,
    ServiceCustomThreshold, Rule, AlertRule
)
# 从项目设置模块导入自定义阈值服务配置
from omp_server.settings import CUSTOM_THRESHOLD_SERVICES
# 从 promemonitor 模块导入 Grafana URL 相关功能
from promemonitor import grafana_url
# 从 promemonitor 告警工具模块导入多个工具函数
from promemonitor.alert_util import utc_to_local, get_monitor_url, get_log_url
# 从 promemonitor 过滤模块导入多个过滤器类
from promemonitor.promemonitor_filters import AlertFilter, MyTimeFilter, \
    QuotaFilter
# 从 promemonitor 序列化器模块导入多个序列化器类
from promemonitor.promemonitor_serializers import (
    MonitorUrlSerializer, ListAlertSerializer, UpdateAlertSerializer,
    MaintainSerializer, MonitorAgentRestartSerializer,
    ReceiveAlertSerializer, RuleSerializer, QuotaSerializer
)
# 从 promemonitor 模块导入 Prometheus 类
from promemonitor.prometheus import Prometheus
# 从工具通用异常模块导入操作错误异常类
from utils.common.exceptions import OperateError
# 从工具中间件模块导入环境上下文获取函数
from utils.middleware_handler import get_request_env
# 从工具通用分页模块导入分页器类
from utils.common.paginations import PageNumberPager
# 从工具解析配置模块导入 Prometheus 认证信息
from utils.parse_config import PROMETHEUS_AUTH
# 从 promemonitor 模块导入 Prometheus 工具类
from promemonitor.prometheus_utils import PrometheusUtils

# 获取名为 'server' 的日志记录器
logger = logging.getLogger('server')


class MonitorUrlViewSet(ListModelMixin, CreateModelMixin, GenericViewSet):
    """
        list:
        查询监控地址列表

        create:
        创建一批监控配置

        multiple_update:
        更新一个或多个监控配置一个或多个字段
    """
    # 指定序列化器类，用于监控地址数据的序列化和反序列化
    serializer_class = MonitorUrlSerializer
    # 指定查询集，获取所有的监控地址对象
    queryset = MonitorUrl.objects.all()
    # GET 请求的描述信息
    get_description = "查询监控地址配置"
    # PATCH 请求的描述信息
    patch_description = "修改监控地址配置"

    def get_serializer(self, *args, **kwargs):
        """
        根据请求数据的类型，动态设置序列化器是否处理多条数据。

        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 序列化器实例
        """
        # 获取序列化器类
        serializer_class = self.get_serializer_class()
        # 设置序列化器的上下文
        kwargs.setdefault('context', self.get_serializer_context())
        if self.request:
            # 若请求数据中的 'data' 字段为列表，使用多对象序列化
            if isinstance(self.request.data.get("data"), list):
                return serializer_class(many=True, *args, **kwargs)
            return serializer_class(*args, **kwargs)
        else:
            return serializer_class(*args, **kwargs)

    @action(methods=['patch'], detail=False)
    def multiple_update(self, request, *args, **kwargs):
        """
        批量更新监控配置。

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含更新后数据的响应
        """
        # 从关键字参数中弹出 partial 参数，默认为 True，表示部分更新
        partial = kwargs.pop('partial', True)
        instances = []
        # 遍历请求数据中的每个监控配置项
        for item in request.data.get('data'):
            # 根据 id 获取监控地址对象，若不存在则返回 404 错误
            instance = get_object_or_404(MonitorUrl, id=int(item['id']))
            # 获取序列化器实例，对监控地址对象进行更新
            serializer = super().get_serializer(instance, data=item,
                                                partial=partial)
            # 验证序列化器数据，若验证失败则抛出异常
            serializer.is_valid(raise_exception=True)
            # 保存更新后的数据
            serializer.save()
            instances.append(serializer.data)
        return Response(instances)


class GrafanaUrlViewSet(ListModelMixin, GenericViewSet):
    """
        list:
        查询异常清单列表
    """
    # 指定查询集，获取所有的监控地址对象
    queryset = MonitorUrl.objects.all()

    def list(self, request, *args, **kwargs):
        """
        获取异常清单列表数据（按当前环境过滤，spec §6.2）。

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含异常清单列表数据的响应
        """
        # 将请求查询参数转换为字典
        params = request.query_params.dict()
        # 从参数中弹出 'asc' 参数，默认为 '0'
        asc = params.pop('asc', '0')
        # 根据 'asc' 参数的值确定排序顺序
        asc = True if asc == '0' else False
        # 从参数中弹出 'ordering' 参数，默认为 'date'
        ordering = params.pop('ordering', 'date')
        # 异常清单按当前环境上下文过滤（主机/服务基准列表限本环境）
        env = get_request_env(request)
        # 调用 grafana_url 模块的函数解析 Prometheus 数据
        current = grafana_url.explain_prometheus(params, env=env)
        if current == "error":
            # 若获取数据失败，抛出操作错误异常
            raise OperateError("prometheus获取数据失败，请检查prometheus状态")
        # 对获取的数据进行排序
        prometheus_info = sorted(
            current, key=lambda e: e.__getitem__(ordering), reverse=asc)
        # prometheus_json = json.dumps(prometheus_info, ensure_ascii=False)
        return Response(prometheus_info)


class ListAlertViewSet(ListModelMixin, GenericViewSet):
    """
    获取告警记录列表视图类
    """
    # 指定序列化器类，用于告警记录数据的序列化和反序列化
    serializer_class = ListAlertSerializer
    # 指定查询集，获取所有告警记录对象，并按创建时间倒序排序
    queryset = Alert.objects.all().order_by("-create_time")  # 分页，过滤，排序
    # 指定分页器类
    pagination_class = PageNumberPager
    # 指定过滤后端
    filter_backends = (
        DjangoFilterBackend,
        OrderingFilter,
        MyTimeFilter,
    )
    # 指定过滤器类
    filter_class = AlertFilter
    # 指定排序字段
    ordering_fields = ("alert_host_ip", "alert_instance_name", "alert_time")

    def get_queryset(self):
        """
        告警列表按当前环境上下文过滤（spec §6.2：告警随入库环境隔离）。

        基于类属性 queryset（模块导入期构建）做过滤，保持与原
        filter_backends 的兼容。

        :return: 当前环境的告警记录查询集，按创建时间倒序排序
        """
        env = get_request_env(self.request)
        return self.queryset.filter(env=env)


class UpdateAlertViewSet(CreateModelMixin, GenericViewSet):
    """
    更新告警记录视图类
    """
    # 指定序列化器类，用于告警记录数据的序列化和反序列化
    serializer_class = UpdateAlertSerializer
    # 指定查询集，获取所有告警记录对象，并按 id 排序
    queryset = Alert.objects.all().order_by('id')
    # POST 请求的描述信息
    post_description = "更新告警记录（已读/未读）"


class MaintainViewSet(GenericViewSet, CreateModelMixin, ListModelMixin):
    """
    create:
    全局进入 / 退出维护模式
    """
    # 指定序列化器类，用于维护对象数据的序列化和反序列化
    serializer_class = MaintainSerializer
    # POST 请求的描述信息
    post_description = "更新全局维护状态"

    def get_queryset(self):
        """
        获取当前环境的维护记录（matcher 值为环境 code，spec §6.4）。

        :return: 当前环境的维护对象查询集
        """
        env = get_request_env(self.request)
        return Maintain.objects.filter(
            matcher_name='env', matcher_value=env.code)

    def create(self, request, *args, **kwargs):
        """
        进入 / 退出当前环境的维护模式。

        matcher 强制取当前环境 code（客户端传入值不生效），保证
        多环境维护互相隔离（spec §6.4：维护模式按 request.env.code
        下发 matcher）。

        :param request: 请求对象
        :return: 维护模式操作结果
        """
        env = get_request_env(request)
        if hasattr(request.data, "copy"):
            # QueryDict 等不可变数据先拷贝，再覆盖环境相关 matcher
            request._full_data = request.data.copy()
        request._full_data["matcher_name"] = "env"
        request._full_data["matcher_value"] = env.code
        return super(MaintainViewSet, self).create(
            request, *args, **kwargs)


class ReceiveAlertViewSet(GenericViewSet, CreateModelMixin):
    """
    接收alertmanager发送过来的告警消息后解析入库
    """
    # 指定查询集为 None
    queryset = None
    # 指定序列化器类，用于告警消息数据的序列化和反序列化
    serializer_class = ReceiveAlertSerializer
    # POST 请求的描述信息
    post_description = "接收alertmanager告警信息"
    # 关闭认证类
    authentication_classes = ()
    # 关闭权限类
    permission_classes = ()
    # webhook 回调无用户上下文：跳过环境授权校验（spec §6.2），
    # 告警所属环境由 labels env 标签 / 主机 IP 解析，不取请求上下文
    env_exempt = True


class MonitorAgentRestartView(GenericViewSet, CreateModelMixin):
    """
        create:
        重启监控Agent接口
    """
    # 指定查询集，获取未被删除的主机对象
    queryset = Host.objects.filter(is_deleted=False)
    # 指定序列化器类，用于监控 Agent 重启数据的序列化和反序列化
    serializer_class = MonitorAgentRestartSerializer
    # POST 请求的描述信息
    post_description = "重启监控Agent"


class InstanceNameListView(GenericViewSet, ListModelMixin):
    """
    返回主机和服务实例名列表
    """
    # POST 请求的描述信息
    post_description = "返回主机和服务实例名列表"

    def list(self, request, *args, **kwargs):
        """
        获取主机和服务实例名列表。

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含主机和服务实例名列表的响应
        """
        alert_instance_name_list = list()
        # 获取所有主机的实例名列表
        host_instance_name_list = list(Host.objects.all().values_list(
            'instance_name', flat=True))
        # 待应用模型完善后获取服务实例名列表
        service_instance_name_list = []  # TODO 待应用模型完善
        alert_instance_name_list.append(host_instance_name_list)
        alert_instance_name_list.append(service_instance_name_list)
        return Response(alert_instance_name_list)


class InstrumentPanelView(GenericViewSet, ListModelMixin):
    """
    返回仪表盘所需数据
    """
    # GET 请求的描述信息
    get_description = "查询仪表盘数据"

    @staticmethod
    def get_prometheus_alerts():
        """
        请求prometheus alerts接口返回告警内容

        :return: 包含请求结果和告警数据的元组
        """
        # 获取名为 'prometheus' 的监控地址对象
        mu = MonitorUrl.objects.filter(name="prometheus").first()
        # 获取 Prometheus 的监控地址，若不存在则使用默认地址
        prometheus_url = mu.monitor_url if mu else "127.0.0.1:19011"
        # 获取 Prometheus 认证信息
        prometheus_auth = (PROMETHEUS_AUTH.get(
            "username", "omp"), PROMETHEUS_AUTH.get("plaintext_password", ""))
        try:
            # 构建 Prometheus 告警接口的 URL
            prometheus_alerts_url = f"http://{prometheus_url}/api/v1/alerts"
            # 发送 GET 请求获取告警数据
            response = requests.get(prometheus_alerts_url, headers={
            }, data="", auth=prometheus_auth)
            return True, json.loads(response.text)
        except Exception as e:
            # 若请求失败，记录错误信息并返回失败结果
            logger.error("prometheus请求alerts失败：" + str(e))
            return False, "Failed"

    def get_exc_serializer_info(self, env):
        """
        获取仪表盘所需的异常信息并进行序列化处理。

        :param env: 当前请求环境（Env 实例），各维度计数与明细均按环境过滤
        :return: 包含各类型信息的字典
        """
        # 初始化各类型信息字典
        host_info_dict = {}
        database_info_dict = {}
        service_info_dict = {}
        component_info_dict = {}
        third_info_dict = {}

        # 初始化各类型信息列表
        host_info_list = []
        database_info_list = []
        service_info_list = []
        component_info_list = []
        third_info_list = []
        host_ip_list = []

        # 获取当前环境所有主机的 IP 和实例名信息
        host_list = Host.objects.filter(env=env).values("ip", "instance_name")
        host_ip_list = [host.get("ip") for host in host_list]
        # 定义忽略的服务状态列表
        ignore_status_list = [Service.SERVICE_STATUS_NORMAL,
                              Service.SERVICE_STATUS_STARTING,
                              Service.SERVICE_STATUS_STOPPING,
                              Service.SERVICE_STATUS_RESTARTING,
                              Service.SERVICE_STATUS_STOP]
        # 获取当前环境数据库服务列表
        database_list = Service.objects.filter(
            env=env).filter(
            service__app_type=ApplicationHub.APP_TYPE_COMPONENT).filter(
            service__app_labels__label_name__contains="数据库").filter(
            service_status__in=ignore_status_list).filter(
            service__is_base_env=False)
        # 获取当前环境服务列表
        service_list = Service.objects.filter(
            env=env).filter(
            service__app_type=ApplicationHub.APP_TYPE_SERVICE).filter(
            service_status__in=ignore_status_list).filter(
            service__is_base_env=False).filter(
            service_controllers__start__isnull=False)
        # 获取当前环境组件列表
        component_list = Service.objects.filter(
            env=env).filter(
            service__app_type=ApplicationHub.APP_TYPE_COMPONENT).filter(
            service_status__in=ignore_status_list).filter(
            service__is_base_env=False)
        # 暂未实现第三方信息获取
        # third_info_all = None  # TODO 暂为空

        # 统计各类型信息的总数
        host_info_all_count = len(host_list)
        database_info_all_count = len(database_list)
        service_info_all_count = len(service_list)
        component_info_all_count = len(component_list)
        third_info_all_count = 0  # TODO 暂为空

        # 初始化各类型异常信息数量
        # host_info_exc_count = 0
        database_info_exc_count = 0
        service_info_exc_count = 0
        component_info_exc_count = 0
        third_info_exc_count = 0

        # 初始化各类型未监控信息数量
        host_info_no_monitor_count = 0
        database_info_no_monitor_count = 0
        service_info_no_monitor_count = 0
        component_info_no_monitor_count = 0
        third_info_no_monitor_count = 0

        # 获取 Prometheus 告警信息
        flag, alert_data = self.get_prometheus_alerts()
        # 初始化各类型错误列表
        error_database_list = list()
        error_service_list = list()
        error_component_list = list()
        error_host_list = list()
        if flag:
            # 获取告警数据中的告警列表
            alerts = alert_data.get('data').get('alerts')
            for ele in alerts:
                if not isinstance(ele, dict):
                    continue
                # 忽略已解决的告警或不在主机 IP 列表中的告警
                if ele.get("status") == "resolved" or ele.get(
                        "state") == "resolved" or ele.get("labels").get("instance") not in host_ip_list:
                    continue
                # 获取告警的 IP 地址
                _ip = ele.get("labels").get("instance", "")
                # 获取告警的实例名
                service_instance_str = ele.get("labels").get("instance_name", "")
                if len(service_instance_str) < 1:
                    # 若实例名不存在，根据规则生成实例名
                    app_name_str = ele.get("labels").get("app") if ele.get("labels").get("app") else \
                        ele.get("labels").get("job", "").split("Exporter")[0]
                    service_instance_str = f"{app_name_str}-{_ip.split('.')[2]}-{_ip.split('.')[3]}"
                if len(service_instance_str) < 1:
                    continue
                # 统一用 classify_alert 判定告警类型，与异常清单（grafana_url）保持口径一致，
                # 避免 job=nodeExporter 但 instance_name 为组件实例名时被双算（host+component）
                # 或在异常清单中漏算（被判死为 host）
                alert_labels = ele.get("labels") or {}
                alert_type = grafana_url.classify_alert(
                    alert_labels, database_list, service_list, component_list)
                # 监控/日志 URL：主机告警走 host 面板（instance_name=node），
                # 其余走 service 面板
                if alert_type == "host":
                    url_type, url_instance_name = "host", "node"
                else:
                    url_type = "service"
                    url_instance_name = alert_labels.get("instance_name", "")
                # 构建告警信息字典
                ele_dict = {
                    "ip": _ip,
                    "instance_name": service_instance_str,
                    "alertname": alert_labels.get("alertname"),
                    "severity": alert_labels.get("severity"),
                    "date": utc_to_local(ele.get("activeAt")),
                    "describe": ele.get("annotations").get("description"),
                    # env 传环境 code，跳转 URL 拼参时追加 var-env={code}
                    # （spec 决策 #22，URL 拼接侧由 alert_util 统一实现）
                    "monitor_url": get_monitor_url([{
                        "ip": alert_labels.get("instance"),
                        "type": url_type,
                        "instance_name": url_instance_name,
                        "env": env.code
                    }]),
                    "log_url": get_log_url([{
                        "ip": alert_labels.get("instance"),
                        "type": url_type,
                        "instance_name": url_instance_name,
                        "env": env.code
                    }])
                }
                if alert_type == "host":
                    # 主机告警
                    host_info_list.append(ele_dict)
                    error_host_list.append(alert_labels.get("instance"))
                elif alert_type == "database":
                    # 数据库告警：同时计入组件（数据库本身也是组件）
                    error_database_list.append(service_instance_str)
                    database_info_list.append(ele_dict)
                    error_component_list.append(service_instance_str)
                    component_info_list.append(ele_dict)
                elif alert_type == "service":
                    # 服务告警
                    error_service_list.append(service_instance_str)
                    service_info_list.append(ele_dict)
                elif alert_type == "component":
                    # 组件告警
                    error_component_list.append(service_instance_str)
                    component_info_list.append(ele_dict)
                else:
                    continue
        # 处理主机告警信息，去重
        for index, hil in enumerate(host_info_list):
            if hil.get("severity") == "warning":
                for i, h in enumerate(host_info_list):
                    if index == i:
                        continue
                    if hil.get("ip") == h.get("ip") and hil.get(
                            "alertname") == h.get("alertname") and h.get(
                        "severity") == "critical":
                        host_info_list.pop(index)
                        break
            elif hil.get("severity") == "critical":
                for i, h in enumerate(host_info_list):
                    if index == i:
                        continue
                    if hil.get("ip") == h.get("ip") and hil.get(
                            "alertname") == h.get("alertname") and h.get(
                        "severity") == "warning":
                        host_info_list.pop(i)
                        break
        # 获取所有主机的监控目标
        _, host_targets = Prometheus().get_all_host_targets()
        for host in host_list:
            if host.get("ip") in error_host_list:
                continue
            # 构建主机信息字典
            host_dict = {
                "ip": host.get("ip"), "instance_name": host.get("instance_name"),
                "severity": "normal"}
            if host.get("ip") not in host_targets:
                # 若主机未被监控，更新状态
                host_dict = {
                    "ip": host.get("ip"), "instance_name": host.get("instance_name"),
                    "severity": "unmonitored"}
            host_info_list.append(host_dict)

        # 获取所有服务的监控目标
        _, service_targets = Prometheus().get_all_service_targets()
        for database in database_list:
            if database.service_instance_name in error_database_list:
                continue
            # 构建数据库服务信息字典
            database_dict = {"ip": database.ip,
                             "instance_name": database.service_instance_name,
                             "app_name": database.service.app_name,
                             "severity": "normal"}
            database_ip_instance_name_str = \
                f"{database.ip}_{database.service_instance_name}"
            if database_ip_instance_name_str not in service_targets:
                # 若数据库服务未被监控，更新状态
                database_dict = {"ip": database.ip,
                                 "instance_name":
                                     database.service_instance_name,
                                 "app_name": database.service.app_name,
                                 "severity": "unmonitored"}
            database_info_list.append(database_dict)
        for service in service_list:
            if service.service_instance_name in error_service_list:
                continue
            # 构建服务信息字典
            service_dict = {"ip": service.ip,
                            "instance_name": service.service_instance_name,
                            "app_name": service.service.app_name,
                            "severity": "normal"}
            service_ip_instance_name_str = f"{service.ip}_" \
                                           f"{service.service_instance_name}"
            if service_ip_instance_name_str not in service_targets:
                # 若服务未被监控，更新状态
                service_dict = {"ip": service.ip,
                                "instance_name": service.service_instance_name,
                                "app_name": service.service.app_name,
                                "severity": "unmonitored"}
            service_info_list.append(service_dict)
        for component in component_list:
            if component.service_instance_name in error_component_list:
                continue
            # 构建组件信息字典
            component_dict = {"ip": component.ip,
                              "instance_name": component.service_instance_name,
                              "app_name": component.service.app_name,
                              "severity": "normal"}
            component_ip_instance_name_str = f"{component.ip}_" \
                                             f"{component.service_instance_name}"
            if component_ip_instance_name_str not in service_targets:
                # 若组件未被监控，更新状态
                component_dict = {"ip": component.ip,
                                  "instance_name":
                                      component.service_instance_name,
                                  "app_name": component.service.app_name,
                                  "severity": "unmonitored"}
            component_info_list.append(component_dict)

        # 统计各类型异常信息数量
        host_info_exc_count = len(set(error_host_list))
        database_info_exc_count = len(set(error_database_list))
        service_info_exc_count = len(set(error_service_list))
        component_info_exc_count = len(set(error_component_list))

        # 更新各类型信息字典
        host_info_dict.update({
            "host_info_all_count": host_info_all_count,
            "host_info_exc_count": host_info_exc_count,
            "host_info_no_monitor_count": host_info_no_monitor_count,
            "host_info_list": host_info_list
        })
        database_info_dict.update({
            "database_info_all_count": database_info_all_count,
            "database_info_exc_count": database_info_exc_count,
            "database_info_no_monitor_count": database_info_no_monitor_count,
            "database_info_list": database_info_list
        })
        service_info_dict.update({
            "service_info_all_count": service_info_all_count,
            "service_info_exc_count": service_info_exc_count,
            "service_info_no_monitor_count": service_info_no_monitor_count,
            "service_info_list": service_info_list
        })
        component_info_dict.update({
            "component_info_all_count": component_info_all_count,
            "component_info_exc_count": component_info_exc_count,
            "component_info_no_monitor_count": component_info_no_monitor_count,
            "component_info_list": component_info_list
        })
        third_info_dict.update({
            "third_info_all_count": third_info_all_count,
            "third_info_exc_count": third_info_exc_count,
            "third_info_no_monitor_count": third_info_no_monitor_count,
            "third_info_list": third_info_list
        })
        # 构建序列化信息字典
        serializer_info = {
            "host": host_info_dict,
            "database": database_info_dict,
            "service": service_info_dict,
            "component": component_info_dict,
            "third": third_info_dict,
        }
        return serializer_info

    def list(self, request, *args, **kwargs):
        """
        获取仪表盘所需数据并返回响应。

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含仪表盘数据的响应
        """
        # 各维度（host/service/component/database）均按当前环境统计
        env = get_request_env(request)
        result = self.get_exc_serializer_info(env)
        return Response(result)


class GetSendEmailConfig(GenericViewSet, ListModelMixin):
    """
    获取邮件发送配置
    """
    # GET 请求的描述信息
    get_description = "获取邮件发送配置"

    def list(self, request, *args, **kwargs):
        """
        获取邮件发送配置信息。

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含邮件发送配置信息的响应
        """
        # 获取第一个邮件 SMTP 设置对象
        email_setting = EmailSMTPSetting.objects.first()
        if email_setting:
            return Response(data=email_setting.get_dict())
        return Response({})


class UpdateSendEmailConfig(GenericViewSet, CreateModelMixin):
    """
    更新邮件发送配置
    """
    # POST 请求的描述信息
    post_description = "更新邮件发送配置"

    # 指定序列化器类
    serializer_class = Serializer

    def create(self, request, *args, **kwargs):
        """
        更新邮件发送配置。

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含更新结果的响应
        """
        # 获取请求数据中的邮件服务器地址
        email_host = request.data.get("host")
        if not email_host:
            return Response(data={"code": 1, "message": "请填写SMTP邮件服务器地址！"})
        # 获取请求数据中的邮件服务器端口
        email_port = request.data.get("port")
        if not email_port or not isinstance(email_port, int):
            return Response(
                data={"code": 1, "message": "请检查所填的SMTP邮件服务器端口是否正确！"})
        # 获取请求数据中的邮件服务器发件箱
        email_host_user = request.data.get("username")
        if not email_host_user:
            return Response(data={"code": 1, "message": "请填写SMTP邮件服务器发件箱！"})
        try:
            # 验证邮件服务器发件箱格式
            EmailValidator()(email_host_user)
        except Exception as e:
            message = "SMTP邮件服务器发件箱格式错误！"
            logger.error(f"{message} 错误信息：{str(e)}")
            return Response(data={"code": 1, "message": message})
        # 获取请求数据中的邮件服务器发件箱密码
        email_host_password = request.data.get("password")
        if not email_host_password:
            return Response(data={"code": 1, "message": "填写SMTP邮件服务器发件箱格式错误！"})
        try:
            # 删除所有邮件 SMTP 设置对象
            EmailSMTPSetting.objects.all().delete()
            # 创建新的邮件 SMTP 设置对象
            email_setting = EmailSMTPSetting.objects.create(
                email_host=email_host,
                email_port=email_port,
                email_host_user=email_host_user,
                email_host_password=email_host_password
            )
        except Exception as e:
            message = "修改email邮箱服务器信息出错！"
            logger.error(f"{message} 详细信息：{str(e)}")
            return Response(data={"code": 1, "message": message})
        # 更新邮件设置配置
        state, email_url = email_setting.update_setting_config()
        if not state:
            return Response(data={"code": 1, "message": "同步到Alert Manage失败！"})
        return Response({})


class GetSendAlertSettingView(GenericViewSet, ListModelMixin):
    """
    获取监控邮箱收件配置
    """
    # GET 请求的描述信息
    get_description = "获取监控邮箱收件配置"

    def list(self, request, *args, **kwargs):
        """
        获取监控邮箱收件配置信息。

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含监控邮箱收件配置信息的响应
        """
        # 获取当前请求环境上下文
        env = get_request_env(request)
        # 构建过滤条件字典
        filter_kwargs = dict(env=env)
        # 从请求查询参数中获取方式名称
        way_name = request.GET.get("way_name")
        if way_name:
            filter_kwargs["way_name"] = way_name
        # 根据过滤条件获取告警发送方式设置对象列表
        objs = AlertSendWaySetting.objects.filter(**filter_kwargs)
        data = dict()
        for obj in objs:
            data.update({obj.way_name: obj.get_self_dict()})
        if "email" not in data:
            # 若数据中不包含 'email' 信息，获取默认的邮件配置信息
            # （v1.5 兼容分支保留：回填已有配置并向当前环境落库）
            data["email"] = AlertSendWaySetting.get_v1_5_email_dict(env.id)
        return Response(data=data)


class UpdateSendAlertSettingView(GenericViewSet, CreateModelMixin):
    """更新监控邮箱收件配置"""
    # POST 请求的描述信息
    post_description = "更新监控邮箱收件配置"

    # 指定序列化器类
    serializer_class = Serializer

    def create(self, request, *args, **kwargs):
        """
        更新监控邮箱收件配置。

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含更新结果的响应
        """
        # 获取当前请求环境上下文（body 中冗余 env_id 不再读取）
        env = get_request_env(request)
        # 获取或创建当前环境的告警发送方式设置对象
        alert_setting, _ = AlertSendWaySetting.objects.get_or_create(
            env=env, way_name="email"
        )
        # 从请求数据中获取是否启用标志，默认为 False
        used = request.data.get("used", False)
        # 从请求数据中获取收件箱列表
        emails = request.data.get("server_url", "")
        if emails:
            for email in emails.split(","):
                try:
                    # 验证收件箱格式
                    EmailValidator()(email)
                except Exception as e:
                    message = f"收件箱{email}格式错误！"
                    logger.error(f"{message} 错误信息：{str(e)}")
                    return Response(data={"code": 1, "message": message})
        # 更新当前环境的邮件配置（不波及其它环境）
        alert_setting.used = bool(used)
        alert_setting.server_url = emails
        alert_setting.save()
        # 获取第一个邮件 SMTP 设置对象
        email_setting = EmailSMTPSetting.objects.first()
        if not email_setting:
            return Response(
                data={"code": 1, "message": "邮箱SMTP服务器未配置，配置后才可发送告警邮件！"})
        # 更新邮件设置配置
        state, email_url = email_setting.update_setting_config()
        if not state:
            return Response(data={"code": 1,
                                  "message": "同步到Alert Manage失败！请确保Alert "
                                             "Manage可用"})
        return Response({})


class HostThresholdView(GenericViewSet, ListModelMixin, CreateModelMixin):
    """
    读写主机阈值
    """

    # GET 请求的描述信息
    get_description = "读取主机阈值设置"
    # POST 请求的描述信息
    post_description = "更新主机阈值设置"

    # 指定序列化器类
    serializer_class = Serializer

    def list(self, request, *args, **kwargs):
        """
        获取主机监控指标项设置

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含主机监控指标项设置信息的响应
        """
        # 获取当前请求环境上下文
        env = get_request_env(request)
        if not HostThreshold.objects.filter(env=env).exists():
            return Response(data={"code": 1, "message": f"env {env.id}错误"})
        # 获取当前环境和指标类型的主机阈值信息
        host_thresholds = HostThreshold.objects.filter(
            env=env,
            index_type__in=["cpu_used", "memory_used", "disk_root_used",
                            "disk_data_used"]
        ).annotate(
            value=F("condition_value"), level=F("alert_level")
        ).order_by("index_type", "level").values(
            "index_type", "condition", "value", "level")
        data = {
            "cpu_used": [],
            "memory_used": [],
            "disk_root_used": [],
            "disk_data_used": []
        }
        for host_threshold in host_thresholds:
            data[host_threshold.get("index_type")].append(host_threshold)
        return Response(data=data)

    def create(self, request, *args, **kwargs):
        """
        更新主机指标项到自监控平台

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含更新结果的响应
        """
        try:
            logger.info(f"主机监控指标更新接口获取到的参数为: {request.data}")
            # 获取当前请求环境上下文（body 中冗余 env_id 不再读取）
            env = get_request_env(request)
            # 从请求数据中获取要更新的数据
            update_data = request.data.get("update_data", {})
            if not update_data:
                return Response(data={"code": 1, "message": "无法正确解析到要更新的数据!"})
            # 同步阈值至prometheus主机告警规则文件中，并做配置检查
            # if not check_prometheus():
            #     return Response(1, "无法连接到prometheus，更改阈值失败！")
            _obj_lst = list()
            hosts_list = list()
            for key, value in update_data.items():
                for item in value:
                    if not item["condition"] or not item["value"] or not item[
                        "level"]:
                        continue
                    # 创建主机阈值对象
                    _obj = HostThreshold()
                    _obj.index_type = key
                    _obj.condition = item["condition"]
                    _obj.condition_value = item["value"]
                    _obj.alert_level = item["level"]
                    _obj.env = env
                    _obj_lst.append(_obj)
                    hosts_list.append({
                        'index_type': key,
                        'condition': item["condition"],
                        'condition_value': item["value"],
                        'alert_level': item["level"]
                    })
            with transaction.atomic():
                # 删除当前环境的所有主机阈值对象
                HostThreshold.objects.filter(env=env).delete()
                # 批量创建主机阈值对象
                HostThreshold.objects.bulk_create(_obj_lst)

            from promemonitor.prometheus_utils import PrometheusUtils
            # 创建 Prometheus 工具类实例
            prometheus_util = PrometheusUtils()
            # 更新当前环境的主机阈值（env 传环境 code，spec §6.4）
            prometheus_util.update_host_threshold(
                env=env.code, env_id=env.id)
            # 获取当前环境主机的数据文件夹列表（终审建议项 1：
            # 数据分区规则按环境收口，不再混入其它环境主机的分区）
            data_disk_dir_list = list(Host.objects.filter(
                env=env).values_list(
                "data_folder", flat=True).distinct())
            for ele in data_disk_dir_list:
                # 更新节点数据规则（env 传环境 code，与文件名约定一致）
                prometheus_util.update_node_data_rule(ele, env.code)

            return Response({})
        except Exception as e:
            logger.error(f"更新主机相关阈值过程中出错: {traceback.format_exc()}")
            return Response(
                data={"code": 1, "message": f"更新主机相关阈值过程中出错: {str(e)}!"})


class ServiceThresholdView(GenericViewSet, ListModelMixin, CreateModelMixin):
    """
    读写服务阈值
    """

    # GET 请求的描述信息
    get_description = "读取服务阈值设置"
    # POST 请求的描述信息
    post_description = "更新服务阈值设置"

    # 指定序列化器类
    serializer_class = Serializer

    def list(self, request, *args, **kwargs):
        """
        获取服务阈值监控指标项设置

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含服务阈值监控指标项设置信息的响应
        """
        # 获取当前请求环境上下文
        env = get_request_env(request)
        if not ServiceThreshold.objects.filter(env=env).exists():
            return Response(data={"code": 1, "message": f"env {env.id}错误"})
        # 获取当前环境和指标类型的服务阈值信息
        service_thresholds = ServiceThreshold.objects.filter(
            env=env,
            index_type__in=["service_active", "service_cpu_used",
                            "service_memory_used"]
        ).annotate(
            value=F("condition_value"), level=F("alert_level")
        ).order_by("index_type", "level").values(
            "index_type", "condition", "value", "level")
        data = {
            "service_active": [],
            "service_cpu_used": [],
            "service_memory_used": [],
        }
        for service_threshold in service_thresholds:
            data[service_threshold.get("index_type")].append(service_threshold)
        return Response(data=data)

    def create(self, request, *args, **kwargs):
        """
        更新服务阈值监控指标项设置

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含更新结果的响应
        """
        try:
            logger.info(f"服务监控指标更新接口获取到的参数为: {request.data}")
            # 获取当前请求环境上下文（body 中冗余 env_id 不再读取）
            env = get_request_env(request)
            # 从请求数据中获取要更新的数据
            update_data = request.data.get("update_data", {})
            if not update_data:
                return Response(data={"code": 1, "message": "无法正确解析到要更新的数据!"})
            _obj_lst = list()
            services_list = list()
            for key, value in update_data.items():
                for item in value:
                    if not item["condition"] or not item["value"] or not item[
                        "level"]:
                        continue
                    # 创建服务阈值对象
                    _obj = ServiceThreshold()
                    _obj.index_type = key
                    _obj.condition = item["condition"]
                    _obj.condition_value = item["value"]
                    _obj.alert_level = item["level"]
                    _obj.env = env
                    _obj_lst.append(_obj)
                    services_list.append({
                        'index_type': key,
                        'condition': item["condition"],
                        'condition_value': item["value"],
                        'alert_level': item["level"]
                    })
            with transaction.atomic():
                # 删除当前环境的所有服务阈值对象
                ServiceThreshold.objects.filter(env=env).delete()
                # 批量创建服务阈值对象
                ServiceThreshold.objects.bulk_create(_obj_lst)
            return Response({})
        except Exception as e:
            logger.error(f"更新服务相关阈值过程中出错: {traceback.format_exc()}")
            return Response(
                data={"code": 1, "message": f"更新服务相关阈值过程中出错: {str(e)}!"})


class CustomThresholdView(GenericViewSet, ListModelMixin, CreateModelMixin):
    """
    读写自定义服务指标阈值
    """

    # GET 请求的描述信息
    get_description = "读取自定义服务指标阈值设置"
    # POST 请求的描述信息
    post_description = "更新自定义服务指标阈值设置"

    # 指定序列化器类
    serializer_class = Serializer

    def list(self, request, *args, **kwargs):
        """
        暂时只有kafka_consumergroup_lag

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含自定义服务指标阈值设置信息的响应
        """
        # 获取当前请求环境上下文
        env = get_request_env(request)
        # 获取当前环境的自定义服务阈值信息
        service_thresholds = list(
            ServiceCustomThreshold.objects.filter(
                env=env
            ).annotate(
                value=F("condition_value"), level=F("alert_level")
            ).order_by("service_name", "index_type", "level").values(
                "service_name", "index_type", "condition", "value", "level")
        )
        data = dict()
        for service_threshold in service_thresholds:
            # 获取服务名称和指标类型
            service_name = service_threshold.get("service_name", "")
            index_type = service_threshold.get("index_type", "")
            if not service_name or not index_type:
                continue
            # 构建指标类型信息字典
            index_type_info = {
                "condition": service_threshold.get("condition"),
                "index_type": index_type,
                "level": service_threshold.get("level"),
                "value": service_threshold.get("value")
            }
            # 获取服务阈值信息
            threshold_info = data.get(service_name, {})
            if not threshold_info:
                data[service_name] = {index_type: [index_type_info]}
            else:
                index_type_infos = threshold_info.get(index_type)
                if not index_type_infos:
                    threshold_info[index_type] = [index_type_info]
                else:
                    threshold_info[index_type].append(index_type_info)
        return Response(data=data)

    def valid_kafka_kafka_consumergroup_lag(self, value):  # NOQA
        """
        验证 Kafka 消费者组延迟阈值是否有效。

        :param value: 阈值值
        :return: 若有效返回 True，否则返回 False
        """
        if isinstance(value, int):
            return value > 0
        return value.isdigit() and int(value) > 0

    def create(self, request, *args, **kwargs):
        """
        更新服务阈值监控指标项设置

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含更新结果的响应
        """
        try:
            logger.info(f"自定义服务监控指标更新接口获取到的参数为: {request.data}")
            # 从请求数据中获取服务名称
            service_name = request.data.get("service_name", "")
            # 从配置中获取该服务支持的指标类型列表
            index_types = CUSTOM_THRESHOLD_SERVICES.get(service_name)
            if not index_types:
                return Response(data={"code": 1, "message": "暂不支持该服务定制化阈值!"})
            # 从请求数据中获取指标类型
            index_type = request.data.get("index_type", "")
            if not index_type or index_type not in index_types:
                return Response(data={"code": 1, "message": "暂不支持该指标项!"})
            # 从请求数据中获取指标类型信息
            index_type_info = request.data.get("index_type_info", [])
            if not index_type_info:
                return Response(data={"code": 1, "message": "无法正确解析到要更新的数据!"})
            # 获取当前请求环境上下文（body 中冗余 env_id 不再读取，
            # 环境有效性由 EnvContextMiddleware 保证）
            env = get_request_env(request)

            # 后续可能需要同步阈值至prometheus的rules文件中
            # if not check_prometheus():
            #     return Response(1, "无法连接到prometheus，更改阈值失败！")
            _obj_lst = list()
            # 创建阈值
            for index_type_value in index_type_info:
                # 获取条件、级别和值
                condition = index_type_value.get("condition")
                level = index_type_value.get("level")
                value = index_type_value.get("value")
                # 验证阈值值是否有效
                valid = getattr(
                    self, f"valid_{service_name}_{index_type}"
                )(value)
                if not valid:
                    return Response(
                        data={"code": 1, "message": "阈值更新的值不符合要求！"})
                # 创建自定义服务阈值对象
                _obj = ServiceCustomThreshold(
                    env=env,
                    service_name=service_name,
                    index_type=index_type,
                    condition=condition,
                    condition_value=value,
                    alert_level=level
                )
                _obj_lst.append(_obj)
            with transaction.atomic():
                # 删除当前环境、服务名称和指标类型的所有自定义服务阈值对象
                ServiceCustomThreshold.objects.filter(
                    env=env,
                    service_name=service_name,
                    index_type=index_type
                ).delete()
                # 批量创建自定义服务阈值对象
                ServiceCustomThreshold.objects.bulk_create(_obj_lst)
            return Response({})
        except Exception as e:
            logger.error(f"更新服务相关阈值过程中出错: {traceback.format_exc()}")
            return Response(
                data={"code": 1, "message": f"更新服务相关阈值过程中出错: {str(e)}!"})


class QuotaView(ListModelMixin, GenericViewSet, CreateModelMixin, DestroyModelMixin):
    """
    读写自定义服务指标阈值
    """

    # GET 请求的描述信息
    get_description = "读取指标规则"
    # POST 请求的描述信息
    post_description = "更新指标规则"
    # DELETE 请求的描述信息
    delete_description = "删除指标规则"
    # 指定序列化器类
    serializer_class = QuotaSerializer
    # 指定查询集，获取所有告警规则对象，并按创建时间倒序排序
    # （get_queryset 按当前环境过滤）
    # 指定分页器类
    pagination_class = PageNumberPager
    # 指定过滤后端
    filter_backends = (
        DjangoFilterBackend,
        OrderingFilter,
    )
    # 指定过滤器类
    filter_class = QuotaFilter

    def get_queryset(self):
        """
        获取当前环境的告警规则查询集。

        :return: 当前环境的告警规则查询集，按创建时间倒序排序
        """
        env = get_request_env(self.request)
        return AlertRule.objects.filter(
            env=env).order_by("-create_time")

    def create(self, request, *args, **kwargs):
        """
        添加监控指标项
        env = models.ForeignKey(Env, 环境外键，取当前请求环境，不由客户端传入)
        expr = models.TextField("监控指标表达式，报警语法", null=False, blank=False)
        threshold_value = models.FloatField("阈值的数值", null=False, blank=False)
        compare_str = models.CharField("比较符", max_length=64)
        for_time = models.CharField("持续一段时间获取不到信息就触发告警", max_length=64)
        severity = models.CharField("告警级别", max_length=64)
        alert = models.TextField("标题，自定义摘要")
        service = models.CharField("指标所属服务名称", max_length=255)
        status = models.IntegerField("启用状态", default=0)
        quota_type = models.IntegerField("指标的类型", choices=TYPE, default=0)
        labels = models.JSONField("额外指定标签")
        description = models.TextField("描述, 告警指标描述", null=True)

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含创建结果的响应
        """
        # 创建 Prometheus 工具类实例
        p = PrometheusUtils()
        # 比较符映射字典
        compare_str_dict = {
            ">=": "大于或等于",
            ">": "大于",
            "==": "等于",
            "!=": "不等于",
            "<=": "小于或等于",
            "<": "小于"
        }
        try:
            # 获取当前请求环境上下文（body 中冗余 env_id 不再读取）
            env = get_request_env(request)
            # 丢弃客户端传入的 env_id，环境一律取请求上下文
            request.data.pop("env_id", None)
            # 内置指标表达式的 $env$ 占位符用环境 code 替换
            # （spec §6.4：进入监控链路的 env 字符串均为 Env.code）
            env_name = env.code
            logger.info(f"创建指标规则接口获取到的参数为: {request.data}")
            # 从请求数据中获取指标类型
            quota_type = request.data.get("quota_type")
            # 从请求数据中获取比较符
            compare_str = request.data.get("compare_str")
            # 从请求数据中获取告警级别
            severity = request.data.get("severity")
            # 从请求数据中获取阈值数值
            threshold_value = request.data.get("threshold_value")
            # 从请求数据中弹出 ID，默认为 0
            id = request.data.pop("id", 0)
            # 从请求数据中获取监控指标表达式
            expr = request.data.get("expr")
            if quota_type == 0:
                """
                内置指标
                """
                # 从请求数据中弹出内置指标信息
                builtins_quota = request.data.pop("builtins_quota", None)
                # 获取指标名称
                name = builtins_quota.get("name")
                # 获取监控指标表达式
                expr = builtins_quota.get("expr")
                # 获取指标描述
                description = builtins_quota.get("description")
                # 获取中文比较符
                cn_compare = compare_str_dict.get(compare_str)
                # 更新请求数据中的指标名称
                request.data["name"] = name
                # 更新请求数据中的服务名称
                request.data["service"] = builtins_quota.get("service")
                # 更新请求数据中的指标描述
                request.data["description"] = description.replace("$compare_str$", cn_compare).replace(
                    "$threshold_value$", str(threshold_value))
                # 更新请求数据中的监控指标表达式
                request.data["expr"] = expr.replace("$env$", env_name)
                # 获取告警级别
                severity = request.data.get("severity")
            elif quota_type == 1:
                """
                自定义promsql
                """
                pass
            elif quota_type == 2:
                """
                日志监控
                """
                pass
            else:
                return Response(
                    data={"code": 1, "message": f"创建指标规则过程中出错: 未识别的规则类型"})
            if request.data["service"] != "service":
                # 若服务名称不为 'service'，更新标签信息
                request.data["labels"] = {
                    "job": '{}Exporter'.format(request.data["service"]),
                    "severity": severity
                }
            else:
                # 否则，更新标签信息
                request.data["labels"] = {
                    "severity": severity
                }
            # 规则归属环境：一律取当前请求环境
            request.data["env"] = env
            if id != 0:
                if AlertRule.objects.filter(env=env,
                                            expr=request.data["expr"],
                                            severity=severity).exclude(id=id).exists():
                    return Response(data={"code": 1,
                                          "message": f"更新指标规则过程中出错: "
                                                     f"同一指标规则级别重复添加"})
                # 更新目标必须属于当前环境（跨环境 id 视为不存在，
                # 避免规则文件误写入当前环境后 DB 更新 0 行的不一致）
                if not AlertRule.objects.filter(id=id, env=env).exists():
                    return Response(data={"code": 1,
                                          "message": f"更新指标规则过程中出错: "
                                                     f"规则不存在或不属于当前环境"})
                if not p.update_rule_file(add_data=request.data, update=True,
                                          rule_id=id, env=env.code):
                    return Response(data={"code": 1,
                                          "message": f"更新指标规则错误"})
                # 更新指定 ID 的告警规则对象（限当前环境）
                AlertRule.objects.filter(id=id, env=env).update(**request.data)
                # 重载 Prometheus 规则
                ok = p.reload_prometheus()
                if not ok:
                    return Response(data={"code": 1, "message": "prometheus 重载规则失败，请手动重启prometheus进行重载"})
                return Response()
            print(request.data["expr"], severity)
            # 判重按环境隔离：同一表达式在不同环境各自生效
            if AlertRule.objects.filter(env=env, expr=request.data["expr"], severity=severity).exists():
                return Response(data={"code": 1,
                                      "message": f"创建指标规则过程中出错: "
                                                 f"同一指标规则级别重复添加"})
            if not p.update_rule_file(add_data=request.data, add=True,
                                      env=env.code):
                return Response(data={"code": 1,
                                      "message": f"创建指标规则错误"})
            # 创建新的告警规则对象
            AlertRule(**request.data).save()
            # 重载 Prometheus 规则
            ok = p.reload_prometheus()
            if not ok:
                return Response(data={"code": 1,
                                      "message": "prometheus 重载规则失败，请手动重启prometheus进行重载"})
            return Response()
        except Exception as e:
            logger.error(f"创建指标规则过程中出错: {traceback.format_exc()}")
            return Response(
                data={"code": 1, "message": f"创建指标规则过程中出错: {str(e)}!"})

    def delete(self, request, *args, **kwargs):
        """
        删除规则

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含删除结果的响应
        """
        # 从请求查询参数中获取规则 ID
        id = request.query_params.get("id")
        # 获取当前请求环境上下文
        env = get_request_env(request)
        # 创建 Prometheus 工具类实例
        p = PrometheusUtils()
        # 规则文件按环境 code 拆分，删除只作用于当前环境的规则文件
        if not p.update_rule_file(delete=True, rule_id=id, env=env.code):
            return Response(data={"code": 1,
                                  "message": f"删除指标规则时，更新配置文件失败"})
        # 删除指定 ID 的告警规则对象（限当前环境），并获取删除的数量
        num, _ = AlertRule.objects.filter(id=id, env=env).delete()
        if num == 0:
            return Response(data={"code": 1, "message": "删除失败"})
        # 重载 Prometheus 规则
        ok = p.reload_prometheus()
        if not ok:
            return Response(data={"code": 1,
                                  "message": "prometheus "
                                             "重载规则失败，请手动重启prometheus进行重载"})
        return Response()


class BuiltinsRuleView(GenericViewSet, ListModelMixin):
    # POST 请求的描述信息
    post_description = "获取内置指标列表"
    # 指定序列化器类
    serializer_class = RuleSerializer
    # 指定查询集，获取所有规则对象
    queryset = Rule.objects.all()

    def list(self, request, *args, **kwargs):
        """
        获取内置指标列表。

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含内置指标列表的响应
        """
        # 获取序列化后的规则数据
        data = self.get_serializer(self.queryset, many=True).data
        # 获取所有服务名称的集合
        services = set([i.get("service") for i in data])
        r_data = {}
        for service in services:
            r_data[service] = []
            for i in data:
                if service == i.get("service"):
                    r_data[service].append(i)
        return Response(data=r_data)


class PromSqlTestView(GenericViewSet, CreateModelMixin):
    # POST 请求的描述信息
    post_description = "测试指标"
    # 指定序列化器类
    serializer_class = Serializer

    def create(self, request, *args, **kwargs):
        """
        测试指标。

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含测试结果的响应
        """
        # 从请求数据中获取监控指标表达式
        expr = request.data.get("expr")
        # 调用 Prometheus 类的方法获取指标结果
        ok, res = Prometheus().get_quota_res(quota=expr)
        if ok:
            return Response(data=res)
        return Response(data={"code": 1, "message": res})


class BatchUpdateRuleView(GenericViewSet, CreateModelMixin):
    """
    批量修改
    """
    # POST 请求的描述信息
    post_description = "批量修改启用停用状态"
    # 指定序列化器类
    serializer_class = QuotaSerializer
    # 指定查询集，获取所有告警规则对象
    queryset = AlertRule.objects.all()

    def create(self, request, *args, **kwargs):
        """
        id list
        批量修改接口

        :param request: 请求对象
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 包含批量修改结果的响应
        """
        # 创建 Prometheus 工具类实例
        p = PrometheusUtils()
        # 从请求数据中获取规则 ID 列表
        ids = request.data.get("ids")
        # 从请求数据中获取启用状态
        status = request.data.get("status")
        # 按 id 批量启停：仅本环境规则生效，且规则文件按当前环境 code
        # 生成（QuotaView 同款，多环境架构 Task 7b）
        env = get_request_env(request)
        for id in ids:
            # 更新指定 ID 的告警规则对象的启用状态（限当前环境）
            AlertRule.objects.filter(id=id, env=env).update(status=status)
        if not p.update_rule_file(env=env.code):
            return Response(data={"code": 1,
                                  "message": f"删除指标规则时，更新配置文件失败"})
        # 重载 Prometheus 规则
        ok = p.reload_prometheus()
        if not ok:
            return Response(data={"code": 1,
                                  "message": "prometheus 重载规则失败，请手动重启prometheus进行重载"})

        return Response()