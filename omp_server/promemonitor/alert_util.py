"""
此模块用于解析 Prometheus 返回的告警信息，包括时间转换、服务类型获取、
监控和日志 URL 获取以及告警信息分析等功能。
"""
# 导入 datetime 模块，用于处理日期和时间相关操作
import datetime
# 导入 logging 模块，用于记录程序运行中的日志信息
import logging
# 导入 traceback 模块，用于获取异常的堆栈跟踪信息
import traceback

# 导入 pytz 模块，用于处理时区相关操作
import pytz
# 从项目配置文件中导入时区设置
from omp_server.settings import TIME_ZONE
# 从数据库模型模块导入 Host、Service 和 ApplicationHub 模型
from db_models.models import Host, Service, ApplicationHub, Env
# 从 grafana_url 模块导入 explain_url 函数，用于解析 Grafana 相关 URL
from promemonitor.grafana_url import explain_url

# 获取名为 'server' 的日志记录器
logger = logging.getLogger('server')


def resolve_alert_env(labels, alert_host_ip):
    """
    解析告警所属环境（三级回退，spec §6.2）：

    1. 告警 labels 的 env 标签（值为 Env.code）→ Env.objects.filter(code=...)
    2. 标签缺失或未匹配到环境 → 按告警主机 IP 反查 Host.env
    3. 均失败 → default 环境（id=1），并记录 warning 日志

    告警入库写 env（ReceiveAlertSerializer）与监控/日志跳转 URL 的
    var-env 拼参共用本函数，保证同一条告警两处环境一致。

    :param labels: 告警 labels 字典
    :param alert_host_ip: 告警来源主机 IP
    :return: Env 实例；default 环境也缺失时返回 None（调用方按 None 处理）
    """
    labels = labels or {}
    # 1. labels env 标签（值 = Env.code）
    env_code = labels.get("env", "")
    if env_code:
        env = Env.objects.filter(code=env_code).first()
        if env is not None:
            return env
        logger.warning(f"告警 labels env 标签 {env_code} 未匹配到环境")
    # 2. 按告警主机 IP 反查 Host.env（与 __call__ 主机查询同款路径）
    host = Host.objects.filter(ip=alert_host_ip).first()
    host_env = getattr(host, "env", None) if host is not None else None
    if host_env is not None:
        return host_env
    # 3. 兜底归 default 环境
    logger.warning(
        f"告警环境解析失败（labels env={env_code!r}, ip={alert_host_ip}），"
        f"归入 default 环境")
    return Env.objects.filter(id=1).first()


def append_var_env(url, ele):
    """
    为 Grafana 跳转 URL 追加 var-env 参数（spec 决策 #22）。

    看板 PromQL 为 env="$env" AND instance 双重过滤，不带 var-env 时
    新环境资源看板无数据。explain_url 内部已拼 var-env 的 URL
    （JavaSpringBoot 面板 / 日志面板）不重复追加。

    :param url: 原始 URL
    :param ele: 包含服务信息的列表，首元素 dict 可携带 env=Env.code
    :return: 追加 var-env 后的 URL；url 为空时原样返回
    """
    if not url or "var-env=" in url:
        return url
    env_code = "default"
    if ele and isinstance(ele, (list, tuple)) and ele[0]:
        env_code = ele[0].get("env") or "default"
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}var-env={env_code}"


def get_service_type(ip, service_name):
    """
    获取服务的中文名称以及服务分类
    
    :param ip: 服务所在主机的 IP 地址
    :param service_name: 服务名称
    :type service_name: str
    :return: 服务的中文名称和服务分类
    """
    # 默认将服务名称作为中文名称
    product_cn_name = service_name
    # 默认将 IP 地址作为服务分类
    service_type = ip
    return product_cn_name, service_type


