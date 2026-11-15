# -*- coding: utf-8 -*-
# Project: monitor_agent
# Author: omp
# Create time: 2021-10-07 13:45
# IDE: PyCharm
# Version: 1.0
# Introduction:

"""
安装、卸载、更新monitor agent
"""
# 导入 json 模块，用于处理 JSON 数据
import json
# 导入 os 模块，用于处理文件路径和操作系统相关功能
import os
# 导入 time 模块，用于处理时间相关操作
import time
# 导入 random 模块，用于生成随机数
import random
# 导入 logging 模块，用于记录日志信息
import logging
# 从 concurrent.futures 模块导入 ThreadPoolExecutor 类，用于线程池管理
from concurrent.futures import ThreadPoolExecutor

# 从 db_models.models 模块导入 Host 模型，用于操作主机数据
from db_models.models import Host
# 从 omp_server.settings 模块导入 PROJECT_DIR 变量，获取项目目录
from omp_server.settings import PROJECT_DIR
# 从 promemonitor.prometheus_utils 模块导入 PrometheusUtils 类，用于与 Prometheus 交互
from promemonitor.prometheus_utils import PrometheusUtils
# 从 utils.plugin.salt_client 模块导入 SaltClient 类，用于与 Salt 服务交互
from utils.plugin.salt_client import SaltClient

# 获取名为 "server" 的日志记录器
logger = logging.getLogger("server")


