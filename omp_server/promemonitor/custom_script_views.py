# !/usr/bin/python3
# 指定使用 Python 3 解释器运行该脚本

# -*-coding:utf-8-*-
# 指定文件的编码格式为 UTF-8

# Author:' Lingyang.guo'
# 代码作者信息

# CreateDate: 14:08
# 代码创建时间，缺少日期信息

import json
import logging
import os.path
import traceback

import requests
import yaml
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from rest_framework.mixins import ListModelMixin, CreateModelMixin, UpdateModelMixin, DestroyModelMixin
from rest_framework.serializers import Serializer
from rest_framework.viewsets import GenericViewSet
from rest_framework.response import Response

# from db_models.models import UploadFileHistory
# 从数据库模型模块导入 CustomScript 模型，用于操作自定义脚本记录
from db_models.models.custom_metric import CustomScript
# 从自定义脚本序列化器模块导入 CustomScriptSerializer 类，用于序列化自定义脚本数据
from promemonitor.custom_script_serializers import CustomScriptSerializer
# 从自定义脚本过滤模块导入 CustomScriptFilter 类，用于过滤自定义脚本数据
from promemonitor.promemonitor_filters import CustomScriptFilter
# 从通用分页模块导入 PageNumberPager 类，用于自定义脚本列表的分页
from utils.common.paginations import PageNumberPager
# 从 Prometheus 工具模块导入 PrometheusUtils 类，用于操作 Prometheus 相关配置
from promemonitor.prometheus_utils import PrometheusUtils
# 从配置解析模块导入 MONITOR_PORT 配置信息，用于获取监控端口
from utils.parse_config import MONITOR_PORT
# 从工具中间件模块导入环境上下文获取函数
from utils.middleware_handler import get_request_env
# 从 Prometheus 工具模块导入 CW_TOKEN，用于认证信息
from promemonitor.prometheus_utils import CW_TOKEN

# 获取名为 'server' 的日志记录器，用于记录程序运行过程中的信息
logger = logging.getLogger('server')


