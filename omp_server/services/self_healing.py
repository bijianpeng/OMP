# 导入日志记录模块，用于记录程序运行过程中的信息
import logging
# 导入深拷贝模块，用于复制对象
import copy
# 导入时间模块，用于处理时间相关操作
import time
# 导入 Paramiko 库，用于 SSH 连接和操作
import paramiko
# 导入 Requests 库，用于发送 HTTP 请求
import requests
# 导入 JSON 模块，用于处理 JSON 数据
import json
# 导入日期时间模块，用于处理日期和时间
import datetime
# 从数据库模型模块导入所需的模型类
from db_models.models import Service, SelfHealingSetting, \
    SelfHealingHistory, Host, WaitSelfHealing, ApplicationHub
# 从 Celery 库导入共享任务装饰器，用于定义异步任务
from celery import shared_task
# 从监控模块导入 CW_TOKEN，可能用于身份验证
from promemonitor.prometheus_utils import CW_TOKEN
# 从工具插件模块导入 Salt 客户端类，用于执行 Salt 命令
from utils.plugin.salt_client import SaltClient
# 从工具插件模块导入 AES 加密器类，用于数据加密和解密
from utils.plugin.crypto import AESCryptor
# 从并发执行模块导入线程池执行器和异步结果获取函数
from concurrent.futures import (
    ThreadPoolExecutor, as_completed
)
# 从配置解析工具模块导入配置信息
from utils.parse_config import MONITOR_PORT, BASIC_ORDER, \
    THREAD_POOL_MAX_WORKERS, HEALTH_REDIS_TIMEOUT, HEALTH_REQUEST_COUNT, HEALTH_REQUEST_SLEEP
# 从应用商店模块导入 Redis 数据库类
from app_store.new_install_utils import RedisDB
# 从工具插件模块导入维护装饰器
from utils.plugin.crontab_utils import maintain

# 获取名为 'server' 的日志记录器
logger = logging.getLogger('server')


