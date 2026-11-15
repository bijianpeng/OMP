# -*- coding: utf-8 -*-
# Project: prometheus_utils
# Author: omp
# Create time: 2021-10-11 14:31
# IDE: PyCharm
# Version: 1.0
# Introduction:

"""
prometheus更新监控项使用的工具集
"""

# 导入操作系统相关模块，用于文件和目录操作
import os
# 导入 JSON 模块，用于处理 JSON 数据
import json
# 导入 pickle 模块，用于对象的序列化和反序列化
import pickle
# 导入 shutil 模块，用于高级文件操作，如复制文件
import shutil
# 导入日志记录模块，用于记录程序运行过程中的信息
import logging
# 导入 requests 模块，用于发送 HTTP 请求
import requests
# 导入 hashlib 模块，用于生成哈希值
import hashlib

# import requests
# 导入 yaml 模块，用于处理 YAML 格式的数据
import yaml
# 从 ruamel.yaml 模块导入 YAML 类，用于更灵活地处理 YAML 文件
from ruamel.yaml import YAML

# 从数据库模型模块导入主机阈值、服务自定义阈值、告警规则和环境模型
from db_models.models import HostThreshold, ServiceCustomThreshold, \
    AlertRule, Env
# 从项目设置模块导入项目目录
from omp_server.settings import PROJECT_DIR
# 从配置解析模块导入监控端口、Prometheus 认证信息和 Loki 配置
from utils.parse_config import MONITOR_PORT, PROMETHEUS_AUTH, LOKI_CONFIG

# from utils.parse_config import MONITOR_PORT

# 获取名为 'server' 的日志记录器
logger = logging.getLogger("server")

# 定义 CW 令牌，用于认证
CW_TOKEN = {
    'CWAccessToken': 'FnQGiEXrYr6n8diKuY6cc61Zw3MMyLW9icwiUlHjyoAkBsBKCDIqmDZbf'}

# 定义协议为 HTTP
AGREE = "http"
# 内置 exporter 列表
EXPORTERS = [
    "beanstalk",
    "clickhouse",
    "elasticsearch",
    "httpd",
    "kafka",
    "mysql",
    "node",
    "postgreSql",
    "redis",
    "tengine",
    "zookeeper",
    "rocketmq",
]

# 定义不同服务的指标路径
METRICS = {
    "arangodb": "_admin/metrics",
    "nacos": "nacos/actuator/prometheus",
}