def get_monitor_url(ele):
    """
    获取监控页面的 URL（追加 var-env={Env.code}，spec 决策 #22）

    :param ele: 包含服务信息的列表，首元素 dict 可携带 env=Env.code
    :return: 监控页面的 URL，如果获取失败则返回 None
    """
    try:
        # 调用 explain_url 函数解析 URL 并获取监控页面的 URL
        monitor_url = explain_url(ele)[0].get('monitor_url')
        # 看板按 env 双过滤，URL 未携带 var-env 时补齐（见 append_var_env）
        monitor_url = append_var_env(monitor_url, ele)
    except TypeError:
        # 记录获取监控 URL 失败的日志
        logger.error('get monitor url failed')
        monitor_url = None
    return monitor_url


def get_log_url(ele):
    """
    获取日志页面的 URL（追加 var-env={Env.code}，spec 决策 #22）

    :param ele: 包含服务信息的列表，首元素 dict 可携带 env=Env.code
    :return: 日志页面的 URL，如果获取失败则返回 None
    """
    try:
        # 调用 explain_url 函数解析 URL 并获取日志页面的 URL
        monitor_log_url = explain_url(ele)[0].get('log_url')
        # 看板按 env 双过滤，URL 未携带 var-env 时补齐（见 append_var_env）
        monitor_log_url = append_var_env(monitor_log_url, ele)
    except TypeError:
        # 记录获取日志 URL 失败的日志
        logger.error('get monitor log url failed')
        monitor_log_url = None
    return monitor_log_url