class SelfHealing:
    def __init__(self, instance_tp, max_healing_count):
        # 需要起停信息ip等操作
        # 自愈实例类型
        self.instance_tp = instance_tp
        # 最大自愈次数
        self.max_healing_count = max_healing_count
        # 初始化 Redis 数据库实例
        self.redis = RedisDB()
        # 存储服务信息的集合
        self.service_info = set()
        # 存储主机信息的集合
        self.host_info = set()

    def merge_and_filter_ser(self, alert_info):
        """
        初始化用，过滤服务（主机），及服务初始化信息

        :param alert_info: 告警信息列表
        :return: 过滤后的服务信息字典和主机信息列表
        """
        # 存储服务信息的字典
        data_dict = {}
        # 存储主机信息的列表
        host_ls = []
        for d in alert_info:
            # 若告警信息包含服务名称、实例名称且实例名称未在服务信息集合中
            if d.get("alert_service_name") and d.get("alert_instance_name") and \
                    d['alert_instance_name'] not in self.service_info:
                # 将告警信息按服务名称分组添加到 data_dict 中
                data_dict.setdefault(d['alert_service_name'], []).append(d)
                # 将实例名称添加到服务信息集合中
                self.service_info.add(d['alert_instance_name'])
            # 若告警信息不包含服务名称且主机 IP 未在主机信息集合中
            if not d.get("alert_service_name") and \
                    d['alert_host_ip'] not in self.host_info:
                # 将主机 IP 添加到主机信息集合中
                self.host_info.add(d['alert_host_ip'])
                # 将告警信息添加到主机信息列表中
                host_ls.append(d)
        # 初始化主机信息字典，通过查询数据库获取主机 IP 对应的 agent 目录
        self.host_info = dict(Host.objects.filter(
            ip__in=list(self.host_info)).values_list("ip", "agent_dir"))
        # 初始化服务信息字典，通过查询数据库获取服务实例名称对应的服务控制器
        self.service_info = dict(Service.objects.filter(
            service_instance_name__in=list(self.service_info)
        ).values_list("service_instance_name", "service_controllers"))
        return data_dict, host_ls

    def sort_service(self, alert_info):
        """
        初始化用，提供排序

        :param alert_info: 告警信息列表
        :return: 排序后的服务信息列表
        """
        # 复制基础排序顺序
        sort_dict = copy.copy(BASIC_ORDER)
        # 赋值并过滤，获取服务信息字典和主机信息列表
        data_dict, host_ls = self.merge_and_filter_ser(alert_info)
        # 存储排序后的服务信息列表
        sort_ser = []
        for key in sort_dict:
            # 临时存储当前排序组的服务信息
            temp = []
            for item in sort_dict[key]:
                # 将对应服务名称的告警信息添加到临时列表中
                temp.extend(data_dict.pop(item, []))
            if temp:
                # 若临时列表不为空，将其添加到排序后的服务信息列表中
                sort_ser.append(temp)
        # 获取剩余未排序的服务信息
        other_ser = data_dict.values()
        if other_ser:
            # 展平剩余服务信息列表
            other_ser = [service for app in other_ser for service in app]
            # 将剩余服务信息添加到排序后的服务信息列表中
            sort_ser.append(other_ser)
        if host_ls:
            # 若主机信息列表不为空，将其插入到排序后的服务信息列表开头
            sort_ser.insert(0, host_ls)
        return sort_ser

    def exec_salt_cmd(self, ip, command, his_obj):
        """
        进行启动，请求接口查询状态，日志追加，状态变更

        :param ip: 目标主机 IP
        :param command: 要执行的命令
        :param his_obj: 自愈历史记录对象
        :return: 执行结果，成功返回 True，失败返回 False
        """
        # 创建 Salt 客户端实例
        salt_obj = SaltClient()
        # 执行 Salt 命令
        cmd_flag, cmd_msg = salt_obj.cmd(
            target=ip,
            command=command,
            timeout=60)
        # 记录执行日志
        healing_log = f"执行ip:{ip},执行cmd:{command},执行结果:{cmd_flag},执行详情:{cmd_msg},"
        if not cmd_flag:
            # 若命令执行失败，更新自愈历史记录的日志信息并保存
            his_obj.healing_log = healing_log
            his_obj.save()
            return False
        # 循环检测，超出检测次数后退出
        for _ in range(HEALTH_REQUEST_COUNT):
            # 检查服务健康状态
            res = self.check_health(ip, command, his_obj, healing_log)
            if res:
                return True
            # 每次检测间隔一定时间
            time.sleep(HEALTH_REQUEST_SLEEP)
        return False

    @staticmethod
    def check_health(ip, command, his_obj, healing_log):
        """
        检查服务健康状态

        :param ip: 目标主机 IP
        :param command: 执行的命令
        :param his_obj: 自愈历史记录对象
        :param healing_log: 执行日志
        :return: 健康状态，正常返回 True，异常返回 False
        """
        # 构造请求监控的参数
        request_monitor = {"service_name": his_obj.service_name, "ip": ip}
        if "omp_monitor_agent" in command:
            # 若命令包含监控代理，将服务名称设为 node
            request_monitor["service_name"] = "node"
        try:
            # 调用函数获取服务状态
            monitor_agent_res = get_service_status_direct([request_monitor])
        except Exception as e:
            # 若请求监控报错，更新自愈历史记录的日志信息并保存
            his_obj.healing_log = healing_log + ",请求监控报错"
            his_obj.save()
            logger.info("monitor_agent_res_error 监控报错信息{}".format(e))
            return False
        if monitor_agent_res[0].get("status") == 1:
            # 若服务状态正常，更新自愈历史记录的日志信息并保存
            his_obj.healing_log = healing_log + "monitor_agent_res 服务状态查看正常更新服务状态"
            his_obj.save()
            return True
        return False

    def get_command(self, instance_name):
        """
        获取cmd ，通过策略类型选择启动或重启

        :param instance_name: 实例名称
        :return: 要执行的命令
        """
        # 定义策略类型与操作的映射
        action_dc = {
            0: "start",
            1: "restart"
        }
        # 根据自愈实例类型获取操作名称
        action = action_dc[self.instance_tp]
        # 获取服务对应的操作命令
        service_action = self.service_info.get(instance_name)
        # 获取主机对应的操作目录
        host_action = self.host_info.get(instance_name)
        if service_action:
            # 若服务有对应的操作命令，优先使用
            command = service_action.get(action) if service_action.get(action) \
                else service_action.get("start", "").replace("start", action)
        else:
            # 若为主机，构造监控代理操作命令
            command = f"bash {host_action}/omp_monitor_agent/monitor_agent.sh {action}"
        return command

    @staticmethod
    def write_db(data, healing_count):
        """
        合法后创建记录表用

        :param data: 告警信息
        :param healing_count: 自愈次数
        :return: 创建的自愈历史记录对象
        """
        # 初始化自愈历史记录的初始值
        initial_v = {
            "start_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_read": 0,
            "state": 2,
            "healing_log": "",
            "healing_count": healing_count
        }
        # 定义告警信息字段与自愈历史记录字段的映射
        compare_dc = {
            "alert_host_ip": "host_ip",
            "alert_service_name": "service_name",
            "alert_time": "alert_time",
            # "fingerprint": "fingerprint",
            # "monitor_log": "monitor_log",
            "alert_describe": "alert_content",
            "alert_instance_name": "instance_name",
            # 告警信息恒携带 env_id（AlertAnalysis.__call__ 写入，
            # 取自告警关联主机/服务自身），自愈历史按环境落库
            "env_id": "env_id",
        }
        # 存储写入数据库的字段信息
        write_db_dc = {}
        for field, value in data.items():
            # 获取映射后的字段名
            compare_v = compare_dc.get(field)
            if compare_v:
                # 若存在映射，将字段信息添加到 write_db_dc 中
                write_db_dc[compare_v] = value
        # 更新写入数据库的字段信息
        write_db_dc.update(initial_v)
        # 创建自愈历史记录对象并返回
        return SelfHealingHistory.objects.create(**write_db_dc)

    def get_redis_count(self, instance_name):
        """
        缓存校验用，周期内自愈次数最大限制

        :param instance_name: 实例名称
        :return: 当前实例的自愈次数
        """
        # 从 Redis 中获取实例的自愈次数
        _flag, _data = self.redis.get(f"heal{instance_name}")
        if not _flag:
            # 若 Redis 中不存在该实例的自愈次数，初始化为 1
            count = 1
        else:
            # 若存在，将次数加 1
            count = int(_data) + 1
        # 更新 Redis 中该实例的自愈次数
        self.redis.update(
            name=f"heal{instance_name}",
            data=count,
            timeout=HEALTH_REDIS_TIMEOUT
        )
        return count

    def host(self, hosts_info):
        """
        处理主机自愈逻辑

        :param hosts_info: 主机告警信息
        """
        # 识别描述信息
        identify_des = "monitor_agent进程丢失"
        # 获取主机 IP
        ip = hosts_info["alert_host_ip"]
        if identify_des not in hosts_info.get('alert_describe'):
            # 若告警描述不包含识别描述，记录暂不支持的模式信息
            logger.info(f"暂不支持的模式{ip}")
            return True
        # 处理主机 IP ，用于 Redis 键
        host_ip = "".join(ip.split("."))
        # 获取当前主机的自愈次数
        healing_count = self.get_redis_count(host_ip)
        if healing_count > self.max_healing_count:
            # 若自愈次数超出最大限制，记录信息并返回
            logger.info(f"自愈实例超出限制个数{ip}")
            return True
        # 创建自愈历史记录对象
        his_obj = self.write_db(hosts_info, healing_count)
        # 执行 Salt 命令进行自愈
        res = self.exec_salt_cmd(ip, self.get_command(ip), his_obj)
        if not res:
            # 若第一次自愈失败，再次尝试
            res = self.exec_salt_cmd(ip, self.get_command(ip), his_obj)
        # 根据自愈结果更新自愈历史记录的状态
        his_obj.state = SelfHealingHistory.HEALING_SUCCESS if res else SelfHealingHistory.HEALING_FAIL
        # 更新自愈历史记录的结束时间
        his_obj.end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        # 保存自愈历史记录对象
        his_obj.save()

    def service(self, service_info):
        """
        处理服务自愈逻辑

        :param service_info: 服务告警信息
        """
        # 识别描述信息
        identify_des = "been down for more than a minute"
        if identify_des not in service_info.get('alert_describe'):
            # 若告警描述不包含识别描述，记录暂不支持的模式信息
            logger.info(f"暂不支持的模式{service_info['alert_instance_name']}")
            return True
        # 获取当前服务的自愈次数
        healing_count = self.get_redis_count(service_info['alert_instance_name'])
        if healing_count > self.max_healing_count:
            # 若自愈次数超出最大限制，记录信息并返回
            logger.info(f"自愈实例超出限制个数{service_info['alert_instance_name']}")
            return True
        # 创建自愈历史记录对象
        his_obj = self.write_db(service_info, healing_count)
        # 获取要执行的命令
        command = self.get_command(service_info['alert_instance_name'])
        # 执行 Salt 命令进行自愈
        res = self.exec_salt_cmd(service_info['alert_host_ip'], command, his_obj)
        if not res:
            # 若第一次自愈失败，再次尝试
            res = self.exec_salt_cmd(service_info['alert_host_ip'], command, his_obj)
        # 根据自愈结果更新自愈历史记录的状态
        his_obj.state = SelfHealingHistory.HEALING_SUCCESS if res else SelfHealingHistory.HEALING_FAIL
        # 更新自愈历史记录的结束时间
        his_obj.end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        # 保存自愈历史记录对象
        his_obj.save()