class MonitorAgentManager(object):
    """ 监控Agent的管理类 """

    def __init__(self, host_objs=None):
        """
        初始化方法

        :param host_objs: 主机对象组成的列表
        """
        # 检查 host_objs 是否为列表且不为空，若不满足条件则抛出类型错误异常
        if not host_objs or not isinstance(host_objs, list):
            raise TypeError("host_objs must be a list of host objs!")
        # 定义监控 Agent 的名称
        self.name = "omp_monitor_agent"
        # 存储主机对象列表
        self.host_objs = host_objs
        # 拼接软件包仓库的目录路径
        self.package_hub_dir = os.path.join(PROJECT_DIR, "package_hub")
        # 初始化监控 Agent 源码包的名称
        self.monitor_agent_package_name = ""
        # 检查监控 Agent 源码包是否存在
        self.check_monitor_agent_package()

    def check_monitor_agent_package(self):
        """
        检查monitor agent的源码包是否存在

        :return: None
        """
        # 遍历软件包仓库目录下的所有文件和文件夹
        for item in os.listdir(self.package_hub_dir):
            # 判断文件名是否以监控 Agent 名称开头且以 .tar.gz 结尾
            if item.startswith(self.name) and item.endswith("tar.gz"):
                # 若满足条件，则记录该源码包的名称
                self.monitor_agent_package_name = item
                break

    @staticmethod
    def execute(host_obj_lst, thread_name_prefix, func):
        """
        执行函数，使用线程池并发执行指定函数

        :param host_obj_lst: 主机对象组成的列表
        :param thread_name_prefix: 线程前缀，用于标识线程
        :param func: 执行函数对象，仅接收 host 主机对象参数
        :return: 元组，第一个元素为布尔值表示执行是否成功，第二个元素为执行消息
        """
        # 创建一个最大工作线程数为 20 的线程池
        thread_p = ThreadPoolExecutor(
            max_workers=20, thread_name_prefix=thread_name_prefix)
        # futures_list: 存储元组 (ip, future) 的列表，用于记录每个主机的任务
        futures_list = list()
        # 遍历主机对象列表
        for item in host_obj_lst:
            # 向线程池提交任务
            future = thread_p.submit(func, item)
            # 将主机 IP 和任务对象添加到 futures_list 中
            futures_list.append((item.ip, future))
        # result_list: 存储元组 (ip, res_bool, res_msg) 的列表，用于记录每个主机的执行结果
        result_list = list()
        # 遍历 futures_list
        for f in futures_list:
            # 将主机 IP、任务执行结果的布尔值和消息添加到 result_list 中
            result_list.append((f[0], f[1].result()[0], f[1].result()[1]))
        # 关闭线程池，等待所有任务完成
        thread_p.shutdown(wait=True)
        # 初始化错误消息为空字符串
        error_msg = ""
        # 遍历执行结果列表
        for el in result_list:
            # 若执行失败
            if not el[1]:
                # 将错误信息添加到 error_msg 中
                error_msg += \
                    f"{el[0]}: (execute_flag: {el[1]}; execute_msg: {el[2]});"
        # 若存在错误消息
        if error_msg:
            return False, error_msg
        return True, "success!"

    def _install(self, obj):
        """
        安装函数，在指定主机上安装监控 Agent

        :param obj: 主机对象
        :type obj: Host
        :return: 元组，第一个元素为布尔值表示安装是否成功，第二个元素为安装消息
        """
        # step1: 判断源码包是否存在
        # 若监控 Agent 源码包不存在
        if not self.monitor_agent_package_name:
            return False, "omp_monitor_agent package does not exist!"
        # step2: 发送源码包文件
        # 创建 SaltClient 实例
        salt_obj = SaltClient()
        # 调用 cp_file 方法将源码包发送到目标主机
        send_flag, send_msg = salt_obj.cp_file(
            target=obj.ip,
            source_path=self.monitor_agent_package_name,
            target_path=obj.agent_dir,
            makedirs=False)
        # 记录发送源码包的日志信息
        logger.info(
            f"Send omp_monitor_agent, "
            f"send_flag: {send_flag}; send_msg: {send_msg}")
        # 若发送失败
        if not send_flag:
            return send_flag, send_msg
        # step3: 解压源码包并启动服务
        # 将监控指标认证信息转换为 JSON 字符串，后续需从配置文件读取
        metrics_auth = json.dumps(
            {"username": "mokey", "password": "w7SiYs$oE"})  # TODO  后续从配置文件读取
        # 将服务信息转换为 JSON 字符串
        services_info = json.dumps({"node": {"quotes": [], "exporter_port": 19017, "exporter_metric": "metrics",
                                             "auth_user": "mokey",
                                             "auth_password_encryption": "$2y$12$GThv30aK.STxvx6A32CXVubbveBkEq3vatYTPpuIVTT6uRE24L91O"}})
        # 调用 cmd 方法在目标主机上执行安装和启动命令
        cmd_flag, cmd_res = salt_obj.cmd(
            target=obj.ip,
            command=f"cd {obj.agent_dir} && "
                    f"tar -xmf {self.monitor_agent_package_name} && "
                    f"/bin/rm -rf {self.monitor_agent_package_name} && "
                    f"cd {self.name} && "
                    f"./install --agent_ip={obj.ip} --metrics_auth='{metrics_auth}' --services_info='{services_info}' && "
                    f"bash monitor_agent.sh init &&"
                    f"bash monitor_agent.sh start",
            timeout=120)
        # 记录安装命令执行的日志信息
        logger.info(
            f"Install omp_monitor_agent cmd, "
            f"cmd_flag: {cmd_flag}; cmd_res: {cmd_res}")
        # 安装成功后更新数据库的状态
        # 若安装命令执行失败
        if not cmd_flag:
            # 更新数据库中主机的监控 Agent 状态和错误信息
            Host.objects.filter(ip=obj.ip).update(
                monitor_agent=4,
                monitor_agent_error=str(cmd_res) if len(
                    str(cmd_res)) < 200 else str(cmd_res)[:200]
            )
            return cmd_flag, cmd_res
        # 若安装命令执行成功，更新数据库中主机的监控 Agent 状态和错误信息
        Host.objects.filter(ip=obj.ip).update(
            monitor_agent=0,
            monitor_agent_error=None
        )
        return True, "success"

    def install(self):
        """
        安装monitor agent

        :return: 元组，第一个元素为布尔值表示安装是否成功，第二个元素为安装消息
        """
        # 调用 execute 方法并发安装监控 Agent
        flag, msg = self.execute(
            host_obj_lst=self.host_objs,
            thread_name_prefix="install_",
            func=self._install)
        # 若安装过程中出现错误
        if not flag:
            return flag, msg
        # 更新监控Server端配置，暂时靠sleep解决文件并发操作
        # 随机休眠 1 到 5 秒
        time.sleep(random.randint(1, 5))
        # 创建 PrometheusUtils 实例
        _pro_obj = PrometheusUtils()
        # 调用 add_node 方法添加节点信息
        _pro_obj.add_node(self.parse_hosts_data())
        return True, "success!"

    def parse_hosts_data(self):
        """
        解析主机信息，生成 Prometheus 使用的 target 数据

        :return: 包含主机信息的列表
        """
        # 初始化存储主机信息的列表
        hosts_data = list()
        # 遍历主机对象列表
        for item in self.host_objs:
            # TODO 支持手动添加服务器，暂不支持无SSH
            # 获取主机 IP
            _ip = item.ip
            # 获取主机所属环境标识（Env.code，spec §6.4：进入监控链路的一切 env 字符串均为 Env.code）
            _env = item.env.code
            # 获取主机数据文件夹路径
            _data_folder = item.data_folder
            # 获取主机磁盘信息
            _disk_info = item.disk
            # 若磁盘信息为空
            if not _disk_info:
                # 重新从数据库获取磁盘信息
                _disk_info = Host.objects.get(id=item.id).disk
            # 初始化数据路径为空字符串
            data_path = ""
            # 若磁盘信息存在且为字典类型
            if _disk_info and isinstance(_disk_info, dict):
                # 遍历磁盘信息
                for key, _ in _disk_info.items():
                    # 跳过根目录
                    if key == "/":
                        continue
                    # 若数据文件夹路径以当前磁盘路径开头
                    if _data_folder.startswith(key):
                        # 记录数据路径
                        data_path = key
                        break
            # 将主机信息添加到 hosts_data 列表中
            hosts_data.append({
                "ip": _ip,
                "env": _env,
                "data_path": data_path or _data_folder,
                "instance_name": item.instance_name
            })
        return hosts_data

    def _uninstall(self, obj):
        """
        卸载函数，在指定主机上卸载监控 Agent

        :param obj: 主机对象
        :type obj: Host
        :return: 元组，第一个元素为布尔值表示卸载是否成功，第二个元素为卸载消息
        """
        # 创建 SaltClient 实例
        salt_obj = SaltClient()
        # 拼接监控 Agent 的主目录路径
        monitor_agent_home = os.path.join(obj.agent_dir, self.name)
        # 调用 cmd 方法在目标主机上执行卸载命令
        cmd_flag, cmd_res = salt_obj.cmd(
            target=obj.ip,
            command=f"cd {monitor_agent_home} && "
                    f"./manage stop_all && bash monitor_agent.sh stop && "
                    f"cd {obj.agent_dir} && /bin/rm -rf {self.name}",
            timeout=120)
        # 记录卸载命令执行的日志信息
        logger.info(
            f"Uninstall monitor_agent, "
            f"cmd_flag: {cmd_flag}; cmd_res: {cmd_res}")
        # 若卸载命令执行失败
        if not cmd_flag:
            return cmd_flag, cmd_res
        return True, "success"

    def uninstall(self):
        """
        卸载monitor agent

        :return: 元组，第一个元素为布尔值表示卸载是否成功，第二个元素为卸载消息
        """
        # TODO 需要确定exporter停止脚本使用参数情况
        # 调用 execute 方法并发卸载监控 Agent
        return self.execute(
            host_obj_lst=self.host_objs,
            thread_name_prefix="uninstall_",
            func=self._uninstall)