def utc_to_local(utc_time_str, utc_format='%Y-%m-%dT%H:%M:%SZ'):
    """
    时区转换，如果转换报错，那么使用当前时间作为返回值
    
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


class AlertAnalysis:
    """
    解析 Prometheus 返回的告警信息的类
    """

    def __init__(self, item):
        """
        初始化 AlertAnalysis 类的实例，解析 Prometheus 返回的告警信息
    
        :param item: 包含告警信息的字典，格式如下：
            {
              "status": "resolved",
              "labels":
                {
                    "alertname":"app state",
                    "app":"nbdServer",
                    "instance":"10.0.9.61:18215",
                    "ip":"10.0.9.61",
                    "job":"10.0.9.61",
                    "severity":"critical"
                },
              "annotations":
                {
                  "consignee":"2871253303@qq.com",
                  "description":"主机 10.0.12.35 中的 zookeeper_exporter 已经down掉超过一分钟.",
                  "summary":"app state(instance 10.0.9.61:18215)"
                },
              "state":"firing",
              "activeAt":"2021-04-10T08:36:23.838961588Z",
              "value":"0e+00",
              "fingerprint": "" # 非必需
            }
        """
        self.item = item
        # 获取告警信息中的标签部分
        self.labels = self.item.get("labels", {})
        # 获取告警信息中的注释部分
        self.annotations = self.item.get("annotations", {})
        # 获取告警信息的唯一标识
        self.fingerprint = self.item.get("fingerprint", "")

    @staticmethod
    def _get(items, key):
        """
        从字典中获取指定键的值，如果键不存在则返回默认值 "DEFAULT_DATA"
    
        :param items: 字典对象
        :param key: 要获取的键
        :return: 键对应的值，如果键不存在则返回 "DEFAULT_DATA"
        """
        return items.get(key, "DEFAULT_DATA")

    # @property
    # def is_resolved(self):
    #     return self.item.get("status") == 'resolved'

    # @property
    # def is_alert(self):
    #     return self._get(self.labels, "severity") in ["critical", "warning"]

    def node_exporter(self):
        """
        处理 nodeExporter 类型的告警信息
    
        :return: 包含告警类型、主机 IP 等信息的字典
        """
        return dict(
            alert_type="host",
            alert_host_ip=self._get(self.labels, "instance"),
            alert_service_name="",
            alert_service_type="",
            alert_service_en_type=""
        )

    def exporter(self):
        """
        处理 Exporter 类型的告警信息
    
        :return: 包含告警类型、主机 IP、服务名称等信息的字典
        """
        # 获取告警主机的 IP 地址
        alert_host_ip = self._get(self.labels, "instance")
        # 获取告警服务信息
        alert_service = self._get(self.labels, "job")
        # 去除服务信息中的 "Exporter" 并去除首尾空格
        alert_service_name = alert_service.replace("Exporter", "").strip()
        # 获取服务类型和英文服务类型
        alert_service_type, alert_service_en_type = get_service_type(
            alert_host_ip, alert_service_name)
        # 获取应用名称
        app_name_str = self._get(self.labels, "app") if self._get(self.labels, "app") else \
            self._get(self.labels, "job").split("Exporter")[0]
        if not app_name_str:
            # 若应用名称为空，告警类型为 "service"
            _alert_type = "service"
        # 获取非基础环境的组件列表
        component_list = Service.objects.filter(
            service__app_type=ApplicationHub.APP_TYPE_COMPONENT).filter(
            service__is_base_env=False)
        if list(filter(
            lambda x: x.service.app_name == app_name_str, list(
                component_list))):
            # 若应用名称在组件列表中，告警类型为 "component"
            _alert_type = "component"
        else:
            # 否则，告警类型为 "service"
            _alert_type = "service"
        return dict(
            alert_type=_alert_type,
            alert_host_ip=self._get(self.labels, "instance"),
            alert_service_name=alert_service_name,
            alert_service_type=alert_service_type,
            alert_service_en_type=alert_service_en_type
        )

    # def other(self):
    #     alert_host_ip = self._get(self.labels, "ip")
    #     alert_service_name = self._get(self.labels, "app").strip()
    #     alert_service_type, alert_service_en_type = get_service_type(
    #         alert_host_ip, alert_service_name)
    #     return dict(
    #         alert_type="service",
    #         alert_host_ip=alert_host_ip,
    #         alert_service_name=alert_service_name,
    #         alert_service_type=alert_service_type,
    #         alert_service_en_type=alert_service_en_type
    #     )

    def get_alert_time(self):
        """
        获取告警发生的时间，并将其从 UTC 时间转换为本地时间
    
        :return: 转换后的本地时间字符串
        """
        # 优先获取 startsAt 时间，若不存在则获取 activeAt 时间
        start_time = self.item.get("startsAt", "")
        if not start_time:
            start_time = self.item.get("activeAt", "")
        # 调用 utc_to_local 函数进行时间转换
        return utc_to_local(utc_time_str=start_time)

    def analysis_labels(self):
        """
        分析告警信息中的标签部分，获取告警类型、级别等信息
    
        :return: 包含告警相关信息的字典
        """
        # 获取旧的告警类型
        old_alert_type = self._get(self.labels, "job")
        if old_alert_type == "nodeExporter":
            # 若为 nodeExporter 类型，调用 node_exporter 方法处理
            kwargs = self.node_exporter()
        elif "Exporter" in old_alert_type:
            # 若包含 "Exporter"，调用 exporter 方法处理
            kwargs = self.exporter()
        else:
            # 其他情况，暂时调用 exporter 方法处理
            # kwargs = self.other()
            kwargs = self.exporter()  # TODO 有other场景出现再换
        # 添加告警状态信息
        kwargs["status"] = self.item.get("status", "firing")
        # 添加告警级别信息
        kwargs["alert_level"] = self._get(self.labels, "severity")
        # 添加告警指标名称信息
        kwargs["alertname"] = self._get(self.labels, "alertname")
        # 添加告警唯一标识信息
        kwargs["fingerprint"] = self.fingerprint
        # 添加告警发生时间信息
        kwargs.update(alert_time=self.get_alert_time())
        # 环境三级解析（labels env 标签 → IP 反查 → default），
        # 跳转 URL 的 var-env 拼参与告警入库写 env 共用该结果
        env = resolve_alert_env(self.labels, kwargs.get("alert_host_ip"))
        kwargs["env_code"] = str(env.code) if env is not None else "default"
        if kwargs["alert_type"] == "service" or kwargs["alert_type"] == "component":
            # 若告警类型为服务或组件，获取监控和日志 URL
            kwargs["monitor"] = get_monitor_url(
                [{
                    "ip": kwargs.get("alert_host_ip"),
                    "type": "service",
                    "instance_name": kwargs.get("alert_service_name", ""),
                    "env": kwargs["env_code"]
                }]
            )
            kwargs["monitor_log"] = get_log_url(
                [{
                    "ip": kwargs.get("alert_host_ip"),
                    "type": "service",
                    "instance_name": kwargs.get("alert_service_name"),
                    "env": kwargs["env_code"]
                }]
            )
        else:
            # 若告警类型为主机，获取主机监控和日志 URL
            kwargs["monitor"] = get_monitor_url(
                [{
                    "ip": kwargs.get("alert_host_ip"),
                    "type": "host",
                    "instance_name": "node",
                    "env": kwargs["env_code"]
                }]
            )
            kwargs["monitor_log"] = get_log_url(
                [{
                    "ip": kwargs.get("alert_host_ip"),
                    "type": "host",
                    "instance_name": "node",
                    "env": kwargs["env_code"]
                }]
            )
        return kwargs

    def analysis_annotations(self):
        """
        分析告警信息中的注释部分，获取告警接收人和描述信息
    
        :return: 包含告警接收人和描述信息的字典
        """
        return dict(
            alert_receiver=self._get(self.annotations, "consignee"),
            #  服务down：主机 10.0.12.35 中的 zookeeper 已经down掉超过一分钟.
            #  服务exporter down：
            #  主机 10.0.12.35 中的 zookeeper_exporter 已经down掉超过一分钟.
            alert_describe=self._get(self.annotations, "description")
        )

    def __call__(self, *args, **kwargs):
        """
        调用该类的实例时执行的方法，返回完整的告警信息

        告警所属环境由 analysis_labels 内的 resolve_alert_env 解析
        （labels env 标签 → IP 反查 → default），env_id 取自告警关联的
        主机/服务自身（历史行为保留），env_code 为解析结果（入库与
        var-env 拼参使用）。

        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含完整告警信息的字典，格式如下：
            {
                "alert_type": 告警类型 host or service,
                "alert_host_ip": 告警来自哪个主机,
                "alert_host_system": 告警来自主机的系统,
                "alert_service_name": 告警服务名称,
                "alert_service_type": 告警服务所属产品名称,
                "alert_service_en_type": 告警服务类型，self_dev component database,
                "alert_level": 告警级别,
                "alert_describe": 告警描述,
                "alert_receiver": 告警接收人,
                "alert_resolve": 告警解决方案,
                "alert_time": 告警发生时间,
                "monitor": 跳转grafana地址,
                "monitor_log": 日志跳转url（仅服务存在）,
                "fingerprint": 告警对应的唯一标识,
                "status": 告警状态： resolved，恢复；firing：告警 # 推送使用，其他无用,
                "alertname": 告警指标： # 推送使用，其他无用,
                "env_id": 告警关联主机/服务的环境 ID（自身字段）,
                "env_code": 告警解析出的环境标识（Env.code）,
            }
        """
        # if not self.is_alert:
        #     return {}
        # 分析告警标签信息
        alert_info = self.analysis_labels()
        if alert_info["alert_type"] == "host":
            # 若告警类型为主机，获取主机信息
            host = Host.objects.filter(
                ip=alert_info["alert_host_ip"]).first()
            if not host:
                return {}
            # 添加环境 ID 和主机实例名称信息
            alert_info["env_id"] = host.env_id
            alert_info["alert_instance_name"] = host.instance_name
        else:
            # 若告警类型为服务或组件，获取服务信息
            ser = Service.objects.filter(
                service__app_name=alert_info["alert_service_name"],
                ip=alert_info["alert_host_ip"]
            ).first()
            # host = Host.objects.filter(
            #     ip=alert_info["alert_host_ip"]).first()
            if not ser:
                return {}
            # 添加环境 ID 和服务实例名称信息
            alert_info["env_id"] = ser.env_id
            alert_info["alert_instance_name"] = ser.service_instance_name
        # 合并注释分析信息
        alert_info.update(**self.analysis_annotations())
        return alert_info
