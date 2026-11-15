"""
服务相关异步任务
"""

import logging

from celery import shared_task
from celery.utils.log import get_task_logger
from db_models.models import (
    Service, ServiceHistory
)
from utils.plugin.salt_client import SaltClient
import time
import json
from promemonitor.prometheus_utils import PrometheusUtils
from db_models.models import (
    Host, HostOperateLog, ClusterInfo, Product, SelfHealingHistory, Alert
)
from utils.parse_config import BASIC_ORDER, CLEAR_DB
from django.utils import timezone

from django.db.models import F
from django.db import transaction

# 屏蔽celery任务日志中的paramiko日志
logging.getLogger("paramiko").setLevel(logging.WARNING)
# 获取名为 "celery_log" 的任务日志记录器
logger = get_task_logger("celery_log")


def delete_action(service_obj):
    """
    查询需要删除的目录

    :param service_obj: 服务对象实例
    :return: 用空格连接的需要删除的目录字符串
    """
    # 获取服务的安装详情参数
    install_detail = service_obj.detailinstallhistory_set.first().install_detail_args
    # 定义需要查询的目录类型列表
    dir_list = ["base_dir", "log_dir", "data_dir"]
    # 初始化有效目录列表
    valida_rm = []
    # 遍历安装参数
    # 兼容两种参数键名：老 schema 为 install_args，新前端 payload 原样
    # 落库(executeInstall → new_install_utils)为 app_install_args
    # （与 install_exec unzip 步骤的键名兼容修复 bd017fe 同模式）
    for args in install_detail.get("install_args") or \
            install_detail.get("app_install_args") or []:
        if args.get("key") in dir_list:
            # 获取目录名称
            dir_name = args.get("default")
            if dir_name and len(dir_name) >= 5:
                # 将符合条件的目录添加到有效目录列表
                valida_rm.append(dir_name)
    # 将有效目录列表用空格连接成字符串
    result = " ".join(valida_rm)
    return result


def get_app_dir(service_obj):
    """
    获取服务的 app_dir

    :param service_obj: 服务对象实例
    :return: 服务的 app_dir 路径，如果不符合条件则返回 None
    """
    base_dir = ""
    # 获取服务的安装详情参数
    install_detail_args = service_obj.detailinstallhistory_set.first().install_detail_args
    # 从安装参数中筛选出 base_dir 的默认值
    # （参数键名兼容同上：install_args 优先，回退 app_install_args）
    base_dir_dict = {
        "base_dir":
            args.get("default") for args in (
                install_detail_args.get("install_args") or
                install_detail_args.get("app_install_args") or [])
        if args.get("key") == "base_dir"
    }
    # 获取 base_dir 的值
    base_dir = base_dir_dict.get("base_dir", "")
    if base_dir and len(base_dir) >= 5:
        return base_dir


def delete_file(service_controllers, service_obj):
    """
    执行文件删除操作

    :param service_controllers: 服务控制信息字典
    :param service_obj: 服务对象实例
    :return: 定时任务删除操作和安装路径删除操作结果的逻辑与
    """
    # 创建 Salt 客户端实例
    salt_obj = SaltClient()
    # 获取停止服务的操作命令
    exe_action = service_controllers.get("stop", "")
    if "hadoop" in exe_action and "hadoop3" not in exe_action:
        # 对 hadoop 服务的停止命令进行处理
        scripts_param = exe_action.split()
        if len(scripts_param) > 3:
            return True
        scripts_param[2] = "all"
        exe_action = " ".join(scripts_param)
    # 存在停止脚本则先执行停止脚本
    if exe_action:
        for count in range(2):
            # 执行停止脚本
            is_success, info = salt_obj.cmd(service_obj.ip, exe_action, 600)
            time.sleep(count + 1)
            if is_success is True:
                break
            # 记录停止操作结果
            logger.info(f"执行 [delete] 操作 {is_success}，原因: {info}")
    # 获取需要删除的目录
    base_dir = delete_action(service_obj)
    # 获取服务的 app_dir
    app_dir = get_app_dir(service_obj)
    # TODO 删除定时任务
    # 构建删除定时任务的命令
    cron_del_str = f"crontab -l |grep -v {app_dir} 2>/dev/null | crontab -"
    # 执行删除定时任务的命令
    cmd_res, msg = salt_obj.cmd(
        service_obj.ip, cron_del_str, 600
    )
    # 记录删除定时任务操作结果
    logger.info(f"执行 [delete] crontab操作 {cmd_res}, 原因: {msg}")

    # 删除安装路径
    if base_dir:
        # 执行删除安装路径的命令
        is_success, info = salt_obj.cmd(
            service_obj.ip, f"/bin/rm -rf {base_dir}", 600)
        # 记录删除安装路径操作结果
        logger.info(f"执行 [delete] 操作 {is_success}，原因: {info}")
        return cmd_res and is_success