def get_enable_health(repairs):
    """
    获取可进行自愈的主机和服务列表

    :param repairs: 已修复的实例列表
    :return: 可进行自愈的实例列表
    """
    # 获取所有主机的 IP 地址
    h_ls = set(Host.objects.all().values_list("ip", flat=True))
    for app in ApplicationHub.objects.filter(is_base_env=False):
        if not app.extend_fields.get("affinity", "") == "tengine":
            # 若应用不是基础环境且亲和性不是 tengine，将应用名称添加到集合中
            h_ls.add(app.app_name)
    # 返回可进行自愈的实例列表
    return list(h_ls - set(repairs))


@shared_task
@maintain
def self_healing(task_id):
    """
    自愈任务的异步函数

    :param task_id: 自愈任务的 ID
    :return: 任务执行结果信息
    """
    # 校验是否需要自愈
    # 获取自愈设置对象
    self_obj = SelfHealingSetting.objects.get(id=task_id)
    if not self_obj.used:
        # 若自愈策略未启用，返回信息
        return "该策略并未启用"
    if "all" in self_obj.repair_instance:
        # 若修复实例包含 'all'，获取所有可进行自愈的实例
        data = self_obj.get_enable_health(list())
    else:
        # 否则，获取指定的修复实例列表
        data = list(self_obj.repair_instance)
    # 获取需要自愈的服务对象
    wait_ser = WaitSelfHealing.objects.filter(service_name__in=data)
    if not wait_ser or wait_ser.filter(repair_status=1):
        # 若不存在需要自愈的服务或存在正在自愈的服务，返回信息
        return "存在正在自愈的服务或无需自愈的服务"
    # 更新需要自愈的服务的修复状态为正在修复
    wait_ser.update(repair_status=1)
    # 获取需要自愈的服务的 ID 和修复信息的字典
    repair_ser_dc = dict(wait_ser.values_list("id", "repair_ser"))

    # 存储需要自愈的服务信息
    repair_info = []
    for ser in repair_ser_dc.values():
        repair_info.append(ser)
    logger.info(f"需要自愈的服务:{repair_info}")
    # 排序 先主机 - 基础组件 - 自研服务
    try:
        # 创建自愈对象
        health_obj = SelfHealing(self_obj.instance_tp, self_obj.max_healing_count)
        # 对需要自愈的服务进行排序
        ser = health_obj.sort_service(repair_info)
        logger.info(f"等待自愈的服务信息:{ser}")
        # 开启修复
        for service_ls in ser:
            # 使用线程池执行自愈任务
            with ThreadPoolExecutor(THREAD_POOL_MAX_WORKERS) as executor:
                future_list = []
                for service in service_ls:
                    # 提交任务到线程池
                    future_obj = executor.submit(
                        getattr(health_obj,
                                "service" if service['alert_type'] == "component" else service['alert_type']), service)
                    future_list.append(future_obj)
                for future in as_completed(future_list):
                    # 获取任务结果
                    future.result()
    except Exception as e:
        logger.info(f"未知异常，需保护释放锁 {e}")
        # 释放锁 ,防止惰性查询再次筛选
    # 删除已处理的等待自愈的服务对象
    WaitSelfHealing.objects.filter(id__in=list(repair_ser_dc)).delete()