class PrometheusUtils(object):
    """ prometheus工具集 """

    def __init__(self):
        # Prometheus 配置文件路径
        self.prometheus_conf_path = os.path.join(
            PROJECT_DIR, "component/prometheus/conf/prometheus.yml")
        # Prometheus 规则文件目录路径
        self.prometheus_rules_path = os.path.join(
            PROJECT_DIR, "component/prometheus/conf/rules")
        # Prometheus 目标文件目录路径
        self.prometheus_targets_path = os.path.join(
            PROJECT_DIR, "component/prometheus/conf/targets")
        # 主机告警规则模板文件路径
        self.prometheus_node_rule_tpl = os.path.join(
            PROJECT_DIR,
            "package_hub/prometheus_rules_template/node_rule.yml")
        # 主机数据分区告警规则模板文件路径
        self.prometheus_node_data_rule_tpl = os.path.join(
            PROJECT_DIR,
            "package_hub/prometheus_rules_template/node_data_rule.yml")
        # 服务状态告警规则模板文件路径
        self.prometheus_service_status_rule_tpl = os.path.join(
            PROJECT_DIR,
            "package_hub/prometheus_rules_template/service_status_rule.yml")
        # exporter 状态告警规则模板文件路径
        self.prometheus_exporter_status_rule_tpl = os.path.join(
            PROJECT_DIR,
            "package_hub/prometheus_rules_template/exporter_status_rule.yml")
        # 邮件地址
        self.email_address = "omp@testmail.com"
        # 监控端口
        self.monitor_port = 19031
        # Agent 请求头
        self.agent_request_header = {}
        # Prometheus 基本认证信息
        self.basic_auth = (PROMETHEUS_AUTH.get(
            "username", "omp"), PROMETHEUS_AUTH.get("plaintext_password", ""))

    def get_node_targets_file(self, env_code):
        """
        获取节点 exporter targets 文件路径（按环境拆分，文件名带 env_code 前缀）

        :param env_code: 环境标识（Env.code，spec §6.4：进入监控链路的一切 env 字符串均为 Env.code）
        :return: 节点 targets JSON 文件路径
        """
        return os.path.join(
            self.prometheus_targets_path,
            "{}_nodeExporter.json".format(env_code))

    @staticmethod
    def get_service_targets_file_name(env_code, service_name):
        """
        服务 exporter targets 文件名（按环境拆分，文件名带 env_code 前缀）

        :param env_code: 环境标识（Env.code）
        :param service_name: 服务名
        :return: targets JSON 文件名，如 prod_mysqlExporter.json
        """
        return "{}_{}Exporter.json".format(env_code, service_name)

    @staticmethod
    def replace_placeholder(path, placeholder_list):
        """
        替换文件中的占位符

        :param path: 要替换的文件路径
        :param placeholder_list: 占位符字典列表 [{"key":"value"}]
        :return: 替换成功返回 True 和空字符串，失败返回 False 和错误信息
        """
        if not os.path.isfile(path):
            return False, f"{path} not exists!"
        # 读取文件内容
        with open(path, "r") as f:
            data = f.read()
            # 遍历占位符列表
            for item in placeholder_list:
                for k, v in item.items():
                    # 构造占位符
                    placeholder = "${{{}}}".format(k)
                    # 替换占位符为对应的值
                    data = data.replace(placeholder, str(v))
        # 将替换后的内容写回文件
        with open(path, "w") as f:
            f.write(data)
        return True, ""

    @staticmethod
    def json_distinct(iterable_lst):
        """
        json元素去重

        :param iterable_lst: 去重对象
        :return: 去重后的对象
        """
        res = []
        # 将每个元素序列化为字节串
        for instance in iterable_lst:
            res.append(pickle.dumps(instance))
        # 使用集合去重
        res = set(res)
        # 将去重后的字节串反序列化为对象
        return [pickle.loads(i) for i in res]

    @staticmethod
    def get_dic_from_yaml(file_path):
        """
        从yaml中获取字典

        :param file_path: 文件路径
        :return: YAML 文件解析后的字典
        """
        with open(file_path, "r", encoding="utf8") as fp:
            content = fp.read()
        my_yaml = YAML()
        # 解析 YAML 文件内容为字典
        return my_yaml.load(content)

    @staticmethod
    def write_dic_to_yaml(dic, file_path):
        """
        将字典写入yaml

        :param dic: 字典数据
        :param file_path: yaml文件路径
        :return: 写入成功返回 True，失败返回 False
        """
        my_yaml = YAML()
        try:
            with open(file_path, "w", encoding="utf8") as fp:
                # 将字典数据写入 YAML 文件
                my_yaml.dump(dic, fp)
            return True
        except Exception:
            return False

    @staticmethod
    def get_expr(num, env, data_path):
        """
        获取prometheus数据分区匹配规则

        :param num: 阈值
        :param env: 环境标识（Env.code）
        :param data_path: 数据分区路径
        :return: 处理后的 Prometheus 查询表达式
        """
        _expr = \
            """max((node_filesystem_size_bytes{env="ENV",
            mountpoint="DATA_PATH"}-node_filesystem_free_bytes{env="ENV",
            mountpoint="DATA_PATH"})*100/(node_filesystem_avail_bytes{
            env="ENV",mountpoint="DATA_PATH"}+(node_filesystem_size_bytes{
            env="ENV",mountpoint="DATA_PATH"}-node_filesystem_free_bytes{
            env="ENV",mountpoint="DATA_PATH"})))by(instance,env)>= """
        return _expr.replace("ENV", env).replace(
            "DATA_PATH", data_path).replace("\n", "").replace(
            " ", ""
        ) + str(num)

    @staticmethod
    def get_service_port(service_name):
        """
        获取服务端口

        :param service_name: 服务名称
        :return: 服务对应的端口号，若未找到则返回 None
        """
        port = MONITOR_PORT.get(service_name)
        return port

    def make_data_node_rule(self, level, data_path, env="default"):
        """
        生成数据分区告警规则

        :param level: 告警级别
        :param data_path: 数据分区路径
        :param env: 主机所属环境标识（Env.code）
        :return: 包含告警规则信息的字典
        """
        try:
            # 从数据库中获取警告级别和严重级别的主机阈值对象
            warning_obj = HostThreshold.objects.filter(env_id=1, index_type="disk_data_used",
                                                       alert_level="warning").first()
            critical_obj = HostThreshold.objects.filter(env_id=1, index_type="disk_data_used",
                                                        alert_level="critical").first()
            # 获取警告阈值，若对象不存在则使用默认值
            warning_threshold = warning_obj.condition_value if warning_obj else "0"
            # 获取严重阈值，若对象不存在则使用默认值
            critical_threshold = critical_obj.condition_value if critical_obj else "100"
        except Exception as e:
            # 若获取阈值失败，使用默认阈值
            warning_threshold = "80"
            critical_threshold = "90"
            logger.error(f"更新数据分区告警于是失败！详情为：{e}")
        # 告警描述信息
        des = "主机 {{ $labels.instance }} 数据分区使用率为 " \
              "{{ $value | humanize }}%, 大于阈值 "
        return {
            "alert": "主机数据分区磁盘使用率过高",
            "annotations": {
                "disk_data_path": f"{data_path}",
                "consignee": f"{self.email_address}",
                "description": des + f"{critical_threshold}%" if level == "critical" else des + f"{warning_threshold}%",
                "summary": "disk_data_used (instance {{ $labels.instance }})"
            },
            "expr": self.get_expr(
                critical_threshold if level == "critical" else warning_threshold, env, data_path),
            "for": "1m",
            "labels": {
                "job": "nodeExporter",
                "severity": level
            }
        }

    def update_node_data_rule(self, data_path, env="default"):
        """
        更新主机data disk分区告警规则，当添加主机时使用

        :rtype: tuple
        :param data_path: 数据分区地址
        :param env: 主机所属环境标识（Env.code）
        :return: 元组，第一个元素为布尔值表示操作是否成功，第二个元素为操作结果信息
        """
        logger.info(f"Start update_node_data_rule: {data_path}; {env}")
        # 数据分区告警规则文件路径
        data_rule_path = os.path.join(
            self.prometheus_rules_path, f"{env}_node_data_rule.yml")
        # 生成严重级别和警告级别的数据分区告警规则
        _critical = self.make_data_node_rule("critical", data_path, env)
        _warning = self.make_data_node_rule("warning", data_path, env)
        # _critical_flag = True
        # _warning_flag = True
        if not os.path.exists(data_rule_path):
            # 若规则文件不存在，创建新的规则文件
            node_data_rule_dic = {
                "groups": [
                    {
                        "name": "主机数据分区磁盘使用率过高",
                        "rules": [
                            _critical, _warning
                        ]
                    }
                ]
            }
            self.write_dic_to_yaml(node_data_rule_dic, data_rule_path)
            return True, "success by new create"
        # 读取现有的规则文件内容
        node_data_rule_dic = self.get_dic_from_yaml(data_rule_path)
        groups = node_data_rule_dic.get("groups", []).copy()
        for item_index, item in enumerate(groups):
            rules = item.get("rules", []).copy()
            for el_index, el in enumerate(rules):
                if el.get("annotations", {}).get("disk_data_path") \
                        == data_path and el.get("labels", {}).get("severity") \
                        == "critical":
                    # _critical_flag = False
                    # 更新严重级别的规则
                    item.get("rules", [])[el_index] = _critical
                if el.get("annotations", {}).get("disk_data_path") \
                        == data_path and el.get("labels", {}).get(
                    "severity") \
                        == "warning":
                    # _warning_flag = False
                    # 更新警告级别的规则
                    item.get("rules", [])[el_index] = _warning
            node_data_rule_dic.get("groups", [])[item_index] = item
        # 将更新后的规则写回文件
        self.write_dic_to_yaml(node_data_rule_dic, data_rule_path)
        return True, "success"

    def add_rules(self, rule_type, env="default"):
        """
        rule_type:
            node: 主机告警规则
            service: 服务状态告警规则
            exporter: exporter状态告警规则
        更新prometheus rules规则, 建议在安装prometheus时进行更新

        :param rule_type: 更新方式
        :param env: 环境标识（Env.code）
        :return: 元组，第一个元素为布尔值表示操作是否成功，第二个元素为操作结果信息
        """
        logger.info(f"Start add rules: {rule_type}; {env}")
        # 规则文件占位符脚本
        rules_file_placeholder_script = [
            {"ENV": env},
            {"EMAIL_ADDRESS": self.email_address}
        ]
        if rule_type == "node":
            # 主机告警规则文件路径
            node_rule_yml_file = os.path.join(
                self.prometheus_rules_path,
                f"{env}_node_rule.yml"
            )
            if not os.path.exists(node_rule_yml_file):
                # 若文件不存在，复制模板文件并替换占位符
                shutil.copy(
                    self.prometheus_node_rule_tpl,
                    node_rule_yml_file
                )
                self.replace_placeholder(
                    node_rule_yml_file,
                    rules_file_placeholder_script
                )
        elif rule_type == "service":
            # 服务状态告警规则文件路径
            status_rule_yml_file = os.path.join(
                self.prometheus_rules_path,
                f"{env}_service_status_rule.yml"
            )
            if not os.path.exists(status_rule_yml_file):
                # 若文件不存在，复制模板文件并替换占位符
                shutil.copy(
                    self.prometheus_service_status_rule_tpl,
                    status_rule_yml_file
                )
                self.replace_placeholder(
                    status_rule_yml_file,
                    rules_file_placeholder_script
                )
        elif rule_type == "exporter":
            # exporter 状态告警规则文件路径
            exporter_rule_yml_file = os.path.join(
                self.prometheus_rules_path,
                f"{env}_exporter_status_rule.yml")
            if not os.path.exists(exporter_rule_yml_file):
                # 若文件不存在，复制模板文件并替换占位符
                shutil.copy(
                    self.prometheus_exporter_status_rule_tpl,
                    exporter_rule_yml_file
                )
                self.replace_placeholder(
                    exporter_rule_yml_file,
                    rules_file_placeholder_script
                )
        else:
            return False, "not support!"
        return True, "success"

    def delete_rules(self, rule_type, env="default"):
        """
        删除prometheus rules的规则

        :param rule_type: 删除类型
        :param env: 环境标识（Env.code）
        :return: 元组，第一个元素为布尔值表示操作是否成功，第二个元素为操作结果信息
        """
        if rule_type not in ("node", "service", "exporter"):
            return False, "not support!"
        if rule_type == "node":
            # 主机告警规则文件路径
            rule_yml_file = os.path.join(
                self.prometheus_rules_path,
                f"{env}_node_rule_yml"
            )
        else:
            # 其他类型告警规则文件路径
            rule_yml_file = os.path.join(
                self.prometheus_rules_path,
                f"{env}_{rule_type}_status_rule.yml"
            )
        if os.path.exists(rule_yml_file):
            # 若文件存在，删除该文件
            os.remove(rule_yml_file)
        return True, "success"

    def merge_job_files(self, job_name, target_files):
        """
        将 targets 文件并入 prometheus.yml 指定 job 的 file_sd 文件列表

        线上部分 job（如 nodeExporter）的 file_sd 是固定文件名而非 glob，
        按环境新拆分的 {env_code}_xxx.json 必须追加进该 job 的 files
        才会被纳入抓取（与 add_service 的同名 job 合并逻辑对称）。

        :param job_name: job_name 名称（如 nodeExporter）
        :param target_files: 要并入的文件列表（相对 prometheus.yml，
            如 targets/default_nodeExporter.json）
        :return: 无
        """
        if not os.path.exists(self.prometheus_conf_path):
            # 配置文件缺失（如全新安装前）时跳过合并，仅记日志不阻断
            # targets 文件写入主流程
            logger.warning(
                f"{self.prometheus_conf_path} not exists, skip merge "
                f"job files: {job_name} <- {target_files}")
            return
        with open(self.prometheus_conf_path, "r") as fr:
            # 读取 Prometheus 配置文件内容
            content = yaml.load(fr.read(), yaml.Loader)
        scrape_configs = content.get("scrape_configs") or []
        # 同名 job 已存在时合并 file_sd 文件列表，避免产生重复 job_name
        exist_job = next(
            (job for job in scrape_configs
             if isinstance(job, dict) and job.get("job_name") == job_name),
            None)
        if exist_job is None:
            # job 不存在（如全新安装未预置 node job）时按线上既有形态补建
            exist_job = {
                "job_name": job_name,
                "metrics_path": "/metrics/monitor/node",
                "file_sd_configs": [
                    {"refresh_interval": "30s", "files": []}
                ]
            }
            scrape_configs.append(exist_job)
        file_sd_configs = exist_job.get("file_sd_configs") or [{}]
        files = file_sd_configs[0].setdefault("files", [])
        for target_file in target_files:
            if target_file not in files:
                files.append(target_file)
        exist_job["file_sd_configs"] = file_sd_configs
        content["scrape_configs"] = scrape_configs
        with open(self.prometheus_conf_path, "w", encoding="utf8") as fw:
            # 将更新后的配置写回文件
            yaml.dump(data=content, stream=fw,
                      allow_unicode=True, sort_keys=False)

    def add_node(self, nodes_data):
        """
        nodes_data = [
            {
                "data_path": "/data",
                "env": "default",  # Env.code
                "ip": "127.0.0.1",
                "instance_name": "instance"
            }
        ]
        添加主机到自监控系统。主机 targets 按环境拆分为
        {env_code}_nodeExporter.json，多环境互不覆盖。

        :param nodes_data: 新增的主机信息，其中 "env" 必须传环境标识（Env.code）
        :return: 元组，第一个元素为布尔值表示操作是否成功，第二个元素为操作结果信息
        """
        logger.info(f"Start add node: {nodes_data}")
        if not nodes_data:
            return False, "nodes_data can not be null"
        # 按环境分组的节点目标列表
        env_node_target_map = {}
        # 遍历主机数据，添加主机层的告警规则
        for item in nodes_data:
            # 进入监控链路的一切 env 字符串均为 Env.code（spec §6.4）
            env_code = item.get("env") or "default"
            # 构造节点目标元素
            node_target_ele = {
                "targets": [item["ip"] + ":" + str(self.monitor_port)],
                "labels": {
                    "instance": item["ip"],
                    "instance_name": "{}".format(item.get("instance_name")),
                    "service_type": "host",
                    "env": env_code}
            }
            env_node_target_map.setdefault(env_code, []).append(node_target_ele)
            print("添加数据分区", item.get("data_path"))
            # 需要像数据库添加数据分区的的规则
            if item.get("data_path"):
                self.add_data_disk_rules(item["data_path"], env_code)
        # 增加主机的target配置文件(prometheus/conf/targets)，按环境分别写入
        for env_code, node_target_list in env_node_target_map.items():
            node_targets_file = self.get_node_targets_file(env_code)
            if os.path.exists(node_targets_file):
                with open(node_targets_file, "r") as f:
                    content = f.read()
                    if content:
                        # 读取现有目标列表
                        old_node_target_list = json.loads(content)
                        node_target_list.extend(old_node_target_list)
            # 对节点目标列表去重
            node_target_list = self.json_distinct(node_target_list)
            with open(node_targets_file, "w") as f2:
                # 将去重后的目标列表写入文件
                json.dump(node_target_list, f2, ensure_ascii=False, indent=4)
        # nodeExporter job 的 file_sd 为固定文件名（非 glob），新写入的
        # {env_code}_nodeExporter.json 需并入该 job 的 files 才会被抓取
        # （终审必修项 5，与 add_service 的 job 合并逻辑对称）
        self.merge_job_files(
            "nodeExporter",
            ["targets/{}_nodeExporter.json".format(env_code)
             for env_code in env_node_target_map])
        # 重载 Prometheus 配置
        self.reload_prometheus()
        return True, "success"

    def delete_node(self, nodes_data):
        """
        从自监控系统删除主机信息。targets 文件按环境拆分为
        {env_code}_nodeExporter.json：入参带 "env" 时只处理对应环境文件，
        未带 "env" 时回退扫描 targets 目录下全部 *_nodeExporter.json。

        :param nodes_data: 要删除的主机信息，其中 "env" 传环境标识（Env.code）
        :return: 元组，第一个元素为布尔值表示操作是否成功，第二个元素为操作结果信息
        """
        if not nodes_data:
            return False, "nodes_data can not be null"
        env_codes = {item.get("env") for item in nodes_data if item.get("env")}
        if env_codes:
            # 带环境标识：仅处理对应环境的 targets 文件
            node_targets_files = [
                self.get_node_targets_file(env_code) for env_code in env_codes]
        elif os.path.isdir(self.prometheus_targets_path):
            # 未带环境标识：扫描全部按环境拆分的节点 targets 文件
            node_targets_files = [
                os.path.join(self.prometheus_targets_path, name)
                for name in os.listdir(self.prometheus_targets_path)
                if name.endswith("nodeExporter.json")]
        else:
            return False, f"{self.prometheus_targets_path} not exists!"
        handled = False
        for node_targets_file in node_targets_files:
            if not os.path.exists(node_targets_file):
                continue
            with open(node_targets_file, "r") as f:
                content = f.read()
                if content:
                    # 读取现有目标列表
                    node_target_list = json.loads(content)
                else:
                    node_target_list = list()
            if not node_target_list:
                handled = True
                continue
            for item in nodes_data:
                ip = item["ip"]
                for node in node_target_list:
                    if ip in node["labels"]["instance"]:
                        # 移除要删除的节点目标
                        node_target_list.remove(node)
                        break
            with open(node_targets_file, "w") as f2:
                # 将更新后的目标列表写入文件
                json.dump(node_target_list, f2, ensure_ascii=False, indent=4)
            handled = True
        if not handled:
            return False, "no nodeExporter targets file exists!"
        return True, "success"

    def update_agent_service(self, dest_ip, action, services_data):
        """
        接收omp传来的参数，解析后发送到monitor_agent

        :param action: 更新动作 add or delete
        :param services_data: 要更新的服务信息
        :param dest_ip: 目标 IP 地址
        :return: 元组，第一个元素为布尔值表示操作是否成功，第二个元素为操作结果信息
        """
        json_dict = dict()
        json_content = list()
        headers = CW_TOKEN
        dest_url = ''
        if action == 'add':
            # 构造添加服务的目标 URL
            dest_url = 'http://{}:{}/update/service/add'.format(dest_ip, self.monitor_port)  # NOQA
            for sd in services_data:
                service_temp_data = dict()
                service_temp_data['service_port'] = sd.get('listen_port')
                service_temp_data['run_port'] = sd.get('run_port')
                if sd.get('service_name') in EXPORTERS:
                    # 获取 exporter 端口
                    service_temp_data['exporter_port'] = self.get_service_port(
                        '{}Exporter'.format(sd.get('service_name')))
                else:
                    service_temp_data['exporter_port'] = sd.get(
                        'metric_port', 0)
                if sd.get('service_name') in METRICS.keys():
                    # 获取 exporter 指标路径
                    service_temp_data['exporter_metric'] = METRICS.get(
                        sd.get('service_name'), 0)
                else:
                    service_temp_data['exporter_metric'] = 'metrics'
                service_temp_data['username'] = sd.get('username', '')
                service_temp_data['password'] = sd.get('password', '')
                service_temp_data['name'] = sd.get('service_name')
                service_temp_data['only_process'] = sd.get('only_process')
                service_temp_data['process_key_word'] = sd.get(
                    'process_key_word')
                service_temp_data['instance'] = dest_ip
                service_temp_data['env'] = sd.get('env')
                service_temp_data['log_path'] = sd.get('log_path')
                service_temp_data["scrape_log_level"] = LOKI_CONFIG.get(
                    "scrape_log_level")
                json_content.append(service_temp_data)
        elif action == 'delete':
            # 构造删除服务的目标 URL
            dest_url = 'http://{}:{}/update/service/delete'.format(dest_ip, self.monitor_port)  # NOQA
            for sd in services_data:
                json_content.append(sd.get('service_name'))

        json_dict['services'] = json_content
        try:
            logger.info(f'向agent发送数据{json_dict}')
            # 发送 POST 请求更新服务配置
            result = requests.post(
                dest_url, headers=headers, data=json.dumps(json_dict)).json()
            if result.get('return_code') == 0:
                logger.info('向{}更新服务{}配置成功！'.format(
                    dest_ip, services_data[0].get('service_name')))
            else:
                logger.error('向{}更新服务{}配置失败！'.format(
                    dest_ip, services_data[0].get('service_name')))
                # return False, result.get('return_message')
        except Exception as e:
            logger.error('向{}更新服务{}配置失败！'.format(
                dest_ip, services_data[0].get('service_name')))
            logger.error(e)
            # return False, e
        try:
            from utils.parse_config import MONITOR_PORT, LOCAL_IP
            from db_models.models import Host
            # 构造更新 Promtail 配置的 URL
            update_agent_promtail_url = f'http://{dest_ip}:{self.monitor_port}/update/promtail/add'  # NOQA
            # 获取主机 Agent 目录
            host_agent_dir = Host.objects.filter(
                ip=dest_ip).values_list('agent_dir', flat=True)[0]
            json_dict['promtail_config'] = {
                'http_listen_port': MONITOR_PORT.get('promtail'),
                'loki_url': f'http://{LOCAL_IP}:{MONITOR_PORT.get("loki")}/loki/api/v1/push'  # NOQA
            }
            json_dict['agent_dir'] = host_agent_dir
            logger.info(f'向agent发送数据{json_dict}')
            # 发送 POST 请求更新 Promtail 配置
            promtail_result = requests.post(
                update_agent_promtail_url, headers=headers, data=json.dumps(json_dict)).json()
            if promtail_result.get('return_code') == 0:
                logger.info('向{}更新服务{}日志监控配置成功！'.format(
                    dest_ip, services_data[0].get('service_name')))
            else:
                logger.error('向{}更新服务{}日志监控配置失败！'.format(
                    dest_ip, services_data[0].get('service_name')))
                # return False, promtail_result.get('return_message')
        except Exception as e:
            logger.error(e)
            logger.error('向{}更新服务{}日志监控失败！'.format(
                dest_ip, services_data[0].get('service_name')))
            # return False, e

        return True, 'success'

    def add_service(self, service_data):
        """
        service_data = {
            "service_name": "mysql",
            "instance_name": "mysql_dosm",
            "data_path": "/data/appData/mysql",
            "log_path": "/data/logs/mysql",
            "env": "default",
            "ip": "127.0.0.1",
            "listen_port": "3306"
            "metric_port": "19018"
        }
        添加有exporter的组件信息到各自的exporter监控

        :param service_data: 新增的服务信息
        :return: 元组，第一个元素为布尔值表示操作是否成功，第二个元素为操作结果信息
        """
        if not service_data:
            return False, "args cant be null"

        logger.info(f'收到信息：{service_data}')
        # 进入监控链路的一切 env 字符串均为 Env.code（spec §6.4）
        env_code = service_data.get("env") or "default"
        # 构造 job 名称
        job_name_str = "{}Exporter".format(service_data.get('service_name'))
        # 服务 exporter targets 文件按环境拆分：{env_code}_{service}Exporter.json
        targets_file_name = self.get_service_targets_file_name(
            env_code, service_data.get('service_name'))
        # 构造 Prometheus 作业配置字典
        prom_job_dict = {
            "job_name": job_name_str,
            "metrics_path": f"/metrics/monitor/{service_data.get('service_name')}",
            "file_sd_configs": [
                {
                    "refresh_interval": "30s",
                    "files": [f"targets/{targets_file_name}"]
                }
            ]
        }
        with open(self.prometheus_conf_path, "r") as fr:
            # 读取 Prometheus 配置文件内容
            content = yaml.load(fr.read(), yaml.Loader)
        scrape_configs = content.get("scrape_configs") or []
        # 同名 job 已存在时（服务在其它环境已注册）合并 file_sd 文件列表，
        # 避免产生重复 job_name 的抓取配置
        exist_job = next(
            (job for job in scrape_configs
             if isinstance(job, dict) and job.get("job_name") == job_name_str),
            None)
        if exist_job is not None:
            file_sd_configs = exist_job.get("file_sd_configs") or [{}]
            files = file_sd_configs[0].setdefault("files", [])
            if f"targets/{targets_file_name}" not in files:
                files.append(f"targets/{targets_file_name}")
            exist_job["file_sd_configs"] = file_sd_configs
        else:
            # 添加新的作业配置
            scrape_configs.append(prom_job_dict)
        # 对作业配置列表去重
        content["scrape_configs"] = self.json_distinct(scrape_configs)
        with open(self.prometheus_conf_path, "w", encoding="utf8") as fw:
            # 将更新后的配置写回文件
            yaml.dump(data=content, stream=fw,
                      allow_unicode=True, sort_keys=False)
        # 构造服务 exporter 目标文件路径
        self_exporter_target_file = os.path.join(
            self.prometheus_targets_path, targets_file_name)
        self_target_list = list()
        self_target_ele = ""
        try:
            # 构造服务目标元素
            self_target_ele = {
                "labels": {
                    "instance": "{}".format(service_data["ip"]),
                    "instance_name": "{}".format(service_data.get("instance_name")),
                    "service_type": "service",
                    "env": env_code
                },
                "targets": [
                    "{}:{}".format(service_data["ip"], self.monitor_port)
                ]
            }
        except KeyError as func_e:
            logger.error(func_e)
        self_target_list.append(self_target_ele)

        if os.path.exists(self_exporter_target_file):
            with open(self_exporter_target_file, 'r') as f:
                content = f.read()
                if content:
                    # 读取现有服务目标列表
                    old_self_target_list = json.loads(content)
                    self_target_list.extend(old_self_target_list)
        # 对服务目标列表去重
        self_target_list = self.json_distinct(self_target_list)

        with open(self_exporter_target_file, 'w') as f2:
            # 将去重后的服务目标列表写入文件
            json.dump(self_target_list, f2, ensure_ascii=False, indent=4)
        # 更新 Agent 服务配置
        flag, msg = self.update_agent_service(
            service_data.get('ip'), 'add', [service_data])
        if not flag:
            return False, msg
        # self.add_rules('service', service_data.get('env'))
        # 构造重载 Prometheus 配置的 URL
        reload_prometheus_url = 'http://localhost:19011/-/reload'
        # TODO 确认重载prometheus动作在哪执行
        try:
            # 发送 POST 请求重载 Prometheus 配置
            requests.post(reload_prometheus_url, auth=self.basic_auth)
        except Exception as e:
            logger.error(e)
            logger.error("重载prometheus配置失败！")
        return True, "success"

    def delete_service(self, service_data):
        """
        从自有的exporter中删除对应的服务信息。targets 文件按环境拆分为
        {env_code}_{service}Exporter.json，按 (env_code, instance) 匹配删除，
        不影响其它环境的文件。

        :param service_data: 要删除的服务信息，其中 "env" 传环境标识（Env.code）
        :return: 元组，第一个元素为布尔值表示操作是否成功，第二个元素为操作结果信息
        """
        if not service_data:
            return False, "args cant be null"

        # 进入监控链路的一切 env 字符串均为 Env.code（spec §6.4）
        env_code = service_data.get("env") or "default"
        # 构造服务 exporter 目标文件路径
        self_exporter_target_file = os.path.join(
            self.prometheus_targets_path,
            self.get_service_targets_file_name(
                env_code, service_data["service_name"]))

        self_target_list = list()
        if os.path.exists(self_exporter_target_file):
            with open(self_exporter_target_file, 'r') as f:
                content = f.read()
                if content:
                    # 读取现有服务目标列表
                    self_target_list = json.loads(content)
        else:
            logger.error("{}不存在！".format(self_exporter_target_file))
            return False, "Failed"
        try:
            instance = service_data['ip']
            env = service_data['env']
            for service in self_target_list:
                if (instance == service["labels"]["instance"]) and (env == service["labels"]["env"]):
                    # 移除要删除的服务目标
                    self_target_list.remove(service)
        except KeyError as func_e:
            logger.error(func_e)

        with open(self_exporter_target_file, 'w') as f2:
            # 将更新后的服务目标列表写入文件
            json.dump(self_target_list, f2, ensure_ascii=False, indent=4)
        # 更新 Agent 服务配置
        flag, msg = self.update_agent_service(
            service_data.get('ip'), 'delete', [service_data])
        if not flag:
            return False, msg
        # 构造重载 Prometheus 配置的 URL
        reload_prometheus_url = 'http://localhost:19011/-/reload'
        # TODO 确认重载prometheus动作在哪执行
        try:
            # 发送 POST 请求重载 Prometheus 配置
            requests.post(reload_prometheus_url, auth=self.basic_auth)
        except Exception as e:
            logger.error(e)
            logger.error("重载prometheus配置失败！")
        return True, "success"

    def update_host_threshold(self, env="default", env_id=1):
        """
        更新主机阈值配置

        :param env: 环境标识（Env.code），默认为 "default"
        :param env_id: 环境 ID，默认为 1
        :return: 元组，第一个元素为布尔值表示操作是否成功，第二个元素为操作结果信息
        """
        # 规则文件占位符脚本
        rules_file_placeholder_script = [
            {"ENV": env},
            {"EMAIL_ADDRESS": self.email_address}
        ]

        # 主机规则文件路径
        node_rule_yml_file = os.path.join(
            self.prometheus_rules_path,
            f"{env}_node_rule.yml"
        )
        if not os.path.exists(node_rule_yml_file):
            # 若文件不存在，复制模板文件并替换占位符
            shutil.copy(
                self.prometheus_node_rule_tpl,
                node_rule_yml_file
            )
            self.replace_placeholder(
                node_rule_yml_file,
                rules_file_placeholder_script
            )
        from utils.prometheus.update_threshold import config_update
        try:
            # 调用自监控脚本更新环境阈值
            # 获取主机阈值信息
            host_thresholds = HostThreshold.objects.filter(
                env_id=env_id).values(
                'index_type', 'condition', 'condition_value', 'alert_level')
            # 获取服务自定义阈值信息
            services_objs = ServiceCustomThreshold.objects.filter(
                env_id=env_id
            ).order_by("service_name", "index_type", "condition_value").values(
                "service_name", "index_type", "condition",
                "condition_value", "alert_level")
            services_dict = {}
            for services_obj in services_objs:
                service_name = services_obj.pop("service_name")
                info = services_dict.get(service_name)
                if not info:
                    services_dict[service_name] = [services_obj]
                else:
                    services_dict[service_name].append(services_obj)
            # 构造更新参数
            params = {
                'env_name': env,
                'hosts': list(host_thresholds),
                'services': services_dict
            }
            # data_dir = get_path_dir(env_id)
            # if data_dir:
            #     params.update(disk_data_path=data_dir)  # TODO 补充替换数据分区阈值的逻辑
            # 调用更新函数
            update_result = config_update(params)
            if not update_result:
                return False, "failed"
            return True, "success"
        except Exception as e:
            import traceback
            logger.error(f"同步监控指标出错:{e}{traceback.format_exc()}")
            return False, "failed"

    def gen_one_rule(self, **kwargs):  # NOQA
        """
        生成单个规则

        :param kwargs: 包含规则相关信息的关键字参数
        :return: 包含单个规则信息的字典
        """
        expr = kwargs.get("expr")
        compare_str = kwargs.get("compare_str")
        for_time = kwargs.get("for_time")
        alert = kwargs.get("alert")
        summary = kwargs.get("summary")
        description = kwargs.get("description")
        threshold_value = kwargs.get("threshold_value")
        # 构造规则表达式
        expr_data = f"{expr} {compare_str} {threshold_value}"
        labels = kwargs.get("labels")
        one_rule = {
            "alert": alert,
            "annotations": {
                "description": description,
                "summary": summary,
            },
            "expr": expr_data,
            "for": for_time,
            "labels": labels
        }
        return one_rule

    def get_hash_value(self, expr, severity):  # NOQA
        """
        生成表达式和严重级别的哈希值

        :param expr: 表达式
        :param severity: 严重级别
        :return: 生成的 MD5 哈希值
        """
        data = expr + severity
        # 生成 MD5 哈希值
        hash_data = hashlib.md5(data.encode(encoding='UTF-8')).hexdigest()
        return hash_data

    def add_data_disk_rules(self, data_path, env="default"):
        """
        添加数据分区磁盘使用率告警规则

        :param data_path: 数据分区路径
        :param env: 环境标识（Env.code），默认为 "default"
        :return: 布尔值，表示操作是否成功
        """
        # threshold = "80" if level == "warning" else 90
        logger.error("开始添加数据分区规则")
        # 数据分区规则归属环境：按入参 env（Env.code）反查环境对象，
        # 使 AlertRule 落到所属环境（此前缺省落 default=1，跨环境混写）；
        # 环境解析失败（如 env 未命中 / DB 不可用）不阻断规则创建，
        # 回退原有缺省环境行为
        try:
            env_obj = Env.objects.filter(code=env).first()
        except Exception as e:
            logger.error(f"数据分区规则环境解析失败，落缺省环境: {e}")
            env_obj = None
        # 定义警告和严重级别的阈值列表
        threshold_list = [("warning", "80"), ("critical", "90")]
        for i in range(2):
            info = threshold_list[i]
            level = info[0]
            threshold = info[1]
            # 构造 Prometheus 查询表达式
            expr = 'max((node_filesystem_size_bytes{env="ENV",' \
                   'mountpoint="DATA_PATH"}-node_filesystem_free_bytes{env="ENV",' \
                   'mountpoint="DATA_PATH"})*100/(node_filesystem_avail_bytes{' \
                   'env="ENV",mountpoint="DATA_PATH"}+(node_filesystem_size_bytes{' \
                   'env="ENV",mountpoint="DATA_PATH"}-node_filesystem_free_bytes{' \
                   'env="ENV",mountpoint="DATA_PATH"}))) by (instance,env)'.replace(
                "ENV", env).replace("DATA_PATH", data_path)
            data = {
                "alert": f"主机数据分区{data_path}磁盘使用率",
                "description": '主机 {{ $labels.instance }} 数据分区使用率为 {{ $value | humanize }}%, 大于阈值 $threshold$%'.replace(
                    "$threshold$", threshold),
                "expr": expr,
                "compare_str": ">=",
                "threshold_value": threshold,
                "for_time": "60s",
                "severity": level,
                "labels": {
                    "job": "nodeExporter",
                    "severity": level
                },
                "name": "数据分区使用率",
                "quota_type": 0,
                "status": 1,
                "service": "node",
                "forbidden": 2,

            }
            if env_obj is not None:
                # 规则归属环境（env 未命中环境记录时保持原缺省行为）
                data["env"] = env_obj
            # 生成表达式和严重级别的哈希值
            hash_data = self.get_hash_value(expr=expr, severity=level)
            if AlertRule.objects.filter(expr=expr, severity=level, hash_data=hash_data).exists():
                continue
            try:
                data.update(hash_data=hash_data)
                # 创建告警规则对象并保存到数据库
                AlertRule(**data).save()
            except Exception as e:
                logger.error(f"更新数据分区错误:{e}")
        # 更新规则文件
        self.update_rule_file(env=env)
        return True

    def update_rule_file(self, add_data=None, add=False, update=False, delete=False, env="default", rule_id=0,
                         env_id=1):
        """
        更新规则文件

        :param add_data: 新增或更新的规则数据，默认为 None
        :param add: 是否为新增操作，默认为 False
        :param update: 是否为更新操作，默认为 False
        :param delete: 是否为删除操作，默认为 False
        :param env: 环境标识（Env.code），默认为 "default"
        :param rule_id: 规则 ID，默认为 0
        :param env_id: 环境 ID，默认为 1
        :return: 布尔值，表示操作是否成功
        """
        # 规则文件路径
        rule_file_path = os.path.join(
            self.prometheus_rules_path, f"{env}_rule.yml")
        try:
            # 获取所有启用的告警规则（限当前环境，避免全量规则混写进
            # 单一环境的规则文件——多环境架构终审必修项 3）
            all_rules = AlertRule.objects.filter(
                status=1, env__code=env).all()
            if delete or update:
                # 排除要删除或更新的规则
                all_rules = AlertRule.objects.filter(
                    status=1, env__code=env).exclude(id=rule_id).all()
            # 初始化规则文件数据
            init_data = {"groups": [
                {
                    "name": "OMP Alert",
                    "rules": []
                }
            ]}
            for rule in all_rules:
                content = {
                    "alert": rule.alert,
                    "annotations": {
                        "description": rule.description,
                        "summary": rule.summary,
                    },
                    "expr": f"{rule.expr} {rule.compare_str} {rule.threshold_value}",
                    "for": rule.for_time,
                    "labels": rule.labels,
                }
                # 将规则添加到规则文件数据中
                init_data["groups"][0]["rules"].append(content)
            if add or update:
                # 若为新增或更新操作，添加新的规则
                init_data["groups"][0]["rules"].append(
                    self.gen_one_rule(**add_data)
                )
            my_yaml = YAML()
            with open(rule_file_path, "w", encoding="utf8") as fp:
                # 将规则文件数据写入 YAML 文件
                my_yaml.dump(init_data, fp)

            return True
        except Exception as e:
            logger.error(f"生成规则文件{rule_file_path}失败{e}")
            return False

    def reload_prometheus(self):
        """
        重载prometheus

        :return: 布尔值，表示操作是否成功
        """
        # 构造重载 Prometheus 配置的 URL
        reload_prometheus_url = 'http://localhost:19011/-/reload'
        # TODO 确认重载prometheus动作在哪执行
        try:
            # 发送 POST 请求重载 Prometheus 配置
            response = requests.post(
                reload_prometheus_url, auth=self.basic_auth)
            logger.error(f"重载成功 {response.text}")
            return True
        except Exception as e:
            logger.error(e)
            logger.error("重载prometheus配置失败！")
            return False