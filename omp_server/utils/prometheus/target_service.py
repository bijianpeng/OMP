# !/usr/bin/python3
# -*-coding:utf-8-*-
# Author: omp
# CreateDate: 2021/10/22 10:04 下午
# Description: 此模块用于组件巡检，通过多线程的方式采集不同服务的指标信息，并进行数据组装和统计

import json
import random
import logging
import traceback

from db_models.models import Service
from utils.prometheus.thread import MyThread
from utils.prometheus.target_service_jvm_base import ServiceBase
from utils.prometheus.target_service_arangodb import ServiceArangodbCrawl
from utils.prometheus.target_service_beanstalk import ServiceBeanstalkCrawl
from utils.prometheus.target_service_clickhouse import ServiceClickhouseCrawl
from utils.prometheus.target_service_elasticsearch import ServiceElasticsearchCrawl
from utils.prometheus.target_service_flink import ServiceFlinkCrawl
from utils.prometheus.target_service_gotty import ServiceGottyCrawl
from utils.prometheus.target_service_grafana import ServiceGrafanaCrawl
from utils.prometheus.target_service_hadoop import ServiceHadoopCrawl
from utils.prometheus.target_service_httpd import ServiceHttpdCrawl
from utils.prometheus.target_service_ignite import ServiceIgniteCrawl
from utils.prometheus.target_service_ntpd import ServiceNtpdCrawl
from utils.prometheus.target_service_postgresql import ServicePostgresqlCrawl
from utils.prometheus.target_service_prometheus import ServicePrometheusCrawl
from utils.prometheus.target_service_tengine import ServiceTengineCrawl
from utils.prometheus.target_service_mysql import ServiceMysqlCrawl
from utils.prometheus.target_service_redis import ServiceRedisCrawl
from utils.prometheus.target_service_kafka import ServiceKafkaCrawl
from utils.prometheus.target_service_nacos import ServiceNacosCrawl
from utils.prometheus.target_service_rocketmq import ServiceRocketmqCrawl
from utils.prometheus.target_service_zookeeper import ServiceZookeeperCrawl

# 配置日志记录器
logger = logging.getLogger("server")

# 开源服务名称与对应的爬取类的映射字典
open_source_class_dict = {
    "arangodb": ServiceArangodbCrawl,
    "beanstalk": ServiceBeanstalkCrawl,
    "clickhouse": ServiceClickhouseCrawl,
    "elasticsearch": ServiceElasticsearchCrawl,
    "flink": ServiceFlinkCrawl,
    "gotty": ServiceGottyCrawl,
    "grafana": ServiceGrafanaCrawl,
    "hadoop": ServiceHadoopCrawl,
    "httpd": ServiceHttpdCrawl,
    "ignite": ServiceIgniteCrawl,
    "kafka": ServiceKafkaCrawl,
    "mysql": ServiceMysqlCrawl,
    "nacos": ServiceNacosCrawl,
    "ntpd": ServiceNtpdCrawl,
    "postgreSql": ServicePostgresqlCrawl,
    "prometheus": ServicePrometheusCrawl,
    "redis": ServiceRedisCrawl,
    "rocketmq": ServiceRocketmqCrawl,
    "tengine": ServiceTengineCrawl,
    "zookeeper": ServiceZookeeperCrawl
}


def get_port_and_status(i):
    """
    组建巡检：统一获取每个服务的端口信息及服务状态
    从target_service_run方法拆出来一段

    :param i: server表基础信息，包含服务端口和服务状态等字段
    :return: 包含服务端口、服务所有端口列表和服务状态的列表
    """
    # 组装端口
    service_port, service_ports = '', []
    # 解析服务端口信息，如果存在则转换为JSON格式，否则为空列表
    ports = json.loads(i.get('service_port')) if i.get('service_port') else []
    for p in ports:
        # 将每个端口的默认值添加到服务所有端口列表中
        service_ports.append(p.get('default'))
        if p.get('key') == 'service_port':
            # 获取主服务端口
            service_port = p.get('default')

    # 组装服务状态
    serv_status = {0: "正常", 1: "启动中", 2: "停止中", 3: "重启中", 4: "停止"}
    # 根据服务状态码获取对应的状态描述
    service_status = serv_status.get(i.get('service_status'))
    return [service_port, list(set(service_ports)), service_status]


