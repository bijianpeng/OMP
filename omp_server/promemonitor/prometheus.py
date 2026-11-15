# 导入 JSON 模块，用于处理 JSON 数据
import json
# 导入日志记录模块，用于记录程序运行过程中的信息
import logging
# 导入数学模块，用于数学计算
import math

# 导入 requests 模块，用于发送 HTTP 请求
import requests

# 从数据库模型模块导入 MonitorUrl 模型
from db_models.models import MonitorUrl
# 从配置解析模块导入监控端口和 Prometheus 认证信息
from utils.parse_config import MONITOR_PORT, PROMETHEUS_AUTH

# 获取名为 'server' 的日志记录器
logger = logging.getLogger('server')


class Prometheus:
    """
    定义prometheus的一些参数以及动作
    """
    # 定义状态常量，包含正常、警告、严重三种状态
    STATUS = ("normal", "warning", "critical")

    def __init__(self):
        # 调用 get_prometheus_config 方法获取 Prometheus 的基础 URL
        self.basic_url = self.get_prometheus_config()
        # 构造 Prometheus API 查询的基础 URL
        self.prometheus_api_query_url = f'http://{self.basic_url}/api/v1/query?query='  # NOQA
        # 构造 Prometheus 认证所需的基本认证信息
        self.basic_auth = (PROMETHEUS_AUTH.get(
            "username", "omp"), PROMETHEUS_AUTH.get("plaintext_password", ""))
        # 定义请求头，指定内容类型为 JSON
        self.headers = {'Content-Type': 'application/json'}

    @staticmethod
    def get_prometheus_config():
        """
        获取 Prometheus 的配置 URL，如果数据库中没有配置，则使用默认值。

        :return: Prometheus 的基础 URL
        """
        # 从数据库中查询名称为 'prometheus' 的监控 URL 配置
        prometheus_url_config = MonitorUrl.objects.filter(
            name='prometheus').first()
        if not prometheus_url_config:
            # 若未查询到配置，使用默认的 Prometheus URL
            return f'127.0.0.1:{MONITOR_PORT.get("prometheus", 19011)}'  # 默认值

        monitor_url = prometheus_url_config.monitor_url
        if monitor_url:
            # 若配置存在且 URL 不为空，返回该 URL
            return monitor_url
        # 若配置中的 URL 为空，使用默认的 Prometheus URL
        return f'127.0.0.1:{MONITOR_PORT.get("prometheus", 19011)}'  # 默认值

    @staticmethod
    def get_host_threshold(env_id=1,**kwargs):
        """
        获取主机各项指标的阈值，优先从数据库中获取，若获取失败则使用默认值。

        :param env_id: 环境 ID，默认为 1
        :param kwargs: 其他关键字参数，可用于传递数据目录信息
        :return: 包含主机各项指标阈值的字典
        """
        # 定义主机各项指标的默认阈值
        host_threshold = {
            'cpu': (80, 90),
            'mem': (80, 90),
            'root_disk': (80, 90),
            'data_disk': (80, 90),
        }
        try:
            # 从数据库模型模块导入 AlertRule 模型
            from db_models.models import AlertRule
            # 查询 CPU 使用率警告级别的阈值
            cpu_warning_ht = AlertRule.objects.filter(env_id=env_id,
                                                          name="CPU使用率",
                                                          severity="warning").first()
            # 查询 CPU 使用率严重级别的阈值
            cpu_critical_ht = AlertRule.objects.filter(env_id=env_id,
                                                           name="CPU使用率",
                                                           severity="critical").first()
            # 查询内存使用率警告级别的阈值
            mem_warning_ht = AlertRule.objects.filter(env_id=env_id,
                                                          name="内存使用率",
                                                          severity="warning").first()
            # 查询内存使用率严重级别的阈值
            mem_critical_ht = AlertRule.objects.filter(env_id=env_id,
                                                           name="内存使用率",
                                                           severity="critical").first()
            # 查询根分区使用率警告级别的阈值
            root_disk_warning_ht = AlertRule.objects.filter(env_id=env_id,
                                                                name="根分区使用率",
                                                                severity="warning").first()
            # 查询根分区使用率严重级别的阈值
            root_disk_critical_ht = AlertRule.objects.filter(env_id=env_id,
                                                                 name="根分区使用率",
                                                                 severity="critical").first()
            # 初始化数据分区使用率警告和严重级别的阈值为 None
            data_disk_warning_ht = None
            data_disk_critical_ht = None
            if kwargs.get("data_dir"):
                """
                从指标规则中获取指定路径的数据分区
                """
                # 查询指定数据目录下数据分区使用率警告级别的阈值
                data_disk_warning_ht = AlertRule.objects.filter(env_id=env_id,
                                                                    name="数据分区使用率",
                                                                    severity="warning").first()
                # 查询指定数据目录下数据分区使用率严重级别的阈值
                data_disk_critical_ht = AlertRule.objects.filter(env_id=env_id,
                                                                     name="数据分区使用率",
                                                                     severity="critical").first()


            #
            # from db_models.models import HostThreshold
            # cpu_warning_ht = HostThreshold.objects.filter(env_id=env_id, index_type="cpu_used",
            #                                               alert_level="warning").first()
            # cpu_critical_ht = HostThreshold.objects.filter(env_id=env_id, index_type="cpu_used",
            #                                                alert_level="critical").first()
            # mem_warning_ht = HostThreshold.objects.filter(env_id=env_id, index_type="memory_used",
            #                                               alert_level="warning").first()
            # mem_critical_ht = HostThreshold.objects.filter(env_id=env_id, index_type="memory_used",
            #                                                alert_level="critical").first()
            # root_disk_warning_ht = HostThreshold.objects.filter(env_id=env_id, index_type="disk_root_used",
            #                                                     alert_level="warning").first()
            # root_disk_critical_ht = HostThreshold.objects.filter(env_id=env_id, index_type="disk_root_used",
            #                                                      alert_level="critical").first()
            # data_disk_warning_ht = HostThreshold.objects.filter(env_id=env_id, index_type="disk_data_used",
            #                                                     alert_level="warning").first()
            # data_disk_critical_ht = HostThreshold.objects.filter(env_id=env_id, index_type="disk_data_used",
            #                                                      alert_level="critical").first()
            # 更新主机各项指标的阈值
            host_threshold.update(
                cpu=(
                    int(cpu_warning_ht.threshold_value) if cpu_warning_ht else 0,
                    int(cpu_critical_ht.threshold_value) if cpu_critical_ht else 100,
                ),
                mem=(
                    int(mem_warning_ht.threshold_value) if mem_warning_ht else 0,
                    int(mem_critical_ht.threshold_value) if mem_critical_ht else 100,
                ),
                root_disk=(
                    int(root_disk_warning_ht.threshold_value) if root_disk_warning_ht else 0,
                    int(root_disk_critical_ht.threshold_value) if root_disk_critical_ht else 100,
                ),
                data_disk=(
                    int(data_disk_warning_ht.threshold_value) if data_disk_warning_ht else 0,
                    int(data_disk_critical_ht.threshold_value) if data_disk_critical_ht else 100,
                )
            )
        except Exception as e:
            # 若获取阈值失败，记录错误信息
            logger.error(f"获取主机阈值失败，详情为：{e}")
        return host_threshold

    def get_host_metric_status(self, metric, metric_value, **kwargs):
        """
        根据主机指标值和阈值判断主机指标的状态。

        :param metric: 指标名称，如 'cpu', 'mem' 等
        :param metric_value: 指标值
        :param kwargs: 其他关键字参数，可用于传递数据目录信息
        :return: 指标状态，'normal', 'warning' 或 'critical'
        """
        if metric_value is None:
            # 若指标值为空，返回 None
            return None
        # 调用 get_host_threshold 方法获取主机各项指标的阈值
        host_threshold = self.get_host_threshold(**kwargs)
        if metric_value > max(host_threshold.get(metric)):
            # 若指标值大于阈值中的最大值，状态为严重
            status = 'critical'
        elif metric_value < min(host_threshold.get(metric)):
            # 若指标值小于阈值中的最小值，状态为正常
            status = 'normal'
        else:
            # 否则，状态为警告
            status = 'warning'
        return status

    def get_host_cpu_usage(self, host_list):
        """
        获取指定主机cpu使用率

        :param host_list: 主机列表，每个元素为包含主机信息的字典
        :return: 更新了 CPU 使用率和状态信息的主机列表
        """
        # 构造查询主机 CPU 使用率的 PromQL，交给 requests 通过 params 自动 URL 编码，
        # 避免 []/{}/空格等字符在严格版本的 urllib3 上触发 "Failed to parse"
        cpu_usage_query = '(1 - avg(rate(node_cpu_seconds_total' \
                          '{mode="idle"}[2m])) by (instance))*100'
        try:
            # 发送 GET 请求获取主机 CPU 使用率数据
            get_cpu_response = requests.get(
                url=f'http://{self.basic_url}/api/v1/query',
                params={'query': cpu_usage_query},
                headers=self.headers, auth=self.basic_auth)
            if get_cpu_response.status_code == 200:
                # 若请求成功，将响应内容解析为 JSON 格式
                cpu_usage_dict = get_cpu_response.json()
                if cpu_usage_dict.get('status') != 'success':
                    # 若获取数据失败，记录错误信息并返回原主机列表
                    logger.error(get_cpu_response.text)
                    logger.error('获取主机CPU使用率失败！')
                    return host_list
                for index, host in enumerate(host_list.copy()):
                    for item in cpu_usage_dict.get('data').get('result'):
                        if item.get('metric').get('instance') == host.get('ip'):
                            # 若找到匹配的主机 IP，更新该主机的 CPU 使用率和状态信息
                            host_list[index]['cpu_usage'] = math.ceil(
                                float(item.get('value')[1]))
                            host_list[index]['cpu_status'] = self.get_host_metric_status('cpu', math.ceil(
                                float(item.get('value')[1])))
                            break
                        # 若未找到匹配的主机 IP，将 CPU 使用率和状态信息置为 None
                        host_list[index]['cpu_usage'] = None
                        host_list[index]['cpu_status'] = None  # TODO  待阈值判断

                return host_list
            else:
                # 若请求失败，记录错误信息并返回原主机列表
                logger.error(get_cpu_response.text)
                logger.error('获取主机CPU使用率失败！')
                return host_list
        except requests.ConnectionError as e:
            # 若发生连接错误，记录错误信息并返回原主机列表
            logger.error(e)
            logger.error('获取主机CPU使用率失败！')
            return host_list
        except Exception as e:
            # 若发生其他异常，记录错误信息并返回原主机列表
            logger.error(e)
            logger.error('获取主机CPU使用率失败！')
            return host_list

    def get_host_mem_usage(self, host_list):
        """
        获取指定主机内存使用率

        :param host_list: 主机列表，每个元素为包含主机信息的字典
        :return: 更新了内存使用率和状态信息的主机列表
        """
        # 构造查询主机内存使用率的 Prometheus API URL
        query_url = f'{self.prometheus_api_query_url}(1 - (node_memory_MemAvailable_bytes / ' \
                    f'(node_memory_MemTotal_bytes)))* 100'
        # print(query_url)

        try:
            # 发送 GET 请求获取主机内存使用率数据
            get_mem_response = requests.get(
                url=query_url, headers=self.headers, auth=self.basic_auth)
            if get_mem_response.status_code == 200:
                # 若请求成功，将响应内容解析为 JSON 格式
                mem_usage_dict = get_mem_response.json()
                if mem_usage_dict.get('status') != 'success':
                    # 若获取数据失败，记录错误信息并返回原主机列表
                    logger.error(get_mem_response.text)
                    logger.error('获取主机内存使用率失败！')
                    return host_list
                for index, host in enumerate(host_list.copy()):
                    for item in mem_usage_dict.get('data').get('result'):
                        if item.get('metric').get('instance') == host.get('ip'):
                            # 若找到匹配的主机 IP，更新该主机的内存使用率和状态信息
                            host_list[index]['mem_usage'] = math.ceil(
                                float(item.get('value')[1]))
                            host_list[index]['mem_status'] = self.get_host_metric_status('mem', math.ceil(
                                float(item.get('value')[1])))
                            break
                        # 若未找到匹配的主机 IP，将内存使用率和状态信息置为 None
                        host_list[index]['mem_usage'] = None
                        host_list[index]['mem_status'] = None  # TODO  待阈值判断
                return host_list
            else:
                # 若请求失败，记录错误信息并返回原主机列表
                logger.error(get_mem_response.text)
                logger.error('获取主机内存使用率失败！')
                return host_list
        except requests.ConnectionError as e:
            # 若发生连接错误，记录错误信息并返回原主机列表
            logger.error(e)
            logger.error('获取主机内存使用率失败！')
            return host_list
        except Exception as e:
            # 若发生其他异常，记录错误信息并返回原主机列表
            logger.error(e)
            logger.error('获取主机内存使用率失败！')
            return host_list

    def get_host_root_disk_usage(self, host_list):
        """
        获取指定主机磁盘根分区使用率

        :param host_list: 主机列表，每个元素为包含主机信息的字典
        :return: 更新了根分区使用率和状态信息的主机列表
        """
        # 构造查询主机磁盘根分区使用率的 Prometheus API URL
        query_url = f'{self.prometheus_api_query_url}(node_filesystem_size_bytes{{mountpoint="/"}} - ' \
                    f'node_filesystem_free_bytes{{mountpoint="/",fstype!="rootfs"}}) / ' \
                    f'(node_filesystem_avail_bytes{{mountpoint="/"}}-node_filesystem_free_bytes{{mountpoint="/"}} - ' \
                    f'(-node_filesystem_size_bytes{{mountpoint="/"}}))*100'
        # print(query_url)

        try:
            # 发送 GET 请求获取主机磁盘根分区使用率数据
            get_root_disk_response = requests.get(
                url=query_url, headers=self.headers, auth=self.basic_auth)
            if get_root_disk_response.status_code == 200:
                # 若请求成功，将响应内容解析为 JSON 格式
                root_disk_usage_dict = get_root_disk_response.json()
                if root_disk_usage_dict.get('status') != 'success':
                    # 若获取数据失败，记录错误信息并返回原主机列表
                    logger.error(get_root_disk_response.text)
                    logger.error('获取主机磁盘根分区使用率失败！')
                    return host_list
                for index, host in enumerate(host_list.copy()):
                    for item in root_disk_usage_dict.get('data').get('result'):
                        if item.get('metric').get('instance') == host.get('ip'):
                            # 若找到匹配的主机 IP，更新该主机的根分区使用率和状态信息
                            host_list[index]['root_disk_usage'] = math.ceil(
                                float(item.get('value')[1]))
                            host_list[index]['root_disk_status'] = self.get_host_metric_status('root_disk', math.ceil(
                                float(item.get('value')[1])))
                            break
                        # 若未找到匹配的主机 IP，将根分区使用率和状态信息置为 None
                        host_list[index]['root_disk_usage'] = None
                        host_list[index]['root_disk_status'] = None  # TODO
                return host_list
            else:
                # 若请求失败，记录错误信息并返回原主机列表
                logger.error(get_root_disk_response.text)
                logger.error('获取主机磁盘根分区使用率失败！')
                return host_list
        except requests.ConnectionError as e:
            # 若发生连接错误，记录错误信息并返回原主机列表
            logger.error(e)
            logger.error('获取主机磁盘根分区使用率失败！')
            return host_list
        except Exception as e:
            # 若发生其他异常，记录错误信息并返回原主机列表
            logger.error(e)
            logger.error('获取主机磁盘根分区使用率失败！')
            return host_list

    def get_host_data_disk_usage(self, host_list):
        """
        获取指定主机磁盘数据分区使用率

        :param host_list: 主机列表，每个元素为包含主机信息的字典
        :return: 更新了数据分区使用率和状态信息的主机列表
        """
        for index, host in enumerate(host_list.copy()):
            # 获取主机 IP
            host_ip = host.get('ip')
            # 获取主机数据目录
            host_data_disk = host.get('data_folder')
            # 构造查询主机磁盘数据分区使用率的 Prometheus API URL
            query_url = f'{self.prometheus_api_query_url}' \
                        f'(node_filesystem_size_bytes{{mountpoint="{host_data_disk}",instance="{host_ip}"}} - ' \
                        f'node_filesystem_free_bytes{{mountpoint="{host_data_disk}",instance="{host_ip}"}}) / ' \
                        f'(node_filesystem_avail_bytes{{mountpoint="{host_data_disk}",instance="{host_ip}"}} - ' \
                        f'node_filesystem_free_bytes{{mountpoint="{host_data_disk}",instance="{host_ip}"}} - ' \
                        f'(-node_filesystem_size_bytes{{mountpoint="{host_data_disk}",instance="{host_ip}"}}))*100'
            try:
                # 发送 GET 请求获取主机磁盘数据分区使用率数据
                get_data_disk_response = requests.get(
                    url=query_url, headers=self.headers, auth=self.basic_auth)
                if get_data_disk_response.status_code == 200:
                    # 若请求成功，将响应内容解析为 JSON 格式
                    data_disk_usage_dict = get_data_disk_response.json()
                    if data_disk_usage_dict.get('status') != 'success':
                        # 若获取数据失败，记录错误信息并继续下一个主机的查询
                        logger.error(get_data_disk_response.text)
                        logger.error('获取主机磁盘数据分区使用率失败！')
                        continue
                    if not data_disk_usage_dict.get('data').get('result'):
                        # 若未获取到数据，将数据分区使用率和状态信息置为 None
                        host_list[index]['data_disk_usage'] = None
                        host_list[index]['data_disk_status'] = None
                    for item in data_disk_usage_dict.get('data').get('result'):
                        if item.get('metric').get('instance') == host.get('ip'):
                            # 若找到匹配的主机 IP，更新该主机的数据分区使用率和状态信息
                            host_list[index]['data_disk_usage'] = math.ceil(
                                float(item.get('value')[1]))
                            host_list[index]['data_disk_status'] = self.get_host_metric_status('data_disk', math.ceil(
                                float(item.get('value')[1])),data_dir=host_data_disk)
                            break
                        # 若未找到匹配的主机 IP，将数据分区使用率和状态信息置为 None
                        host_list[index]['data_disk_usage'] = None
                        host_list[index]['data_disk_status'] = None
                else:
                    # 若请求失败，记录错误信息并继续下一个主机的查询
                    logger.error(get_data_disk_response.text)
                    logger.error('获取主机磁盘数据分区使用率失败！')
                    continue
            except requests.ConnectionError as e:
                # 若发生连接错误，记录错误信息并继续下一个主机的查询
                logger.error(e)
                logger.error('获取主机磁盘数据分区使用率失败！')
                continue
            except Exception as e:
                # 若发生其他异常，记录错误信息并继续下一个主机的查询
                logger.error(e)
                logger.error('获取主机磁盘数据分区使用率失败！')
                continue
        return host_list

    def get_host_info(self, host_list):
        """
        获取主机负载基本信息

        :param host_list: 主机列表，每个元素为包含主机信息的字典
        :return: 更新了 CPU、内存、根分区和数据分区使用率及状态信息的主机列表
        """
        for index, host in enumerate(host_list.copy()):
            # 初始化主机的 CPU、内存、根分区和数据分区使用率及状态信息为 None
            host_list[index]['cpu_usage'] = None
            host_list[index]['cpu_status'] = None
            host_list[index]['mem_usage'] = None
            host_list[index]['mem_status'] = None
            host_list[index]['root_disk_usage'] = None
            host_list[index]['root_disk_status'] = None
            host_list[index]['data_disk_usage'] = None
            host_list[index]['data_disk_status'] = None
        # 调用 get_host_cpu_usage 方法更新主机 CPU 使用率和状态信息
        host_list = self.get_host_cpu_usage(host_list)
        # 调用 get_host_mem_usage 方法更新主机内存使用率和状态信息
        host_list = self.get_host_mem_usage(host_list)
        # 调用 get_host_root_disk_usage 方法更新主机根分区使用率和状态信息
        host_list = self.get_host_root_disk_usage(host_list)
        # 调用 get_host_data_disk_usage 方法更新主机数据分区使用率和状态信息
        host_list = self.get_host_data_disk_usage(host_list)
        return host_list

    def get_all_service_status(self):
        """
        获取服务状态  0-运行; 1-停止

        :return: 元组，第一个元素为布尔值表示是否成功，第二个元素为包含服务状态信息的字典
        """
        # 构造查询服务状态的 Prometheus API URL
        query_url = f'{self.prometheus_api_query_url}probe_success'
        try:
            # 发送 GET 请求获取服务状态数据
            res_body = requests.get(
                url=query_url, headers=self.headers, auth=self.basic_auth)
            # 将响应内容解析为 JSON 格式
            res_dic = json.loads(res_body.text)
            if res_dic.get("status") != "success":
                # 若获取数据失败，返回失败标志和空字典
                return False, {}
            # 获取服务状态数据列表
            service_data = res_dic.get("data", {}).get("result", [])
            # 初始化服务状态字典
            service_status_dic = dict()
            for item in service_data:
                # 获取服务指标信息
                metric = item.get("metric", {})
                if metric.get("service_type") != "service":
                    continue
                # 构造服务状态字典的键
                _key = metric.get("instance", "") + "_" + \
                    metric.get("instance_name", "")
                # 根据查询结果判断服务是否运行
                _value = True if int(
                    item.get("value", [0, 0])[-1]) == 1 else False
                # 更新服务状态字典
                service_status_dic[_key] = _value
            return True, service_status_dic
        except Exception as e:
            # 若发生异常，记录错误信息并返回失败标志和空字典
            logger.error(f"从prometheus获取数据失败: {str(e)}")
            return False, {}

    def get_all_host_targets(self):
        """
        获取所有主机的 targets 信息

        :return: 元组，第一个元素为布尔值表示是否成功，第二个元素为包含主机 targets 信息的列表
        """
        # 构造查询主机 targets 信息的 Prometheus API URL
        query_url = f'{self.basic_url}/api/v1/targets'
        # 初始化主机 targets 列表
        host_targets = list()
        try:
            # 发送 GET 请求获取主机 targets 信息
            res_body = requests.get(url=f"http://{query_url}", headers=self.headers, auth=self.basic_auth)  # NOQA
            # 将响应内容解析为 JSON 格式
            res_dic = json.loads(res_body.text)
            if res_dic.get("status") != "success":
                # 若获取数据失败，返回失败标志和空字典
                return False, {}
            # 获取活动 targets 数据列表
            targets_data = res_dic.get("data", {}).get("activeTargets")
            for item in targets_data:
                if item.get("labels", {}).get("job") != "nodeExporter":
                    continue
                # 将符合条件的主机 instance 信息添加到主机 targets 列表中
                host_targets.append(item.get("labels").get("instance"))
            return True, host_targets
        except Exception as e:
            # 若发生异常，记录错误信息并返回失败标志和空列表
            logger.error(f"从prometheus获取主机targets失败: {str(e)}")
            return False, []

    def get_all_service_targets(self):
        """
        获取所有服务的 targets 信息

        :return: 元组，第一个元素为布尔值表示是否成功，第二个元素为包含服务 targets 信息的列表
        """
        # 构造查询服务 targets 信息的 Prometheus API URL
        query_url = f'{self.basic_url}/api/v1/targets'
        # 初始化服务 targets 列表
        service_targets = list()
        try:
            # 发送 GET 请求获取服务 targets 信息
            res_body = requests.get(url=f"http://{query_url}", headers=self.headers, auth=self.basic_auth)  # NOQA
            # 将响应内容解析为 JSON 格式
            res_dic = json.loads(res_body.text)
            if res_dic.get("status") != "success":
                # 若获取数据失败，返回失败标志和空字典
                return False, {}
            # 获取活动 targets 数据列表
            targets_data = res_dic.get("data", {}).get("activeTargets")
            for item in targets_data:
                if item.get("labels", {}).get("service_type") != "service":
                    continue
                # 将符合条件的服务 instance 和 instance_name 信息添加到服务 targets 列表中
                service_targets.append(
                    f'{item.get("labels").get("instance")}_{item.get("labels").get("instance_name")}')
            return True, service_targets
        except Exception as e:
            # 若发生异常，记录错误信息并返回失败标志和空列表
            logger.error(f"从prometheus获取服务targets失败: {str(e)}")
            return False, []

    @staticmethod
    def get_service_threshold(env_id=1):
        """
        获取服务各项指标的阈值，当前使用默认值

        :param env_id: 环境 ID，默认为 1
        :return: 包含服务各项指标阈值的字典
        """
        # 定义服务各项指标的默认阈值
        service_threshold = {
            'cpu': (80, 90),
            'mem': (80, 90)
        }
        # try:
        #     from db_models.models import ServiceThreshold
        #     cpu_warning_st = ServiceThreshold.objects.filter(env_id=env_id, index_type="service_cpu_used",
        #                                                      alert_level="warning").first()
        #     cpu_critical_st = ServiceThreshold.objects.filter(env_id=env_id, index_type="service_cpu_used",
        #                                                       alert_level="critical").first()
        #     mem_warning_st = ServiceThreshold.objects.filter(env_id=env_id, index_type="service_memory_used",
        #                                                      alert_level="warning").first()
        #     mem_critical_st = ServiceThreshold.objects.filter(env_id=env_id, index_type="service_memory_used",
        #                                                       alert_level="critical").first()
        #     service_threshold.update(
        #         cpu=(
        #             int(cpu_warning_st.condition_value) if cpu_warning_st else 0,
        #             int(cpu_critical_st.condition_value) if cpu_critical_st else 100,
        #         ),
        #         mem=(
        #             int(mem_warning_st.condition_value) if mem_warning_st else 0,
        #             int(mem_critical_st.condition_value) if mem_critical_st else 100,
        #         )
        #     )
        # except Exception as e:
        #     logger.error(f"获取服务阈值失败，详情为：{e}")
        return service_threshold

    def get_service_metric_status(self, metric, metric_value):
        """
        根据服务指标值和阈值判断服务指标的状态。

        :param metric: 指标名称，如 'cpu', 'mem' 等
        :param metric_value: 指标值
        :return: 指标状态，'normal', 'warning' 或 'critical'
        """
        if metric_value is None:
            # 若指标值为空，返回 None
            return None
        # 调用 get_service_threshold 方法获取服务各项指标的阈值
        service_threshold = self.get_service_threshold()
        if metric_value > max(service_threshold.get(metric)):
            # 若指标值大于阈值中的最大值，状态为严重
            status = 'critical'
        elif metric_value < min(service_threshold.get(metric)):
            # 若指标值小于阈值中的最小值，状态为正常
            status = 'normal'
        else:
            # 否则，状态为警告
            status = 'warning'
        return status

    def get_service_cpu_usage(self, service_list):
        """
        获取服务cpu使用率

        :param service_list: 服务列表，每个元素为包含服务信息的字典
        :return: 更新了 CPU 使用率和状态信息的服务列表
        """
        # 构造查询开源服务 CPU 使用率的 Prometheus API URL
        open_source_query_url = f'{self.prometheus_api_query_url}service_process_cpu_percent'
        # 构造查询自研服务 CPU 使用率的 Prometheus API URL
        self_service_query_url = f'{self.prometheus_api_query_url}process_cpu_usage * 100'
        try:
            # 发送 GET 请求获取开源服务 CPU 使用率数据
            os_cpu_response = requests.get(
                url=open_source_query_url, headers=self.headers, auth=self.basic_auth)
            if os_cpu_response.status_code == 200:
                # 若请求成功，将响应内容解析为 JSON 格式
                os_cpu_usage_dict = os_cpu_response.json()
                if os_cpu_usage_dict.get('status') != 'success':
                    # 若获取数据失败，记录错误信息并返回原服务列表
                    logger.error(os_cpu_response.text)
                    logger.error('获取开源服务CPU使用率失败！')
                    return service_list
                for index, os_service in enumerate(service_list.copy()):
                    if os_service.get('app_name') == 'hadoop':
                        # 若服务为 Hadoop，调整 app_name
                        os_service['app_name'] = os_service.get(
                            'service_instance_name', 'hadoop').split('_')[0]
                    for item in os_cpu_usage_dict.get('data').get('result'):
                        if item.get('metric').get('instance') == os_service.get('ip') \
                                and item.get('metric').get('app') == os_service.get('app_name') \
                                and item.get('metric').get('env') == os_service.get('env'):
                            # 若找到匹配的服务信息，更新该服务的 CPU 使用率和状态信息
                            service_list[index]['cpu_usage'] = math.ceil(
                                float(item.get('value')[1]))
                            service_list[index]['cpu_status'] = self.get_service_metric_status('cpu', math.ceil(
                                float(item.get('value')[1])))
                            service_list[index]['has_cpu_value'] = 1
                            break
                        # 若未找到匹配的服务信息，将 CPU 使用率和状态信息置为 None
                        service_list[index]['cpu_usage'] = None
                        service_list[index]['cpu_status'] = None  # TODO  待阈值判断

            else:
                # 若请求失败，记录错误信息
                logger.error(os_cpu_response.text)
                logger.error('获取开源服务CPU使用率失败！')

            # 发送 GET 请求获取自研服务 CPU 使用率数据
            ss_cpu_response = requests.get(
                url=self_service_query_url, headers=self.headers, auth=self.basic_auth)
            if ss_cpu_response.status_code == 200:
                # 若请求成功，将响应内容解析为 JSON 格式
                ss_cpu_usage_dict = ss_cpu_response.json()
                if ss_cpu_usage_dict.get('status') != 'success':
                    # 若获取数据失败，记录错误信息并返回原服务列表
                    logger.error(ss_cpu_response.text)
                    logger.error('获取自研服务CPU使用率失败！')
                    return service_list
                for index, ss_service in enumerate(service_list.copy()):
                    if ss_service.get('has_cpu_value', 0) == 1:
                        continue
                    for item in ss_cpu_usage_dict.get('data').get('result'):
                        if item.get('metric').get('instance') == ss_service.get('ip') \
                                and item.get('metric').get('job') == f"{ss_service.get('app_name')}Exporter" \
                                and item.get('metric').get('env') == ss_service.get('env'):
                            # 若找到匹配的服务信息，更新该服务的 CPU 使用率和状态信息
                            service_list[index]['cpu_usage'] = math.ceil(
                                float(item.get('value')[1]))
                            service_list[index]['cpu_status'] = self.get_service_metric_status('cpu', math.ceil(
                                float(item.get('value')[1])))
                            break
                        # 若未找到匹配的服务信息，将 CPU 使用率和状态信息置为 None
                        service_list[index]['cpu_usage'] = None
                        service_list[index]['cpu_status'] = None  # TODO  待阈值判断

            else:
                # 若请求失败，记录错误信息
                logger.error(os_cpu_response.text)
                logger.error('获取自研服务CPU使用率失败！')
            return service_list
        except Exception as e:
            # 若发生异常，记录错误信息并返回原服务列表
            logger.error(f'获取服务cpu使用率失败，报错信息为：{e}')
            return service_list

    def get_service_mem_usage(self, service_list):
        """
        获取服务内存使用率

        :param service_list: 服务列表，每个元素为包含服务信息的字典
        :return: 更新了内存使用率和状态信息的服务列表
        """
        # 构造查询开源服务内存使用率的 Prometheus API URL
        open_source_query_url = f'{self.prometheus_api_query_url}service_process_memory_percent'
        # 构造查询 JVM 内存总量的 Prometheus API URL
        jvm_total_bytes_query_url = f'{self.prometheus_api_query_url}sum(jvm_memory_max_bytes{{area="heap"}}) by (instance,job,application,env)'
        # 构造查询主机内存总量的 Prometheus API URL
        node_total_bytes_query_url = f'{self.prometheus_api_query_url}node_memory_MemTotal_bytes'
        try:
            # 发送 GET 请求获取开源服务内存使用率数据
            os_mem_response = requests.get(
                url=open_source_query_url, headers=self.headers, auth=self.basic_auth)
            if os_mem_response.status_code == 200:
                # 若请求成功，将响应内容解析为 JSON 格式
                os_mem_usage_dict = os_mem_response.json()
                if os_mem_usage_dict.get('status') != 'success':
                    # 若获取数据失败，记录错误信息并返回原服务列表
                    logger.error(os_mem_response.text)
                    logger.error('获取开源服务内存使用率失败！')
                    return service_list
                for index, os_service in enumerate(service_list.copy()):
                    # 初始化服务的内存使用率和状态信息为 None
                    service_list[index]['mem_usage'] = None
                    service_list[index]['mem_status'] = None
                    for item in os_mem_usage_dict.get('data').get('result'):
                        if item.get('metric').get('instance') == os_service.get('ip') \
                                and item.get('metric').get('app') == os_service.get('app_name') \
                                and item.get('metric').get('env') == os_service.get('env'):
                            # 若找到匹配的服务信息，更新该服务的内存使用率和状态信息
                            service_list[index]['mem_usage'] = math.ceil(
                                float(item.get('value')[1]))
                            service_list[index]['mem_status'] = self.get_service_metric_status('mem', math.ceil(
                                float(item.get('value')[1])))
                            service_list[index]['has_mem_value'] = 1
                            break
                        # service_list[index]['mem_usage'] = None
                        # service_list[index]['mem_status'] = None

            else:
                # 若请求失败，记录错误信息
                logger.error(os_mem_response.text)
                logger.error('获取开源服务内存使用率失败！')

            # 发送 GET 请求获取 JVM 内存总量数据
            jtb_response = requests.get(
                url=jvm_total_bytes_query_url, headers=self.headers, auth=self.basic_auth)
            if jtb_response.status_code == 200:
                # 若请求成功，将响应内容解析为 JSON 格式
                jtb_dict = jtb_response.json()
                if jtb_dict.get('status') != 'success':
                    # 若获取数据失败，记录错误信息并返回原服务列表
                    logger.error(jtb_response.text)
                    logger.error('获取自研服务内存使用量失败！')
                    return service_list
            else:
                # 若请求失败，记录错误信息并返回原服务列表
                logger.error(os_mem_response.text)
                logger.error('获取自研服务内存使用率失败！')
                return service_list

            # 发送 GET 请求获取主机内存总量数据
            ntb_response = requests.get(
                url=node_total_bytes_query_url, headers=self.headers, auth=self.basic_auth)
            if ntb_response.status_code == 200:
                # 若请求成功，将响应内容解析为 JSON 格式
                ntb_dict = ntb_response.json()
                if ntb_dict.get('status') != 'success':
                    # 若获取数据失败，记录错误信息并返回原服务列表
                    logger.error(ntb_response.text)
                    logger.error('获取自研服务内存使用量失败！')
                    return service_list
            else:
                # 若请求失败，记录错误信息并返回原服务列表
                logger.error(os_mem_response.text)
                logger.error('获取主机内存资源量失败！')
                return service_list

            for index, ss_service in enumerate(service_list.copy()):
                if ss_service.get('has_mem_value', 0) == 1:
                    continue
                for item in jtb_dict.get('data').get('result'):
                    for ele in ntb_dict.get('data').get('result'):
                        if item.get('metric').get('instance') == ss_service.get('ip') \
                                and item.get('metric').get('instance') == ele.get('metric').get('instance') \
                                and item.get('metric').get('job') == f"{ss_service.get('app_name')}Exporter" \
                                and item.get('metric').get('env') == ss_service.get('env'):
                            # 若找到匹配的服务信息，计算并更新该服务的内存使用率和状态信息
                            service_list[index]['mem_usage'] = math.ceil(
                                float(item.get('value')[1]) / float(ele.get('value')[1]) * 100)
                            service_list[index]['mem_status'] = self.get_service_metric_status('mem',
                                                                                               service_list[index][
                                                                                                   'mem_usage'])
                            break
            return service_list
        except Exception as e:
            # 若发生异常，记录错误信息并返回原服务列表
            logger.error(f'获取服务mem使用率失败，报错信息为：{e}')
            return service_list

    def get_service_info(self, service_list):
        """
        获取服务负载基本信息

        :param service_list: 服务列表，每个元素为包含服务信息的字典
        :return: 更新了 CPU 和内存使用率及状态信息的服务列表
        """
        for index, service in enumerate(service_list.copy()):
            # 初始化服务的 CPU 和内存使用率及状态信息为 None
            service_list[index]['cpu_usage'] = None
            service_list[index]['cpu_status'] = None
            service_list[index]['mem_usage'] = None
            service_list[index]['mem_status'] = None
        # 调用 get_service_cpu_usage 方法更新服务 CPU 使用率和状态信息
        service_list = self.get_service_cpu_usage(service_list)
        # 调用 get_service_mem_usage 方法更新服务内存使用率和状态信息
        service_list = self.get_service_mem_usage(service_list)
        return service_list

    def get_quota_res(self,quota):
        """
        获取指标结果

        :param quota: Prometheus 查询指标
        :return: 元组，第一个元素为布尔值表示是否成功，第二个元素为查询结果或错误信息
        """
        # 构造查询指标结果的 Prometheus API URL
        query_url = f"{self.prometheus_api_query_url}{quota}"
        try:
            # 发送 GET 请求获取指标结果数据
            response = requests.get(
                    url=query_url, headers=self.headers, auth=self.basic_auth)
            if response.status_code != 200:
                # 若请求失败，记录错误信息并返回失败标志和错误信息
                logger.error(f"测试promsql错误: 状态码为{response.status_code} 错误{response.text}")
                return False, response.text
            print(query_url,response.json())
            if response.json().get("status") == "success":
                # 若查询成功，返回成功标志和查询结果
                return True, response.json()["data"]["result"]
            # 若查询失败，返回失败标志和错误信息
            return False, response.text
        except Exception as e:
            # 若发生异常，记录错误信息并返回失败标志和错误信息
            logger.error(f"测试promsql错误：{e}")
            return False, "访问prometheus错误"


class UpdatePrometheusRule(object):
    """
    更新prometheus的配置文件
    """