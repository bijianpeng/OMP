"""
此模块主要用于与 Prometheus 和 Grafana 交互，包括获取 Prometheus 告警信息、
进行时区转换、判断服务类型、生成前端异常清单所需数据、过滤数据以及封装包含 Grafana URL 的数据。
"""
# 从数据库模型模块导入所需的模型类
from db_models.models import GrafanaMainPage, MonitorUrl, Host, ApplicationHub, Service
# 导入 requests 库，用于发送 HTTP 请求
import requests
# 导入 JSON 模块，用于处理 JSON 数据
import json
# 导入日志记录模块，用于记录程序运行中的信息
import logging
# 导入 pytz 模块，用于处理时区相关操作
import pytz
# 导入 datetime 模块，用于处理日期和时间
import datetime
# 导入 traceback 模块，用于获取异常的堆栈跟踪信息
import traceback
# 从项目配置文件中导入时区设置
from omp_server.settings import TIME_ZONE
# 从配置解析工具模块导入 Prometheus 认证信息
from utils.parse_config import PROMETHEUS_AUTH

# 获取名为 'server' 的日志记录器
logger = logging.getLogger('server')


class CurlPrometheus(object):
    """
    该类用于向 Prometheus 发送请求，获取告警信息。
    """
    @staticmethod
    def curl_prometheus():
        """
        请求 Prometheus 的告警信息接口，并返回相应的 JSON 数据。

        :return: 包含 Prometheus 告警信息的 JSON 数据，请求失败时返回 {"status": "-1"}
        """
        # 获取 Prometheus 的认证信息
        prometheus_auth = (PROMETHEUS_AUTH.get("username"),
                           PROMETHEUS_AUTH.get("plaintext_password"))
        # 从数据库中查询 Prometheus 的监控 URL
        monitor_ip = MonitorUrl.objects.filter(name="prometheus")
        # 若查询到 URL 则使用，否则使用默认值
        monitor_url = monitor_ip[0].monitor_url if len(
            monitor_ip) else "127.0.0.1:19013"
        try:
            # 构造请求 Prometheus 告警信息的 URL
            url = f"http://{monitor_url}/api/v1/alerts"
            # 发送 GET 请求获取告警信息
            response = requests.request(
                "GET", url, headers={}, data="", auth=prometheus_auth)
            # 将响应文本转换为 JSON 数据并返回
            return json.loads(response.text)
        except Exception as e:
            # 记录请求失败的错误信息
            logger.error("prometheus请求alerts失败：" + str(e))
            return {"status": "-1"}


def utc_local(utc_time_str, utc_format='%Y-%m-%dT%H:%M:%SZ'):
    """
    时区转换，如果转换报错，那么使用当前时间作为返回值。

    :type utc_time_str: str
    :param utc_time_str: UTC 时间字符串
    :type utc_format: str
    :param utc_format: UTC 时间格式
    :return: 转换后的本地时间字符串
    """
    try:
        # 处理 UTC 时间字符串，去除毫秒部分
        utc_time_str = utc_time_str.split(
            ".")[0] + utc_time_str.split(".")[-1][-1]
        # 获取本地时区对象
        local_tz = pytz.timezone(TIME_ZONE)
        # 定义本地时间格式
        local_format = "%Y-%m-%d %H:%M:%S"
        # 将 UTC 时间字符串解析为 datetime 对象
        utc_dt = datetime.datetime.strptime(utc_time_str, utc_format)
        # 将 UTC 时间对象转换为本地时间对象
        local_dt = utc_dt.replace(tzinfo=pytz.utc).astimezone(local_tz)
        # 将本地时间对象格式化为字符串
        time_str = local_dt.strftime(local_format)
        return time_str
    except Exception as e:
        # 记录时间格式转换失败的日志，包含异常信息和堆栈跟踪
        logger.error(f"在转化时间格式时报错: {str(e)}\n详情为: {traceback.format_exc()}")
        # 若转换失败，返回当前时间的字符串
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def classify_alert(labels, database_list, service_list, component_list):
    """
    统一判定一条告警属于 host、database、service、component。

    规则：
    1) 优先用 labels.instance_name 精确匹配 Service.service_instance_name
       （修复 job=nodeExporter 但 instance_name 为组件实例名时被误判为 host）；
    2) 匹配不上或为空时，回退用 app/job 推断 app_name 匹配 service.app_name
       （保留原 get_item_type 的行为）；
    3) 都不匹配则 nodeExporter 归 host、其余归 service。

    :param labels: 告警的 labels 字典
    :param database_list: 数据库服务列表（预取）
    :param service_list: 普通服务列表（预取）
    :param component_list: 组件服务列表（预取）
    :return: 类型字符串 host/database/service/component
    """
    labels = labels or {}
    instance_name = labels.get("instance_name", "")
    # 1) 优先用 instance_name 精确匹配（覆盖 nodeExporter + 组件 instance_name 等场景）
    if instance_name:
        if any(x.service_instance_name == instance_name for x in database_list):
            return "database"
        if any(x.service_instance_name == instance_name for x in service_list):
            return "service"
        if any(x.service_instance_name == instance_name for x in component_list):
            return "component"
    # 2) 回退：用 app/job 推断 app_name 匹配
    app_name = labels.get("app") or labels.get("job", "").split("Exporter")[0]
    if app_name:
        if any(x.service.app_name == app_name for x in database_list):
            return "database"
        if any(x.service.app_name == app_name for x in service_list):
            return "service"
        if any(x.service.app_name == app_name for x in component_list):
            return "component"
    # 3) 最终回退：nodeExporter 归 host，其余归 service
    return "host" if labels.get("job") == "nodeExporter" else "service"


