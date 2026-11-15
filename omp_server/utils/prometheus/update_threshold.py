# -*- coding: utf-8 -*-
# 导入命令行参数解析模块
import argparse
# 导入操作系统相关功能模块
import os

# 导入用于发送 HTTP 请求的模块
import requests
# 导入用于处理 YAML 格式数据的模块
import yaml
# 导入日志记录模块
import logging

# 从 omp_server 项目的设置文件中导入项目目录路径
from omp_server.settings import PROJECT_DIR

# 获取名为 "server" 的日志记录器
logger = logging.getLogger("server")

# 定义告警描述信息字典，键为指标类型，值为对应的告警描述模板
description = {
    "cpu_used": "主机 {{ $labels.instance }} CPU 使用率为 {{ $value | humanize }}%, 大于阈值 $condition_value$%",
    "memory_used": "主机 {{ $labels.instance }} 内存使用率为 {{ $value | humanize }}%，大于阈值 $condition_value$%",
    "disk_root_used": "主机 {{ $labels.instance }} 根分区使用率为 {{ $value | humanize }}%, 大于 阈值 $condition_value$%",
    "disk_data_used": "主机 {{ $labels.instance }} 数据分区使用率为 {{ $value | humanize }}%, 大于 阈值 $condition_value$%",
    "kafka_consumergroup_lag": "Kafka 消费组{{ $labels.consumergroup }}消息堆积数过多  {{ humanize $value }}"
}
# 定义 Prometheus 查询表达式字典，键为指标类型，值为对应的查询表达式模板
expr = {
    "cpu_used": "(100 - sum(avg without (cpu)(irate(node_cpu_seconds_total{mode='idle', "
                "env=\"$env_name$\"}[2m]))) by (instance) * 100) $condition$ $condition_value$",
    "memory_used": "(1 - (node_memory_MemAvailable_bytes{env=\"$env_name$\"} / (node_"
                   "memory_MemTotal_bytes{env=\"$env_name$\"}))) * 100 $condition$ $condition_value$",
    "disk_root_used": "max((node_filesystem_size_bytes{env=\"$env_name$\","
                      "mountpoint=\"/\"}-node_filesystem_free_bytes"
                      "{env=\"$env_name$\",mountpoint=\"/\"}) *100/(node_filesystem_avail_"
                      "bytes{env=\"$env_name$\",mountpoint=\"/\"}+(node_filesystem_size_bytes{"
                      "env=\"$env_name$\",mountpoint=\"/\"}-node"
                      "_filesystem_free_bytes{env=\"$env_name$\",mountpoint=\"/\"})))by(instance)"
                      " $condition$ $condition_value$",
    "disk_data_used": "max((node_filesystem_size_bytes{env=\"$env_name$\","
                      "mountpoint=\"$disk_data_path$\"}-node_filesystem_free_bytes"
                      "{env=\"$env_name$\",mountpoint=\"$disk_data_path$\"}) *100/(node_filesystem_avail_"
                      "bytes{env=\"$env_name$\",mountpoint=\"$disk_data_path$\"}+(node_filesystem_size_bytes{"
                      "env=\"$env_name$\",mountpoint=\"$disk_data_path$\"}-node"
                      "_filesystem_free_bytes{env=\"$env_name$\",mountpoint=\"$disk_data_path$\"})))by(instance)"
                      " $condition$ $condition_value$",
    "kafka_consumergroup_lag": "sum(kafka_consumergroup_lag{env=\"$env_name$\"}) by (consumergroup,instance,job,env) $condition$ $condition_value$"

}

def gen_summary(index_type):
    """
    生成告警摘要信息

    :param index_type: 指标类型
    :return: 替换后的告警摘要信息
    """
    return replace_value("$index_type$ (instance {{ $labels.instance }})", index_type=index_type)

def replace_value(line, env_name=None, condition=None, condition_value=None, alert_level=None, index_type=None,
                  disk_data_path=None):
    """
    替换字符串中的占位符

    :param line: 包含占位符的字符串
    :param env_name: 环境标识（Env.code，spec §6.4：进入监控链路的一切 env 字符串均为 Env.code）
    :param condition: 条件，如 >=、> 等
    :param condition_value: 条件值
    :param alert_level: 告警级别
    :param index_type: 指标类型
    :param disk_data_path: 数据磁盘路径
    :return: 替换占位符后的字符串
    """
    if env_name:
        line = line.replace("$env_name$", str(env_name))
    if condition:
        line = line.replace("$condition$", str(condition))
    if condition_value:
        line = line.replace("$condition_value$", str(condition_value))
    if alert_level:
        line = line.replace("$alert_level$", str(alert_level))
    if index_type:
        line = line.replace("$index_type$", str(index_type))
    if disk_data_path:
        line = line.replace("$disk_data_path$", str(disk_data_path))
    return line

