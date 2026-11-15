#!/usr/bin/python3
# -*-coding:utf-8-*-

from utils.prometheus.prometheus import Prometheus
from utils.plugin.salt_client import SaltClient
import json


class TargetServiceBase(Prometheus):
    """
    所有 Prometheus Target Service 的通用基类。
    封装了查询 target 健康状态、运行时间、CPU/内存使用率等通用方法。
    """

    def __init__(self, env, instance, service_name, metric_num=4):
        """
        初始化基类。

        :param env: 环境标识（Env.code，spec §6.4：进入监控链路的一切 env 字符串均为 Env.code）
        :param instance: 主机 IP
        :param service_name: 服务名称 (例如: mysql, redis) 或 job 名称 (例如: jvmExporter)
        :param metric_num: 初始指标数量
        """
        super().__init__()
        self.ret = {}
        self.basic = []
        self.env = env
        self.instance = instance
        self.service_name = service_name
        self.metric_num = metric_num
        self._salt_client = SaltClient()
        # 定义基础指标的采集方法列表
        self.base_metrics_handler = [
            self.get_service_status,
            self.get_run_time,
            self.get_cpu_usage,
            self.get_mem_usage,
        ]

    def get_service_status(self):
        """
        通用方法：查询服务健康状态 (probe_success)。
        """
        expr = (f"probe_success{{env=~'{self.env}', instance=~'{self.instance}', "
                f"job=~'{self.service_name}|{self.service_name}Exporter', app=~'{self.service_name}|node'}}")
        self.ret['service_status'] = self.unified_job(*self.query(expr))

    def get_run_time(self):
        """
        通用方法：查询服务运行时间 (process_uptime_seconds)。
        """
        expr = (f"process_uptime_seconds{{env=~'{self.env}', instance=~'{self.instance}',"
                f"job=~'{self.service_name}|{self.service_name}Exporter', app=~'{self.service_name}|node'}}")
        uptime = self.unified_job(*self.query(expr))
        uptime = float(uptime) if uptime else 0
        days, rem = divmod(uptime, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, seconds = divmod(rem, 60)
        
        if days > 0:
            self.ret['run_time'] = f"{int(days)}天{int(hours)}小时{int(minutes)}分钟{int(seconds)}秒"
        elif hours > 0:
            self.ret['run_time'] = f"{int(hours)}小时{int(minutes)}分钟{int(seconds)}秒"
        else:
            self.ret['run_time'] = f"{int(minutes)}分钟{int(seconds)}秒"

    def get_cpu_usage(self):
        """
        通用方法：查询服务 CPU 使用率。
        尝试 process_cpu_usage * 100 (jmx_exporter),
        或 service_process_cpu_percent (由 agent push)。
        """
        # JMX Exporter
        expr_jmx = (f"process_cpu_usage{{env=~'{self.env}', instance=~'{self.instance}', "
                    f"job=~'{self.service_name}|{self.service_name}Exporter'}} * 100")
        val = self.unified_job(*self.query(expr_jmx))

        # Agent push
        if not val:
            expr_agent = f"service_process_cpu_percent{{instance='{self.instance}',app='{self.service_name}'}}"
            val = self.unified_job(*self.query(expr_agent))
        
        val = round(float(val), 2) if val else '0.00'
        self.ret['cpu_usage'] = f"{val}%"

    def get_mem_usage(self):
        """
        通用方法：查询服务内存使用率。
        """
        expr = f"service_process_memory_percent{{instance='{self.instance}',app='{self.service_name}'}}"
        val = self.unified_job(*self.query(expr))
        val = round(float(val), 4) if val else '-'
        self.ret['mem_usage'] = f"{val}%"

    def get_metrics_by_salt(self, check_module):
        """
        通过 Salt Client 获取指标并更新 ret 和 basic 字典。
        这是一个通用方法，子类可以通过提供不同的 check_module 来复用。
        :param check_module: 要执行的 Salt check 模块名 (e.g., "flink_check.main")
        """
        try:
            self._salt_client.salt_module_update()
            ret = self._salt_client.fun(self.instance, check_module)
            if ret and ret[0]:
                metrics = json.loads(ret[1])
            else:
                metrics = {}
        except Exception:
            metrics = {}

        # 通用地更新 ret 中的核心指标
        self.ret['cpu_usage'] = metrics.get('cpu_usage', self.ret.get('cpu_usage', '-'))
        self.ret['mem_usage'] = metrics.get('mem_usage', self.ret.get('mem_usage', '-'))
        self.ret['run_time'] = metrics.get('run_time', self.ret.get('run_time', '-'))
        self.ret['service_status'] = metrics.get('service_status', self.ret.get('service_status', '-'))
        
        # 子类可能需要解析 basic 和其他 ret 的指标
        return metrics

    def run(self):
        """
        执行所有在 base_metrics_handler 中定义的基础指标采集。
        子类可以重写此方法，并调用 super().run() 来执行基础采集。
        """
        for handler in self.base_metrics_handler:
            try:
                handler()
            except Exception:
                # 即使某个指标查询失败，也继续执行下一个
                continue 