class CustomScriptViewSet(GenericViewSet, ListModelMixin, CreateModelMixin, UpdateModelMixin, DestroyModelMixin):
    """
    list:
    查询自定义脚本列表

    create:
    新增自定义脚本记录

    update:
    更新自定义脚本模型字段

    delete:
    删除指定自定义脚本
    """
    # 获取自定义脚本记录的描述信息
    get_description = "读取自定义脚本记录"
    # 更新自定义脚本记录的描述信息
    post_description = "更新自定义脚本记录"
    # 指定序列化器类，用于将 CustomScript 模型实例序列化为 JSON 数据
    serializer_class = CustomScriptSerializer
    # 指定分页器类，用于对自定义脚本列表进行分页
    pagination_class = PageNumberPager
    # 过滤和排序的后端类，支持 Django 过滤和排序功能
    filter_backends = (DjangoFilterBackend, OrderingFilter)
    # 查询所有自定义脚本记录，并按创建时间倒序排列
    queryset = CustomScript.objects.all().order_by("-created")
    # 指定过滤类，用于对自定义脚本记录进行过滤
    filter_class = CustomScriptFilter

    # 创建 PrometheusUtils 类的实例，用于操作 Prometheus 相关配置
    prometheus_util = PrometheusUtils()

    def list(self, request, *args, **kwargs):
        """
        获取自定义脚本列表信息
        """
        # 对查询集进行过滤、排序操作
        queryset = self.filter_queryset(self.get_queryset())

        # 对查询集进行分页操作
        page = self.paginate_queryset(queryset)
        if page is not None:
            # 若分页成功，对分页后的结果进行序列化
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # 若未分页，对整个查询集进行序列化
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """
        新增一条自定义脚本记录
        """
        # 从请求中获取上传的文件对象
        file_obj = request.FILES.get('file')

        # 获取上传文件的名称
        script_name = file_obj.name
        # 检查数据库中是否已存在同名的自定义脚本
        if CustomScript.objects.filter(script_name=script_name).exists():
            return Response(data={"code": 1, "message": "该脚本已存在，请重新上传！"})
        # 从请求数据中获取抓取间隔，默认值为 60
        scrape_interval = request.data.get("scrape_interval", 60)
        # 从请求数据中获取启用状态，默认值为 1
        enabled = request.data.get("enabled", 1)

        # 读取文件内容
        script_content = file_obj.read()
        # 将文件内容转换为字符串，使用 UTF-8 编码
        script_content = str(script_content, encoding="utf8")
        # 初始化指标列表
        metrics = list()
        # 遍历脚本内容的每一行
        for line in script_content.split("\n"):
            if "def get_" in line and ":" in line:
                # 提取指标名称
                metric = line.split("def get_")[1].split("(")[0].strip()
                metrics.append(metric)
        # 计算指标数量
        metric_num = len(metrics)
        # 获取脚本内容的第一行为描述信息
        description = script_content.split("\n")[0]

        try:
            # 创建 CustomScript 模型实例
            custom_script = CustomScript(
                script_name=script_name,
                script_content=script_content,
                metrics=metrics,
                metric_num=metric_num,
                scrape_interval=scrape_interval,
                enabled=enabled,
                description=description,
                bound_hosts=[]
            )
            # 保存自定义脚本记录到数据库
            custom_script.save()
            # UploadFileHistory.location(file=file_obj, module_obj=custom_script, user=request.user)
            # 提取脚本作业名称
            script_job_str = script_name.split('.', 1)[0]
            # 构造 Prometheus 作业配置字典
            prom_job_dict = {
                "job_name": f"{script_job_str}Exporter",
                "metrics_path": f"/metrics/monitor/{script_job_str}",
                "file_sd_configs": [
                    {
                        "refresh_interval": f"{scrape_interval}s",
                        "files": [
                            f"targets/{script_job_str}Exporter_all.json"
                        ]
                    }
                ]
            }
            # 读取 Prometheus 配置文件
            with open(self.prometheus_util.prometheus_conf_path, "r") as fr:
                content = yaml.load(fr.read(), yaml.Loader)
            # 将新的作业配置添加到 Prometheus 配置中
            content.get("scrape_configs").append(prom_job_dict)
            # 将更新后的配置写回 Prometheus 配置文件
            with open(self.prometheus_util.prometheus_conf_path, "w", encoding="utf8") as fw:
                yaml.dump(data=content, stream=fw,
                          allow_unicode=True, sort_keys=False)
            # 构造作业目标 JSON 文件路径
            job_target_json = os.path.join(self.prometheus_util.prometheus_targets_path,
                                           f"{script_job_str}Exporter_all.json")
            # 若作业目标 JSON 文件不存在，则创建并写入空列表
            if not os.path.exists(job_target_json):
                with open(job_target_json, "w") as target_fw:
                    json.dump([], target_fw)
            # Prometheus 重载配置的 URL
            reload_prometheus_url = "http://localhost:19011/-/reload"
            # 发送 POST 请求重载 Prometheus 配置
            requests.post(reload_prometheus_url,
                          auth=self.prometheus_util.basic_auth)
            return Response({})
        except Exception as e:
            # 记录异常信息
            logger.error(traceback.format_exc(e))
            return Response(data={"code": 1, "message": "新增自定义脚本失败！"})

    def update(self, request, *args, **kwargs):
        """
        只可以更改绑定主机列表，启用状态和探测周期
        """
        # 获取要更新的自定义脚本实例
        instance = self.get_object()
        # 从请求数据中获取新的抓取间隔
        new_scrape_interval = request.data.get("scrape_interval")
        # 从请求数据中获取新的启用状态，默认值为 1
        new_enabled = request.data.get("enabled", 1)
        # 从请求数据中获取新的绑定主机列表
        new_bound_host_list = request.data.get("bound_hosts")
        # 从请求数据中获取新的描述信息，若未提供则使用原描述信息
        new_description = request.data.get("description", instance.description)

        # 计算新增的主机列表
        add_host_list = set(new_bound_host_list) - set(instance.bound_hosts)
        # 计算删除的主机列表
        deleted_host_list = set(instance.bound_hosts) - \
            set(new_bound_host_list)

        # 更新自定义脚本实例的抓取间隔
        instance.scrape_interval = new_scrape_interval
        # 更新自定义脚本实例的启用状态
        instance.enabled = new_enabled
        # 更新自定义脚本实例的绑定主机列表
        instance.bound_hosts = new_bound_host_list
        # 更新自定义脚本实例的描述信息
        instance.description = new_description
        # 保存更新后的自定义脚本实例到数据库
        instance.save()

        # 构造请求头，指定内容类型为 JSON
        headers = {"Content-Type": "application/json"}
        # 更新请求头，添加认证信息
        headers.update(CW_TOKEN)

        try:
            # 提取脚本作业名称
            script_job_str = instance.script_name.split('.', 1)[0]
            # 初始化 Prometheus 目标列表
            prom_target_list = list()
            # 获取监控代理的端口号，默认值为 19031
            monitor_agent_port = MONITOR_PORT.get('monitorAgent', 19031)
            # 遍历新增和删除的主机列表
            for item in (add_host_list | deleted_host_list):
                if item in add_host_list:
                    # 若为主机新增，构造添加自定义脚本的 URL
                    agent_custom_script_url = f"http://{item}:{monitor_agent_port}/update/custom_scripts/add"  # NOQA
                elif item in deleted_host_list:
                    # 若为主机删除，构造删除自定义脚本的 URL
                    agent_custom_script_url = f"http://{item}:{monitor_agent_port}/update/custom_scripts/delete"  # NOQA
                else:
                    continue
                # 构造请求负载
                payload = {
                    "custom_scripts":
                        [{
                            "script_name": script_job_str,
                            "script_content": instance.script_content,
                            "script_metrics": instance.metrics
                        }]
                }
                # 将请求负载转换为 JSON 字符串
                payload = json.dumps(payload)
                # 发送 POST 请求到监控代理
                res = requests.post(
                    url=agent_custom_script_url, headers=headers, data=payload)
                if res.status_code != 200:
                    # 若请求失败，记录错误信息并返回响应
                    logger.error(f"向主机{item}agent发送添加自定义脚本信息失败！")
                    return Response(data={"code": 1, "message": f"向主机{item}agent发送添加自定义脚本信息失败！"})

            # 遍历绑定的主机列表，构造 Prometheus 目标信息
            # （env label 取当前请求环境 code，spec §6.4）
            env = get_request_env(request)
            for host in instance.bound_hosts:
                prom_target_list.append({
                    "targets": [
                        f"{host}:{monitor_agent_port}"
                    ],
                    "labels": {
                        "instance": f"{host}",
                        "service_type": "service",
                        "env": env.code
                    }
                })

            # 构造作业目标 JSON 文件路径
            job_target_json = os.path.join(self.prometheus_util.prometheus_targets_path,
                                           f"{script_job_str}Exporter_all.json")
            # 将 Prometheus 目标列表写入作业目标 JSON 文件
            with open(job_target_json, "w") as jtj_fw:
                json.dump(prom_target_list, jtj_fw, indent=4)
        except Exception as e:
            # 记录异常信息
            logger.error(traceback.format_exc(e))
            logger.error("向agent发送添加自定义脚本信息失败！")
            return Response(data={"code": 1, "message": "添加自定义脚本信息失败！"})

        return Response()

    def destroy(self, request, *args, **kwargs):
        """
        向agent发送删除该自定义脚本信息；删除prometheus任务；删除库记录
        """
        # 获取要删除的自定义脚本实例
        instance = self.get_object()
        # 提取脚本作业名称
        script_job_str = instance.script_name.split('.', 1)[0]
        # 读取 Prometheus 配置文件
        with open(self.prometheus_util.prometheus_conf_path, "r") as fr:
            content = yaml.load(fr.read(), yaml.Loader)
        # 遍历 Prometheus 配置中的作业列表，删除对应的作业配置
        for i in content.get("scrape_configs"):
            if i.get("job_name") == f"{script_job_str}Exporter":
                content.get("scrape_configs").remove(i)
        # 将更新后的配置写回 Prometheus 配置文件
        with open(self.prometheus_util.prometheus_conf_path, "w", encoding="utf8") as fw:
            yaml.dump(data=content, stream=fw,
                      allow_unicode=True, sort_keys=False)
        # 构造作业目标 JSON 文件路径
        job_target_json = os.path.join(self.prometheus_util.prometheus_targets_path,
                                       f"{script_job_str}Exporter_all.json")

        # 若作业目标 JSON 文件存在，则删除该文件
        if os.path.exists(job_target_json):
            os.remove(job_target_json)
        # 若绑定主机列表为空，直接删除自定义脚本记录
        if len(instance.bound_hosts) == 0:
            instance.delete()
            return Response({})
        # 获取监控代理的端口号，默认值为 19031
        monitor_agent_port = MONITOR_PORT.get('monitorAgent', 19031)
        # 构造请求头，指定内容类型为 JSON
        headers = {"Content-Type": "application/json"}
        # 更新请求头，添加认证信息
        headers.update(CW_TOKEN)
        # 遍历绑定的主机列表，发送删除自定义脚本的请求
        for host in instance.bound_hosts:
            agent_delete_custom_script_url = f"http://{host}:{monitor_agent_port}/update/custom_scripts/delete"  # NOQA
            # 构造请求负载
            payload = {
                "custom_scripts":
                    [{
                        "script_name": script_job_str
                    }]
            }
            # 将请求负载转换为 JSON 字符串
            payload = json.dumps(payload)
            # 发送 POST 请求到监控代理
            res = requests.post(
                url=agent_delete_custom_script_url, headers=headers, data=payload)
            if res.status_code != 200:
                # 若请求失败，记录错误信息并返回响应
                logger.error(f"向主机{host}agent发送删除自定义脚本信息失败！")
                return Response(data={"code": 1, "message": f"向主机{host}agent发送删除自定义脚本信息失败！"})
        # 删除自定义脚本记录
        instance.delete()
        return Response({})