def update_node_rule_yaml(quotes_info):
    """
    更新主机指标文件

    :param quotes_info: 包含指标阈值信息的字典
    :return: 更新成功返回 True，失败返回 False
    """
    # 定义指标英文名称与中文名称的映射字典
    metric_en_cn_dict = {
        "cpu_used": "CPU",
        "memory_used": "内存",
        "disk_root_used": "根分区磁盘",
        "disk_data_used": "数据分区磁盘"
    }
    # 从传入的信息中获取环境标识（Env.code，用于规则文件名与 PromQL env 标签）
    env_name = quotes_info.get("env_name")
    # 构建主机规则 YAML 文件的路径
    node_rule_yml_path = os.path.join(PROJECT_DIR, 'component',
                                      'prometheus/conf/rules',
                                      '{}_node_rule.yml'.format(env_name))
    # 定义实例宕机告警信息
    instance_alert = {
        "alert": "实例宕机",
        "annotations": {
            "consignee": "{}".format(""),  # TODO: 待完善收件人信息
            "description": "实例 {{ $labels.instance }} monitor_agent进程丢失或主机发生宕机已超过1分钟",
            "summary": "实例宕机({{ $labels.instance }})"
        },
        "expr": "sum(up{job=\"nodeExporter\", env=\'%s\'}) by (instance) < 1" % env_name,
        "for": "1m",
        "labels": {
            "job": "nodeExporter",
            "severity": "critical"
        }
    }
    # 定义主机规则信息
    node_rules = {"name": "node alert", "rules": [instance_alert]}
    # 定义包含所有规则组的信息
    dict_total_rules = {"groups": [node_rules]}
    # 从传入的信息中获取主机指标阈值信息
    node_quotes = quotes_info.get("hosts")
    # 再次获取环境名称
    env_name = quotes_info.get("env_name")
    # 从传入的信息中获取数据磁盘路径，若不存在则为 None
    disk_data_path = quotes_info.get("disk_data_path", None)
    try:
        # 遍历主机指标阈值信息
        for host_quote_info in node_quotes:
            # 获取指标类型
            index_type = host_quote_info.get("index_type")
            # 若指标类型为数据分区磁盘使用率且数据磁盘路径为空，则跳过本次循环
            if index_type == "disk_data_used":
                if not disk_data_path:
                    continue
            # 获取告警级别
            alert_level = host_quote_info.get("alert_level")
            # 获取条件值
            condition_value = host_quote_info.get("condition_value")
            # 获取条件
            condition = host_quote_info.get("condition")
            # 定义主机指标告警信息
            quote_info = {
                "alert": "主机 {} 使用率过高".format(metric_en_cn_dict.get(index_type)),
                "annotations": {
                    "consignee": "{}".format(""),  # TODO: 待完善收件人信息
                    "description": replace_value(description.get(index_type), condition_value=condition_value),
                    "summary": gen_summary(index_type=index_type),
                },
                "expr": replace_value(expr.get(index_type), env_name=env_name, condition=condition,
                                      condition_value=condition_value, disk_data_path=disk_data_path),
                "for": "1m",
                "labels": {
                    "job": "nodeExporter",
                    "severity": alert_level,
                }

            }
            # 记录主机指标告警信息
            logger.info(quote_info)
            # 将主机指标告警信息添加到主机规则中
            node_rules["rules"].append(quote_info)
        # 记录开始更新主机告警规则文件的信息
        logger.info('开始更新告警规则文件{}'.format(node_rule_yml_path))

        # 以写入模式打开主机规则 YAML 文件，并将规则信息写入文件
        with open(node_rule_yml_path, "w") as fw:
            yaml.dump(dict_total_rules, fw, allow_unicode=True)
        # 记录更新主机告警规则文件成功的信息
        logger.info("更新主机告警规则文件成功")
        return True
    except Exception as e:
        # 记录更新主机告警规则文件失败的错误信息
        logger.error(e)
        return False