def self_healing_ssh_verification(host_self_healing_list, sudo_check_cmd):
    """
        先留着吧暂时没啥用。
        """

    # host_self_healing_list = host_self_healing_list
    aes_crypto = AESCryptor()
    host_list = Host.objects.filter(ip=host_self_healing_list).values_list("ip", "port", "username", "password")
    for i in range(len(host_list)):
        try:
            if len(host_list[i][2]) != 0 and len(host_list[i][3]) != 0:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(hostname=host_list[i][0], port=host_list[i][1],
                               username=host_list[i][2], password=aes_crypto.decode(host_list[i][3]),
                               timeout=60)
                """ 监控启动脚本 是否需要重启多次？"""
                # 执行 sudo 检查命令
                stdin, stdout, stderr = client.exec_command(sudo_check_cmd)
                # 获取标准输出信息
                stdout = stdout.read().decode('utf-8')
                # 获取标准错误信息
                stderr = stderr.read().decode('utf-8')
                """ 输出信息需要修改"""
                if "dead" in stdout:
                    """ 监控未 启动 """
                    logger.info("monitor_agent 启动失败,输出信息:{} ".format(stdout))
                    return True, 0
                if "running" in stdout:
                    """ 监控启动"""
                    return True, 1
            else:
                logger.info("监控重启失败 无ssh")
                """ 无ssh的情况"""
                return False, 0
        except Exception as e:
            logger.info("监控重启失败,报错信息为：{}".format(e))
            """ ssh 连接超时"""
            return False, 1
    return True, 2