@shared_task
def exec_action(action, instance, operation_user, del_file=False, need_sleep=True):
    """
    执行服务操作的异步任务

    :param action: 操作类型，对应 action_json 中的键
    :param instance: 服务实例的 ID
    :param operation_user: 操作用户
    :param del_file: 是否删除文件，默认为 False
    :param need_sleep: 是否需要休眠，默认为 True
    :return: 若为删除操作返回 None，其他操作返回 (ip, info)
    """
    # edit by vum: 增加服务的目标成功状态、失败状态
    # 定义操作类型及其对应的操作名称、初始状态、成功状态、失败状态
    action_json = {
        "1": ["start", 1, 0, 4],
        "2": ["stop", 2, 4, 0],
        "3": ["restart", 3, 0, 4],
        "4": ["delete", 4]
    }
    # 定义操作结果的映射
    result_json = {
        True: "success",
        False: "failure"
    }
    try:
        # 根据服务实例 ID 获取服务对象
        service_obj = Service.objects.get(id=instance)
    except Exception as e:
        # 记录服务实例 ID 不存在的错误信息
        logger.error(f"service实例id，不存在{instance}:{e}")
        return None
    # 获取服务所在主机的 IP 地址
    ip = service_obj.ip
    # service_controllers 字段为json字段类型
    # 获取服务的控制信息
    service_controllers = service_obj.service_controllers
    # 根据操作类型获取对应的操作信息
    action = action_json.get(str(action))
    if not action:
        # 记录操作动作不合法的错误信息
        logger.error("action动作不合法")
        raise ValueError("action动作不合法")
    if action[0] == 'delete':
        # 处理删除操作
        service_port = None
        if service_obj.service_port is not None:
            # 解析服务端口信息
            service_port_ls = json.loads(service_obj.service_port)
            if len(service_port_ls) > 0:
                service_port = service_port_ls[0].get("default", "")
        if service_port is not None:
            # 端口存在则删除prometheus监控的
            # 获取服务的应用名称
            ser_name = service_obj.service.app_name
            if ser_name == "hadoop":
                ser_name = service_obj.service_instance_name.split("_", 1)[0]
            # 构建服务数据
            service_data = {
                "service_name": ser_name,
                "instance_name": service_obj.service_instance_name,
                "data_path": None,
                "log_path": None,
                "env": service_obj.env.code,
                "ip": ip,
                "listen_port": service_port
            }
            # 删除 Prometheus 中的服务监控
            PrometheusUtils().delete_service(service_data)
        # 删除hosts实例个数
        # 获取服务历史记录对象
        service_history_obj = ServiceHistory.objects.filter(
            service=service_obj)
        if len(service_history_obj) != 0:
            # 删除服务历史记录
            service_history_obj.delete()
        if del_file:
            # 执行文件删除操作
            is_success = delete_file(service_controllers, service_obj)
        else:
            is_success = True
        # 获取服务所在主机的实例
        host_instances = Host.objects.filter(ip=service_obj.ip)
        for instance in host_instances:
            # 创建主机操作日志
            HostOperateLog.objects.create(username=operation_user,
                                          description=f"卸载服务 [{service_obj.service.app_name}]",
                                          result="success" if is_success else "failed",
                                          host=instance)
        with transaction.atomic():
            # 删除服务对象
            service_obj.delete()
            # 统计该主机上剩余的服务数量
            count = Service.objects.filter(ip=service_obj.ip).count()
            # 更新主机的服务数量
            Host.objects.filter(ip=service_obj.ip).update(
                service_num=count)
            # 当服务被删除时，应该将其所在的集群都连带删除
            if service_obj.cluster and Service.objects.filter(
                    cluster=service_obj.cluster
            ).count() == 0:
                # 删除空集群信息
                ClusterInfo.objects.filter(
                    id=service_obj.cluster.id
                ).delete()
            # 当服务被删除时，如果他所属的产品下已没有其他服务（同环境），
            # 那么应该删除产品实例（同环境，跨环境产品实例互不影响——
            # 多环境架构：Product 实例按环境隔离统计）
            if Service.objects.filter(
                    service__product=service_obj.service.product,
                    env=service_obj.env
            ).count() == 0:
                # 删除空产品实例
                Product.objects.filter(
                    product=service_obj.service.product,
                    env=service_obj.env
                ).delete()
        return None

    # 获取操作命令
    exe_action = service_controllers.get(action[0])
    if exe_action:
        # 创建 Salt 客户端实例
        salt_obj = SaltClient()
        # 更新服务状态为操作初始状态
        service_obj.service_status = action[1]
        service_obj.save()
        # 获取当前时间
        time_array = time.localtime(int(time.time()))
        time_style = time.strftime("%Y-%m-%d %H:%M:%S", time_array)
        # 执行操作命令
        is_success, info = salt_obj.cmd(ip, exe_action, 600)
        # TODO 服务状态维护问题，临时解决方案，休眠保持中间态
        if need_sleep:
            time.sleep(35)
        # 根据操作结果更新服务状态
        service_obj.service_status = action[2] if is_success else action[3]
        service_obj.save()
        # 记录操作结果
        logger.info(f"执行 [{action[0]}] 操作 {is_success}，原因: {info}")
        # 创建服务历史记录
        ServiceHistory.objects.create(
            username=operation_user,
            description=f"执行 [{action[0]}] 操作",
            result=result_json.get(is_success),
            created=time_style,
            service=service_obj
        )
        # 记录服务操作详情
        logger.info(f"服务操作详情:{info}")
        return ip, info
    else:
        # 记录数据库中无对应操作命令的错误信息
        logger.error(f"数据库无{action[0]}动作")
        raise ValueError(f"数据库无{action[0]}动作")


@shared_task
def clear_db(task_id):
    """
    清理数据库中的过期记录
    # ToDo 懒得写了以后优化
    """
    # 计算健康记录的过期时间
    days_ago = timezone.now() - timezone.timedelta(
        days=CLEAR_DB.get('health').get("day", 7)
    )
    # 删除过期的自愈历史记录
    SelfHealingHistory.objects.filter(end_time__lt=days_ago).delete()
    # 计算告警记录的过期时间
    days_ago = timezone.now() - timezone.timedelta(
        days=CLEAR_DB.get('alert').get("day", 7)
    )
    # 删除过期的告警记录
    Alert.objects.filter(create_time__lt=days_ago).delete()