def get_item_type(item, database_list, service_list, component_list):
    """
    获取 item 的类型，类型包括 host、database、service、component。

    :param item: 包含告警信息的字典
    :param database_list: 数据库服务列表
    :param service_list: 普通服务列表
    :param component_list: 组件服务列表
    :return: item 的类型字符串
    """
    return classify_alert(item.get("labels") or {}, database_list,
                          service_list, component_list)


def explain_prometheus(params, env=None):
    """
    生成前端异常清单所需要的 JSON 列表。

    :param params: 过滤参数
    :param env: 环境 Env 实例；非 None 时主机/服务基准列表按环境过滤，
        即异常清单只展示当前环境的告警（spec §6.2）
    :return: 包含前端异常清单信息的 JSON 列表，请求失败时返回 "error"
    """
    # 定义忽略的服务状态列表
    ignore_status_list = [Service.SERVICE_STATUS_NORMAL,
                          Service.SERVICE_STATUS_STARTING,
                          Service.SERVICE_STATUS_STOPPING,
                          Service.SERVICE_STATUS_RESTARTING,
                          Service.SERVICE_STATUS_STOP]
    # 环境过滤条件（env 为 None 时不过滤，保持原行为）
    env_filter = dict(env=env) if env is not None else dict()
    # 获取主机列表，包含 IP 和实例名称
    host_list = Host.objects.filter(
        **env_filter).values('ip', 'instance_name')
    # 获取主机 IP 列表
    host_ip_list = [host.get("ip") for host in host_list]
    # 获取数据库服务列表，过滤指定状态和非基础环境的服务
    database_list = Service.objects.filter(
        service__app_type=ApplicationHub.APP_TYPE_COMPONENT).filter(
        service__app_labels__label_name__contains="数据库").filter(
        service_status__in=ignore_status_list).filter(
        service__is_base_env=False).filter(**env_filter)
    # 获取普通服务列表，过滤指定状态和非基础环境的服务
    service_list = Service.objects.filter(
        service__app_type=ApplicationHub.APP_TYPE_SERVICE).filter(
        service_status__in=ignore_status_list).filter(
        service__is_base_env=False).filter(
        service_controllers__start__isnull=False).filter(**env_filter)
    # 获取组件服务列表，过滤指定状态和非基础环境的服务
    component_list = Service.objects.filter(
        service__app_type=ApplicationHub.APP_TYPE_COMPONENT).filter(
        service_status__in=ignore_status_list).filter(
        service__is_base_env=False).filter(**env_filter)
    # 调用 CurlPrometheus 类的方法获取 Prometheus 告警信息
    r = CurlPrometheus.curl_prometheus()
    if r.get('status') == 'success':
        # 初始化存储 Prometheus 信息的列表
        prometheus_info = []
        # 初始化用于去重的比较列表
        compare_list = []
        # 获取告警信息列表
        alerts = r.get('data', {}).get('alerts')
        # 按告警级别对告警信息进行排序
        prometheus_alerts = sorted(
            alerts, key=lambda e: e.get('labels').__getitem__('severity'), reverse=False)
        for lab in prometheus_alerts:
            if lab.get('status') == 'resolved':
                # 若告警状态为已解决，则跳过
                continue
            # 获取告警标签信息
            label = lab.get('labels')
            if label.get("instance", "") not in host_ip_list:
                # 若实例 IP 不在主机 IP 列表中，则跳过
                continue
            # 初始化临时字典
            tmp_dict = {}
            # 获取告警实例的 IP（去掉端口），既用于展示也参与去重
            _ip = label.get('instance').split(":")[0] if label.get('instance') else ''
            # 去重维度含 IP：nodeExporter 告警 instance_name 为空，
            # 必须靠 IP 区分不同主机，否则多台主机的同类告警会被合并
            tmp_list = [label.get('alertname'), label.get(
                'instance_name'), label.get('job'), _ip]
            if tmp_list in compare_list:
                # 若临时列表已存在于比较列表中，则跳过
                continue
            compare_list.append(tmp_list)
            # 获取告警项的类型
            _type = get_item_type(item=lab, database_list=database_list, service_list=service_list,
                                  component_list=component_list)
            tmp_dict['type'] = _type
            tmp_dict['ip'] = _ip
            # 获取应用名称
            s_app = label.get('app') if label.get(
                'app') else label.get("job", "").split("Exporter")[0]
            tmp_dict['instance_name'] = f"{s_app}-{_ip.split('.')[2]}-{_ip.split('.')[3]}" if _type != "host" else s_app
            # 获取告警级别
            tmp_dict['severity'] = label.get('severity')
            # 获取告警注释信息
            annotation = lab.get('annotations')
            tmp_dict['description'] = annotation.get('description')
            # 获取告警发生时间
            lab_date = lab.get('activeAt') if lab.get(
                'activeAt') else lab.get('startsAt')
            tmp_dict['date'] = utc_local(lab_date)
            # 携带环境 code，explain_url 拼跳转 URL 时追加 var-env（决策 #22）
            tmp_dict['env'] = env.code if env is not None else "default"
            prometheus_info.append(tmp_dict)
        # 调用 explain_url 函数封装包含 Grafana URL 的数据
        prometheus_json = explain_url(prometheus_info)
        if params:
            # 若有过滤参数，调用 explain_filter 函数进行过滤
            prometheus_json = explain_filter(prometheus_json, params)
        return prometheus_json
    else:
        # 记录请求失败的错误信息
        logger.error("prometheus请求alerts失败：" + str(r))
        return "error"