def update_service_rule_yaml(quotes_info):
    """
    更新服务指标文件

    :param quotes_info: 包含指标阈值信息的字典
    :return: 更新成功返回 True，失败返回 False
    """
    # 从传入的信息中获取环境标识（Env.code，用于规则文件名与 PromQL env 标签）
    env_name = quotes_info.get("env_name")
    # 构建服务规则 YAML 文件的路径
    service_rule_yml_path = os.path.join(PROJECT_DIR, 'component',
                                         'prometheus/conf/rules',
                                         '{}_service_status_rule.yml'.format(env_name))
    # 定义服务状态告警信息
    instance_alert = {
        "alert": "app state",
        "annotations": {
            "consignee": "{}".format(""),  # TODO: 待完善收件人信息
            "description": "主机 {{ $labels.instance }} 中的 服务 {{ $labels.app }} 已经down掉超过一分钟.",
            "summary": "app state(instance {{ $labels.instance }})"
        },
        "expr": "probe_success{env=\'%s\'} == 0 " % env_name,
        "for": "1m",
        "labels": {
            "severity": "critical"
        }
    }
    # 定义服务规则信息
    service_rules = {"name": "App state", "rules": [instance_alert]}
    # 定义包含所有规则组的信息
    dict_total_rules = {"groups": [service_rules]}
    # 从传入的信息中获取服务指标阈值信息
    service_quotes = quotes_info.get("services")
    try:
        # 遍历服务指标阈值信息
        for service_name, service_quote_info in service_quotes.items():
            for service_quote in service_quote_info:
                # 获取指标类型
                index_type = service_quote.get("index_type")
                # 获取告警级别
                alert_level = service_quote.get("alert_level")
                # 获取条件值
                condition_value = service_quote.get("condition_value")
                # 获取条件
                condition = service_quote.get("condition")
                # 定义服务指标告警信息
                quote_info = {
                    "alert": "{} {} alert".format(service_name, index_type),
                    "annotations": {
                        "consignee": "{}".format(""),  # TODO: 待完善收件人信息
                        "description": replace_value(description.get(index_type), condition_value=condition_value),
                        "summary": gen_summary(index_type=index_type),
                    },
                    "expr": replace_value(expr.get(index_type), env_name=env_name, condition=condition,
                                          condition_value=condition_value),
                    "for": "1m",
                    "labels": {
                        "severity": alert_level,
                    }

                }
                # 记录服务指标告警信息
                logger.info(quote_info)
                # 将服务指标告警信息添加到服务规则中
                service_rules["rules"].append(quote_info)
        # 记录开始更新服务告警规则文件的信息
        logger.info('开始更新服务告警规则文件{}'.format(service_rule_yml_path))
        # 以写入模式打开服务规则 YAML 文件，并将规则信息写入文件
        with open(service_rule_yml_path, "w") as fw:
            yaml.dump(dict_total_rules, fw, allow_unicode=True)
        # 记录更新服务告警规则文件成功的信息
        logger.info("更新服务告警规则文件成功")
        return True
    except Exception as e:
        # 记录更新服务告警规则文件失败的错误信息
        logger.error(e)
        return False

def config_update(quotes_info):
    """
    统一更新主机和服务指标文件，并尝试重载 Prometheus 配置

    :param quotes_info: 相关指标阈值信息，示例格式如下：
    {"env_name": "env_code（Env.code，用于规则文件名与 PromQL env 标签）",
    "hosts": [
        {"index_type": "cpu_used","condition": ">=","condition_value": "80","alert_level": "warning"},
        {"index_type": "cpu_used","condition": ">=","condition_value": "90","alert_level": "critical"},
        {"index_type": "memory_used","condition": ">=","condition_value": "80","alert_level": "warning"},
        {"index_type": "memory_used","condition": ">=","condition_value": "90","alert_level": "critical"},
        {"index_type": "disk_root_used","condition": ">=","condition_value": "80","alert_level": "warning"},
        {"index_type": "disk_root_used","condition": ">=","condition_value": "90","alert_level": "critical"},
        {"index_type": "disk_data_used","condition": ">","condition_value": "80","alert_level": "warning"},
        {"index_type": "disk_data_used","condition": ">","condition_value": "90","alert_level": "critical"}
            ],
    "services": {
        "kafka": [
            {"index_type": "kafka_consumergroup_lag","condition": ">","condition_value": 400,"alert_level": "warning"},
            {"index_type": "kafka_consumergroup_lag","condition": ">","condition_value": 600,"alert_level": "critical"}
                ]
                }
    }
    :return: 固定返回 True, None
    """
    # 记录收到阈值更新 JSON 信息
    logger.info('收到阈值更新json：{}'.format(quotes_info))
    # quotes_info = json.loads(quotes_info)
    # 调用更新主机规则文件的函数
    update_node_mark = update_node_rule_yaml(quotes_info)
    if not update_node_mark:
        # 若更新主机规则文件失败，记录错误信息
        logger.error("更新主机告警规则失败")
    # 调用更新服务规则文件的函数
    update_service_mark = update_service_rule_yaml(quotes_info)
    if not update_service_mark:
        # 若更新服务规则文件失败，记录错误信息
        logger.error("更新服务告警规则失败")
    try:
        # 从 promemonitor.prometheus 模块导入 Prometheus 类
        from promemonitor.prometheus import Prometheus
        # 构建重载 Prometheus 配置的 URL
        url = "http://{}/-/reload".format(Prometheus.get_prometheus_config())  # NOQA
        # 发送 POST 请求重载 Prometheus 配置
        response = requests.request("POST", url)
        if response.status_code == 200:
            # 若请求成功，记录重载配置成功信息
            logger.info('重载prometheus配置成功！')
        else:
            # 若请求失败，记录重载配置失败信息
            logger.error('重载prometheus配置失败！')
    except ConnectionRefusedError:
        # 若连接被拒绝，记录重载配置失败信息
        logger.error('重载prometheus配置失败！')
    return True, None


if __name__ == '__main__':
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(
        usage="it's usage tip.", description="help info.")
    # 添加命令行参数 --threshold-json
    parser.add_argument("--threshold-json",
                        dest="threshold_json", help="the json of threshold")
    # 解析命令行参数
    args = parser.parse_args()

    # 获取阈值 JSON 信息
    threshold_json = args.threshold_json

    # 调用配置更新函数
    config_update(threshold_json)