class CustomScriptJobInfoView(GenericViewSet, ListModelMixin):
    # 读取自定义脚本任务信息的描述
    get_description = "读取自定义脚本任务信息"
    # 序列化器类
    serializer_class = Serializer

    # 创建 PrometheusUtils 类的实例，用于操作 Prometheus 相关配置
    prometheus_util = PrometheusUtils()

    def list(self, request, *args, **kwargs):
        """
        读取自定义脚本任务信息
        """
        # 从请求查询参数中获取自定义脚本的 ID
        cs_id = request.query_params.get("id")
        # 根据 ID 获取自定义脚本实例
        instance = CustomScript.objects.get(id=cs_id)
        # 提取脚本作业名称
        script_job_str = instance.script_name.split('.', 1)[0]
        # 构造作业名称
        job_str = f"{script_job_str}Exporter"
        # 构造 Prometheus 目标信息的 URL
        prometheus_targets_url = f"http://127.0.0.1:{MONITOR_PORT.get('prometheus', '19011')}/api/v1/targets"
        try:
            # 发送 GET 请求获取 Prometheus 目标信息
            res = requests.get(url=prometheus_targets_url,
                               auth=self.prometheus_util.basic_auth)
            if res.status_code != 200:
                # 若请求失败，返回错误响应
                return Response(data={"code": 1, "message": "获取自定义脚本任务信息失败！"})
            # 获取响应中的活跃目标列表
            active_targets_list = res.json().get("data").get("activeTargets")
            # 初始化自定义脚本作业信息列表
            custom_script_job_list = list()
            # 遍历活跃目标列表，提取自定义脚本作业信息
            for active_target in active_targets_list:
                if active_target.get("scrapePool") == job_str:
                    custom_script_job_info = {
                        "scrape_url": active_target.get("scrapeUrl"),
                        "status": active_target.get("health"),
                        "last_scrape_duration": active_target.get("lastScrapeDuration"),
                        "last_error": active_target.get("lastError")
                    }
                    custom_script_job_list.append(custom_script_job_info)
            # 返回自定义脚本作业信息列表
            return Response(custom_script_job_list)
            # return Response(data={"code": 1, "message": "获取自定义脚本任务信息失败！"})
        except Exception as e:
            # 记录异常信息
            logger.error(traceback.format_exc(e))
            return Response(data={"code": 1, "message": "获取自定义脚本任务信息失败！"})