def explain_filter(prometheus_json, params):
    """
    递归筛选 Prometheus 信息。

    :param prometheus_json: 包含 Prometheus 信息的 JSON 列表
    :param params: 过滤参数
    :return: 筛选后的 JSON 列表
    """
    if not params:
        # 若过滤参数为空，则直接返回原始 JSON 列表
        return prometheus_json
    # 弹出一个过滤字段和值
    fil_filed = params.popitem()
    # 初始化存储筛选结果的列表
    fil_info = []
    for j in prometheus_json:
        # 获取当前项的对应字段值
        value = j.get(fil_filed[0])
        if value and fil_filed[1].lower() in value.lower():
            # 若值存在且包含过滤值，则添加到筛选结果列表中
            fil_info.append(j)
        # TODO 组件集合包含数据库
        if fil_filed[1].lower() == "component" and value.lower() == "database":
            # 若过滤值为 component 且当前值为 database，则添加到筛选结果列表中
            fil_info.append(j)
    # 递归调用自身进行筛选
    return explain_filter(fil_info, params)


def explain_url(explain_info, is_service=None, is_host=None):
    """
    封装字典，添加 Grafana 的 URL。

    :param explain_info: 包含实例信息的列表
    :param is_service: 是否为服务类型，默认为 None
    :param is_host: 是否为主机类型，默认为 None
    :return: 封装后的包含 Grafana URL 的实例信息列表
    """
    # monitor_ip = MonitorUrl.objects.filter(name="grafana")
    # grafana_ins = monitor_ip[0].monitor_url if len(
    #     monitor_ip) else "127.0.0.1:19013"
    # grafana_url = f"http://{grafana_ins}"
    # 去掉跳转 Grafana 中携带的 IP、port
    grafana_url = ""
    # 初始化存储 Grafana 实例 URL 的字典
    url_dict = {}
    for i in GrafanaMainPage.objects.all():
        # 将 Grafana 实例名称和 URL 存储到字典中
        url_dict[i.instance_name] = i.instance_url
    for instance_info in explain_info:
        # TODO 待确认 跳转服务面板使用 app_name 而不是 instance_name ?
        if is_service:
            # 若为服务类型，获取应用名称
            service_name = instance_info.get('app_name')
        else:
            # 否则，从实例名称中截取应用名称
            service_name = instance_info.get('instance_name', '').split("-")[0]
        if instance_info.get('is_web'):
            # 若为 Web 服务，则监控 URL 和日志 URL 设为 None
            instance_info['monitor_url'] = None
            instance_info['log_url'] = None
            continue
        # 获取实例的 IP
        service_ip = instance_info.get('ip')
        if instance_info.get('type') != 'host' and not is_host \
                or is_service:
            # 若不是主机类型或为服务类型
            # 获取服务实例名称
            service_instance_name = instance_info.get('service_instance_name')

            # 获取监控 URL
            monitor_url = url_dict.get(service_name.lower() if isinstance(service_name, str) else service_name)
            # 初始化集群 URL
            instance_info['cluster_url'] = ""
            if monitor_url:
                # 若监控 URL 存在，构造监控 URL
                instance_info['monitor_url'] = grafana_url + \
                                               monitor_url + f"?var-instance={service_ip}&kiosk=tv"
                if Service.objects.filter(
                        service_instance_name=service_instance_name).first() and Service.objects.filter(
                    service_instance_name=service_instance_name).first().cluster:
                    # 若服务存在且属于集群，获取集群名称
                    cluster_name = Service.objects.filter(
                        service_instance_name=service_instance_name).first().cluster.cluster_name
                    # 获取集群监控 URL
                    cluster_monitor_url = url_dict.get(f"{service_name}cluster", "")
                    instance_info[
                        'cluster_url'] = cluster_monitor_url + f"?var-cluster={cluster_name}&kiosk=tv" if cluster_monitor_url else ""
            else:
                try:
                    if service_name and ApplicationHub.objects.filter(
                            app_name=service_name
                    ).first() and ApplicationHub.objects.filter(
                        app_name=service_name
                    ).first().app_monitor and ApplicationHub.objects.filter(
                        app_name=service_name
                    ).first().app_monitor.get("type") == "JavaSpringBoot":
                        # 若应用为 JavaSpringBoot 类型，构造监控 URL
                        # （var-env 取上游传入的环境 code，spec 决策 #22）
                        instance_info['monitor_url'] = grafana_url + url_dict.get(
                            'javaspringboot',
                            'nojavaspringboot') + \
                                                       f"?var-env={instance_info.get('env', 'default')}&var-ip={service_ip}" \
                                                       f"&var-app={service_name}&var-job={service_name}Exporter&kiosk=tv"
                    else:
                        # 其他情况，构造监控 URL
                        instance_info['monitor_url'] = grafana_url + url_dict.get(
                            'service', 'noservice') + f"?var-ip={service_ip}&var-app={service_name}&kiosk=tv"
                except Exception as e:
                    # 记录异常信息
                    logger.error(e)
                    # 构造默认监控 URL
                    instance_info['monitor_url'] = grafana_url + url_dict.get(
                        'service', 'noservice') + f"?var-ip={service_ip}&var-app={service_name}&kiosk=tv"
            # 构造日志 URL（var-env 取上游传入的环境 code，spec 决策 #22）
            instance_info['log_url'] = grafana_url + \
                                       url_dict.get(
                                           'log',
                                           'nolog') + f"?var-env={instance_info.get('env', 'default')}&var-app={service_name}" + f"&var-instance={service_ip}"
        else:
            # 若为主机类型，构造监控 URL
            instance_info['monitor_url'] = grafana_url + \
                                           url_dict.get('node', 'nohosts') + \
                                           f"?var-node={service_ip}&kiosk=tv"
            # 日志 URL 设为 None
            instance_info['log_url'] = None
    return explain_info
