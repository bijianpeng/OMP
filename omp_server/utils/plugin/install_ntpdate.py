# -*- coding:utf-8 -*-
# Project: instanll_ntpdate
# Create time: 2022/2/23 1:32 下午
import os
import yaml
import logging
from utils.plugin.salt_client import SaltClient
from concurrent.futures import ThreadPoolExecutor
from omp_server.settings import PROJECT_DIR

# 获取名为 "server" 的日志记录器
logger = logging.getLogger("server")


class InstallNtpdate(object):
    def __init__(self, host_obj_list=None):
        """
        初始化 InstallNtpdate 类

        :param host_obj_list: 主机对象列表，用于指定要安装 ntpdate 的主机
        """
        # 检查 host_obj_list 是否为列表类型，若不满足条件则记录错误日志并抛出异常
        if not host_obj_list or not isinstance(host_obj_list, list):
            logger.error("host_obj_list must be type of list")
            raise TypeError("host_obj_list must be type of list!")
        self.host_obj_list = host_obj_list
        # 初始化 SaltClient 实例，用于与 Salt 服务交互
        self.salt_client = SaltClient()
        # 定义要安装的软件名称
        self.name = "ntpdate"
        # 存储 ntpdate 源码包的名称
        self.ntpdate_package_name = ""
        # 配置文件的路径
        self.config_path = os.path.join(PROJECT_DIR, "config/omp.yaml")
        # 软件包仓库目录的路径
        self.package_hub_dir = os.path.join(PROJECT_DIR, "package_hub")
        # 检查 ntpdate 源码包是否存在
        self.check_ntpdate_package()

    def check_ntpdate_package(self):
        """
        检查 ntpdate 源码包是否存在于软件包仓库目录中
        若存在，则将其名称赋值给 self.ntpdate_package_name
        """
        for file in os.listdir(self.package_hub_dir):
            if file.startswith(self.name) and file.endswith("tar.gz"):
                self.ntpdate_package_name = file
                break

    def get_config_dic(self):
        """
        获取配置文件中的详细信息

        :return: 配置文件内容解析后的字典
        """
        with open(self.config_path, "r", encoding="utf8") as fp:
            return yaml.load(fp, Loader=yaml.FullLoader)

    def get_run_user(self):
        """
        从配置文件中获取运行用户信息

        :return: 运行用户名称
        """
        return self.get_config_dic().get("global_user")

    @staticmethod
    def execute(host_obj_lst, thread_name_prefix, func):
        """
        使用线程池并发执行指定函数

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
        for item in host_obj_lst:
            # 向线程池提交任务
            future = thread_p.submit(func, item)
            futures_list.append((item.ip, future))
        # result_list: 存储元组 (ip, res_bool, res_msg) 的列表，用于记录每个主机的执行结果
        result_list = list()
        for f in futures_list:
            result_list.append((f[0], f[1].result()[0], f[1].result()[1]))
        # 关闭线程池，等待所有任务完成
        thread_p.shutdown(wait=True)
        error_msg = ""
        for el in result_list:
            if not el[1]:
                # 若执行失败，将错误信息添加到 error_msg 中
                error_msg += \
                    f"{el[0]}: (execute_flag: {el[1]}; execute_msg: {el[2]});"
        if error_msg:
            return False, error_msg
        return True, "success!"

    def _install_ntpdate(self, host_obj):
        """
        在指定主机上安装 ntpdate

        :param host_obj: 主机对象，包含主机的相关信息
        :return: 元组，第一个元素为布尔值表示安装是否成功，第二个元素为安装消息
        """
        # 检查 ntpdate 源码包是否存在
        if not self.ntpdate_package_name:
            logger.error("ntpdate_package not existed!")
            return False, "ntpdate_package not existed!"
        # 设置主机的 ntpdate 安装状态为安装中
        host_obj.ntpdate_install_status = 2
        host_obj.save()
        # 获取主机的 Agent 目录
        agent_dir = host_obj.agent_dir
        # 应用程序目录
        app_dir = os.path.join(agent_dir, "app")
        # 目标软件包路径
        target_package_path = os.path.join(app_dir, self.ntpdate_package_name)
        # 数据目录
        data_dir = os.path.join(agent_dir, "appData")
        # 日志目录
        log_dir = os.path.join(agent_dir, "logs")
        # ntpdate 定时任务脚本路径
        ntpdate_cron_path = os.path.join(app_dir, f"{self.name}/scripts/{self.name}_cron.sh")
        # ntpdate 脚本路径
        scripts_path = os.path.join(app_dir, f"{self.name}/scripts/{self.name}")
        # 1. 发送 ntpdate 源码包到目标主机
        send_flag, send_msg = self.salt_client.cp_file(
            target=host_obj.ip,
            source_path=self.ntpdate_package_name,
            target_path=target_package_path,
            makedirs=True
        )
        logger.info(
            f"send ntpdate packages,send_flag: {send_flag}; send_msg: {send_msg}"
        )
        if not send_flag:
            return send_flag, send_msg
        # 2. 解压缩、安装并启动 ntpdate
        cmd_flag, cmd_msg = self.salt_client.cmd(
            target=host_obj.ip,
            command=f"(test -d {app_dir}|| mkdir -p {app_dir})&&"
                    f"(test -d {data_dir}|| mkdir -p {data_dir})&&"
                    f"(test -d {log_dir}|| mkdir -p {log_dir})&&"
                    f"cd {app_dir} &&"
                    f" tar -xmf {self.ntpdate_package_name} &&"
                    f" /bin/rm -rf {self.ntpdate_package_name} &&"
                    rf"sed -i -e 's#\${{CW_INSTALL_APP_DIR}}#{app_dir}#g' -e 's#\${{CW_NTP_ADDRESS}}#{host_obj.ntpd_server}#g' {ntpdate_cron_path} &&"
                    rf"sed -i -e 's#\${{CW_INSTALL_APP_DIR}}#{app_dir}#g' -e 's#\${{CW_INSTALL_LOGS_DIR}}#{log_dir}#g' -e 's#\${{CW_INSTALL_DATA_DIR}}#{data_dir}#g' -e's#\${{CW_RUN_USER}}#{self.get_run_user()}#g' {scripts_path};"
                    f"bash {scripts_path} start",
            timeout=120
        )
        logger.info(f"install ntpdate cmd, cmd_flag: {cmd_flag};cmd_msg: {cmd_msg}")
        if not cmd_flag:
            # 若安装失败，设置主机的 ntpdate 安装状态为安装失败
            host_obj.ntpdate_install_status = 3
            host_obj.save()
            return cmd_flag, cmd_msg
        # 若安装成功，设置主机的 ntpdate 安装状态为安装成功
        host_obj.ntpdate_install_status = 0
        host_obj.save()
        return True, "success"

    def install(self):
        """
        在初始化时指定的所有主机上并发安装 ntpdate

        :return: 元组，第一个元素为布尔值表示安装是否成功，第二个元素为安装消息
        """
        return self.execute(host_obj_lst=self.host_obj_list, thread_name_prefix="install_", func=self._install_ntpdate)
