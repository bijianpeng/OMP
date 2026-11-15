# -*- coding: utf-8 -*-
# Project: parse_config
# Author: omp
# Create time: 2021-09-15 09:26
# IDE: PyCharm
# Version: 1.0
# Introduction:

"""
解析配置文件
"""

import os

from ruamel import yaml

# 获取项目根目录路径
# 首先通过 os.path.abspath(__file__) 获取当前文件的绝对路径
# 然后通过多次调用 os.path.dirname 向上获取三层目录，得到项目根目录
project_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
# 拼接配置文件的完整路径
config_file_path = os.path.join(project_path, "config/omp.yaml")

# 拼接私钥文件的完整路径
private_key_path = os.path.join(project_path, "config/private_key.pem")

# openssl genrsa -out private_key.pem 2048
# openssl rsa -in private_key.pem -out public_key.pem -pubout
# 读取私钥文件内容并存储到 PRIVATE_KEY 变量中
with open(private_key_path, "r", encoding="utf-8") as key_f:
    PRIVATE_KEY = key_f.read()

# 读取配置文件内容并使用 YAML 解析器将其转换为 Python 字典
with open(config_file_path, "r", encoding="utf-8") as fp:
    CONFIG_DIC = yaml.load(fp, Loader=yaml.SafeLoader)

# 从配置字典中获取全局运行用户信息
GLOBAL_RUNUSER = CONFIG_DIC.get("global_runuser")
# 从配置字典中获取本地 IP 地址信息
LOCAL_IP = CONFIG_DIC.get("local_ip")
# 从配置字典中获取 Tengine 端口信息
TENGINE_PORT = CONFIG_DIC.get("tengine")
# 从配置字典中获取 SSH 命令执行超时时间，默认值为 60 秒
SSH_CMD_TIMEOUT = CONFIG_DIC.get("ssh_cmd_timeout", 60)
# 从配置字典中获取 SSH 连接检查超时时间，默认值为 10 秒
SSH_CHECK_TIMEOUT = CONFIG_DIC.get("ssh_check_timeout", 10)
# 从配置字典中获取线程池最大工作线程数，默认值为 20
THREAD_POOL_MAX_WORKERS = CONFIG_DIC.get("thread_pool_max_workers", 20)
# 从配置字典中获取 Salt 主节点返回端口信息，默认值为 19005
SALT_RET_PORT = CONFIG_DIC.get("salt_master", {}).get("ret_port", 19005)
# 从配置字典中获取 Token 过期时间，默认值为 1
TOKEN_EXPIRATION = CONFIG_DIC.get("token_expiration", 1)
# 从配置字典中获取监控端口信息
MONITOR_PORT = CONFIG_DIC.get("monitor_port")
# 从配置字典中获取 Grafana API 密钥信息
GRAFANA_API_KEY = CONFIG_DIC.get("grafana_api_key")
# 从配置字典中获取 Prometheus 认证信息，默认值为空字典
PROMETHEUS_AUTH = CONFIG_DIC.get("prometheus_auth", {})
# 从配置字典中获取 Grafana 认证信息，默认值为空字典
GRAFANA_AUTH = CONFIG_DIC.get("grafana_auth", {})
# 从配置字典中获取 Loki 配置信息，默认值为空字典
LOKI_CONFIG = CONFIG_DIC.get("loki_config", {})
# 从配置字典中获取 Redis 健康检查超时时间，单位为分钟，默认值为 60 分钟
HEALTH_REDIS_TIMEOUT = int(CONFIG_DIC.get("health_redis_timeout", 60)) * 60
# 从配置字典中获取健康检查请求次数，默认值为 6
HEALTH_REQUEST_COUNT = int(CONFIG_DIC.get("health_request_count", 6))
# 从配置字典中获取健康检查请求间隔时间，默认值为 5 秒
HEALTH_REQUEST_SLEEP = int(CONFIG_DIC.get("health_request_sleep", 5))
# 从配置字典中获取需要清理的数据库表信息，默认值为空字典
CLEAR_DB = CONFIG_DIC.get("clear_table", {})
# 从配置字典中获取服务发现信息，默认值为空列表
SERVICE_DISCOVERY = CONFIG_DIC.get("service_discovery", [])

# 优先从环境变量中获取 Redis 主机地址，若未设置则从配置字典中获取
OMP_REDIS_HOST = os.getenv(
    "OMP_REDIS_HOST",
    CONFIG_DIC.get("redis", {}).get("host")
)
# 优先从环境变量中获取 Redis 端口号，若未设置则从配置字典中获取
OMP_REDIS_PORT = os.getenv(
    "OMP_REDIS_PORT",
    CONFIG_DIC.get("redis", {}).get("port")
)
# 优先从环境变量中获取 Redis 密码，若未设置则从配置字典中获取
OMP_REDIS_PASSWORD = os.getenv(
    "OMP_REDIS_PASSWORD",
    CONFIG_DIC.get("redis", {}).get("password")
)

# 优先从环境变量中获取 MySQL 主机地址，若未设置则从配置字典中获取
OMP_MYSQL_HOST = os.getenv(
    "OMP_MYSQL_HOST",
    CONFIG_DIC.get("mysql", {}).get("host")
)
# 优先从环境变量中获取 MySQL 端口号，若未设置则从配置字典中获取
OMP_MYSQL_PORT = os.getenv(
    "OMP_MYSQL_PORT",
    CONFIG_DIC.get("mysql", {}).get("port")
)
# 优先从环境变量中获取 MySQL 用户名，若未设置则从配置字典中获取
OMP_MYSQL_USERNAME = os.getenv(
    "OMP_MYSQL_USERNAME",
    CONFIG_DIC.get("mysql", {}).get("username")
)
# 优先从环境变量中获取 MySQL 密码，若未设置则从配置字典中获取
OMP_MYSQL_PASSWORD = os.getenv(
    "OMP_MYSQL_PASSWORD",
    CONFIG_DIC.get("mysql", {}).get("password")
)

# 从配置字典中获取基础排序信息，默认值为空字典
BASIC_ORDER = CONFIG_DIC.get("basic_order", {})
# 从配置字典中获取亲和性字段信息，默认值为空字典
AFFINITY_FIELD = CONFIG_DIC.get("affinity", {})
# 从配置字典中获取 Hadoop 角色信息，默认值为空字典
HADOOP_ROLE = CONFIG_DIC.get("hadoop_role", {})
# 从配置字典中获取主机名前缀信息，默认值为 "omp-"
HOSTNAME_PREFIX = CONFIG_DIC.get("hostname_prefix", "omp-")
# 从配置字典中获取备份服务信息，默认值为空列表
BACKUP_SERVICE = CONFIG_DIC.get("backup_service", [])