def _joint(i, ret, basics, service_port, service_ports, service_status):
    """
    组件巡检 统一数据组装

    :param i: server表基础信息
    :param ret: 各服务基础数据，字典类型
    :param basics: 各服务拓展数据，列表类型
    :param service_port: 服务端口
    :param service_status: 服务状态
    :param service_ports: 服务全部的端口
    :return: 组装好的包含服务各项信息的字典
    """
    basic = [
        {"name": "port_status", "name_cn": "监听端口", "value": service_ports},
        {"name": "IP", "name_cn": "IP地址", "value": i.get('ip')},
    ] + basics
    return {
        'id': random.randint(1, 99999999),
        'host_ip': i.get('ip'),
        'cluster_name': "-",
        "cpu_usage": ret.get('cpu_usage', '-'),
        "log_level": ret.get('log_level', '-'),
        "mem_usage": ret.get('mem_usage', '-'),
        "run_time": ret.get('run_time', '-'),
        "service_name": i.get('service_instance_name'),
        "service_port": service_port,
        "service_status": service_status,
        "service_type": "2",
        "basic": basic
    }


def target_service_thread(env, i):
    """
    组件数据采集,把顺序执行的代码拷贝出来-多线程执行

    :param env: 环境标识（Env.code，spec §6.4：进入监控链路的一切 env 字符串均为 Env.code）
    :param i: 服务表基础数据(端口/服务名/app_name...)
    :return: 包含总指标数和组装好的服务信息字典的列表
    """
    # 获取每个服务的端口信息及服务状态
    _port_status = get_port_and_status(i)
    if i.get('service__app_monitor', {}).get('type') == 'JavaSpringBoot':
        # 若服务类型为 JavaSpringBoot，使用 ServiceBase 类进行指标采集
        _ = ServiceBase(env, i.get('ip'),
                        f'{i.get("service__app_name")}Exporter')
        _.run()
        # 获取总指标数
        tag_total_num = _.metric_num  
        # 组装服务信息
        tmp = _joint(i, _.ret, _.basic, *_port_status)
    # elif i.get('service__app_monitor', {}).get('type') == 'open_source':  # TODO
    else:
        try:
            # 根据服务名获取对应的爬取类
            crawl_class = open_source_class_dict.get(
                i.get("service__app_name"))
            if not crawl_class:
                return [0, _joint(i, {}, [], *_port_status)]
            # 创建爬取类实例并执行指标采集（env 传 Env.code）
            _ = crawl_class(env=env, instance=i.get('ip'))
            _.run()
            # 获取总指标数
            tag_total_num = _.metric_num  
            # 组装服务信息
            tmp = _joint(i, _.ret, _.basic, *_port_status)
        except Exception as e:
            # 记录服务巡检失败日志
            logger.error(f'服务巡检失败，详情为{traceback.format_exc(e)}')
            # 总指标数置为 0
            tag_total_num = 0  
            ret, basics = {}, []
            # 组装服务信息
            tmp = _joint(i, ret, basics, *_port_status)
    # else:
    #     tag_total_num = 0   # 总指标数 计算
    #     ret, basics = {}, []
    #     tmp = _joint(i, ret, basics, *_port_status)

    return [tag_total_num, tmp]


def target_service_run(env, services):
    """
    组建巡检，多线程执行

    :param env: 环境标识（Env.code，spec §6.4：进入监控链路的一切 env 字符串均为 Env.code）
    :param services: 服务id 列表
    :return: 包含扫描统计信息、扫描结果信息和服务信息列表的元组
    """
    tmp_list = list()
    threads = list()
    # 初始化总指标数、异常指标数
    total_no = error_no = 0
    # 查询该环境（按 Env.code 匹配）下指定ID的服务
    services = Service.objects.filter(env__code=env, id__in=services)
    services = services.values(
        'service_instance_name', 'ip', 'service_port', 'service__app_name',
        'service__app_install_args', 'service_status', 'service__app_monitor')
    for i in services:
        # 创建线程对象
        threads.append(MyThread(func=target_service_thread, args=(env, i)))

    for t in threads:
        # 启动线程
        t.start()

    for t in threads:
        # 等待线程执行结束
        t.join()  
        if not t.res:
            continue
        # 累加总指标数
        total_no += t.res[0]
        # 收集线程返回的服务信息
        tmp_list.append(t.res[1])  

    # 扫描统计信息
    scan_info = {"host": 0, "service": len(services), "component": 0}
    # 分析结果信息
    scan_result = {
        "all_target_num": total_no, "abnormal_target": error_no, "healthy": "-"
    }
    return scan_info, scan_result, tmp_list