def get_service_status_direct(service_obj_list):
    """
    直接从monitor_agent获取服务状态

    :param service_obj_list: 服务对象列表，格式为 [{"ip": "127.0.0.1", "service_name": "mysql"}, {"ip": "127.0.0.1", "service_name": "redis"}]
    :return: 服务状态信息列表
    """
    # 存储服务状态结果的列表
    service_obj_result = list()
    # 获取监控代理的端口号
    monitor_agent_port = MONITOR_PORT.get('monitorAgent', 19031)
    # 请求头的内容类型
    headers_type = {"Content-Type": "application/json"}
    # 请求头的身份验证信息
    headers_authentication = CW_TOKEN
    # 合并请求头信息
    headers = dict(headers_type, **headers_authentication)
    # 存储按 IP 分组的服务对象列表
    ip_item_list = list()
    # 存储所有 IP 地址
    ip_list = list()
    for ele in service_obj_list:
        # 将 IP 地址添加到列表中
        ip_list.append(ele.get("ip"))
    # 去重
    ip_list = list(set(ip_list))
    for ip in ip_list:
        # 存储当前 IP 对应的服务对象列表
        ip_service_list = list()
        for item in service_obj_list:
            if ip == item.get("ip"):
                # 将对应 IP 的服务对象添加到列表中
                ip_service_list.append(item)
        ip_item_list.append(ip_service_list)
    try:
        for ii in ip_item_list:
            # 构造请求监控代理的 URL
            status_url = f"http://{ii[0].get('ip')}:{monitor_agent_port}/service_status"  # NOQA
            # 发送 POST 请求获取服务状态
            response = requests.request(
                "POST", status_url, headers=headers, data=json.dumps(ii))
            logger.info("interface_monitor_agent监控接口返回数据:{}".format(response))
            logger.info("interface_monitor_agent请求地址 {}".format(status_url))
            if response.status_code != 200:
                continue
            logger.info("interface_monitor_agent 接口返回:{}".format(response.json()))
            # 将返回的服务状态信息添加到结果列表中
            service_obj_result.extend(response.json().get("beans"))
        return service_obj_result
    except Exception as e:
        logger.error(f"interface_monitor_agent 获取制定服务列表状态失败，详情为：{e}")
        return service_obj_list
