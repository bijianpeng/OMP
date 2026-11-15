# !/usr/bin/python3
# -*-coding:utf-8-*-
# Author: omp
# CreateDate: 2021/10/14 6:26 下午
# Description: 主机指标
import json
import logging
import random
from datetime import datetime
from db_models.models import Host
from utils.plugin.salt_client import SaltClient
from utils.prometheus.prometheus import Prometheus
from utils.prometheus.utils import get_host_data_folder

# 获取名为 "server" 的日志记录器
logger = logging.getLogger("server")


def target_host_thread(env, instance):
    """
    主机巡检，多线程执行
    :param env: 环境标识（Env.code，spec §6.4：进入监控链路的一切 env 字符串均为 Env.code）
    :param instance: 主机ip地址
    :return: 包含主机巡检信息的字典
    """
    # 初始化存储主机巡检信息的字典
    temp = dict()
    # 主机 prometheus 数据请求，创建 HostCrawl 实例（env 传 Env.code）
    h_w_obj = HostCrawl(env=env, instance=instance)
    # 执行主机指标查询
    h_w_obj.run()
    # 获取查询结果
    _p = h_w_obj.ret
    # 为结果字典添加唯一 id
    temp['id'] = random.randint(1, 99999999)
    # 添加内存使用率
    temp['mem_usage'] = _p.get('mem_usage')
    # 添加 CPU 使用率
    temp['cpu_usage'] = _p.get('cpu_usage')
    # 添加根分区磁盘使用率
    temp['disk_usage_root'] = _p.get('disk_usage_root')
    # 添加数据分区磁盘使用率
    temp['disk_usage_data'] = _p.get('disk_usage_data')
    # 添加系统平均负载
    temp['sys_load'] = _p.get('sys_load')
    # 添加主机运行时间
    temp['run_time'] = _p.get('run_time')
    # 添加主机 IP 地址
    temp['host_ip'] = instance
    # 添加内存使用排名靠前的进程信息
    temp['memory_top'] = _p.get('memory_top', [])
    # 添加 CPU 使用排名靠前的进程信息
    temp['cpu_top'] = _p.get('cpu_top', [])
    # 添加内核参数信息
    temp['kernel_parameters'] = _p.get('kernel_parameters', [])
    # 操作系统，从数据库中获取主机信息
    _h = Host.objects.filter(ip=instance).first()
    # 添加操作系统版本信息
    temp['release_version'] = _h.operate_system if _h else ''
    # 配置信息，拼接主机 CPU、内存和磁盘信息
    host_massage = \
        f"{_h.cpu if _h else '-'}C|{_h.memory if _h else '-'}G|" \
        f"{sum(_h.disk.values()) if _h and _h.disk else '-'}G"
    # 添加主机配置信息
    temp['host_massage'] = host_massage
    # 添加主机基础信息列表
    temp['basic'] = [
        {"name": "IP", "name_cn": "主机IP", "value": instance},
        {"name": "hostname", "name_cn": "主机名",
         "value": _h.host_name if _h else '-'},
        {"name": "kernel_version", "name_cn": "内核版本",
         "value": _p.get('kernel_version')},
        {"name": "selinux", "name_cn": "SElinux 状态",
         "value": _p.get('selinux')},
        {"name": "max_openfile", "name_cn": "最大打开文件数",
         "value": _p.get('max_openfile')},
        {"name": "iowait", "name_cn": "IOWait", "value": _p.get('iowait')},
        {"name": "inode_usage", "name_cn": "inode 使用率",
         "value": {"/": _p.get('inode_usage')}},
        {"name": "now_time", "name_cn": "当前时间",
         "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"name": "run_process", "name_cn": "进程数",
         "value": _p.get('run_process')},
        {"name": "umask", "name_cn": "umask", "value": _p.get('umask')},
        {"name": "bandwidth", "name_cn": "带宽", "value": _p.get('bandwidth')},
        {"name": "throughput", "name_cn": "IO", "value": _p.get('throughput')},
        {"name": "zombies_process", "name_cn": "僵尸进程",
         "value": _p.get('zombies_process')}
    ]
    return temp


class HostCrawl(Prometheus):
    """
    查询 prometheus 主机指标
    """

    def __init__(self, env, instance):
        # 初始化存储查询结果的字典
        self.ret = {}
        # 环境标识（Env.code，PromQL env 标签取值）
        self.env = env
        # 主机 IP 地址
        self.instance = instance
        # 创建 SaltClient 实例
        self._obj = SaltClient()
        # 调用父类 Prometheus 的构造函数
        Prometheus.__init__(self)

    @staticmethod
    def unified_job(is_success, ret):
        """
        实例方法 返回值统一处理
        :param ret: 返回值
        :param is_success: 请求是否成功
        :return: 处理后的返回值
        """
        if is_success:
            if ret.get('result'):
                # 若请求成功且有结果，返回结果中的第一个值
                return ret['result'][0].get('value')[1]
            else:
                # 若请求成功但无结果，返回 0
                return 0
        else:
            # 若请求失败，返回 0
            return 0

    def run_status(self):
        """运行状态"""
        # 构造 Prometheus 查询表达式
        expr = f"round(up{{env='{self.env}', instance='{self.instance}', " \
               f"job='nodeExporter'}})"
        # 执行查询并处理返回值，将结果存入 ret 字典
        self.ret['run_status'] = self.unified_job(*self.query(expr))

    def run_time(self):
        """运行时间"""
        # 构造 Prometheus 查询表达式
        expr = f"avg(time() - node_boot_time_seconds{{env='{self.env}'," \
               f"instance=~'{self.instance}'}})"
        # 执行查询并处理返回值
        _ = self.unified_job(*self.query(expr))
        # 将返回值转换为浮点数，若为 None 则赋值为 0
        _ = float(_) if _ else 0
        # 计算分钟和秒数
        minutes, seconds = divmod(_, 60)
        # 计算小时和分钟数
        hours, minutes = divmod(minutes, 60)
        # 计算天数和小时数
        days, hours = divmod(hours, 24)
        if int(days) > 0:
            # 若运行天数大于 0，格式化运行时间
            self.ret['run_time'] = \
                f"{int(days)}天{int(hours)}小时{int(minutes)}分钟{int(seconds)}秒"
        elif int(hours) > 0:
            # 若运行小时数大于 0，格式化运行时间
            self.ret['run_time'] = \
                f"{int(hours)}小时{int(minutes)}分钟{int(seconds)}秒"
        else:
            # 若运行小时数小于等于 0，格式化运行时间
            self.ret['run_time'] = f"{int(minutes)}分钟{int(seconds)}秒"

    def cpu_usage(self):
        """总cpu使用率"""
        # 构造 Prometheus 查询表达式
        expr = f"100 - (avg(rate(node_cpu_seconds_total" \
               f"{{env='{self.env}'," \
               f"instance=~'{self.instance}'," \
               f"mode='idle'}}[5m])) * 100)"
        # 执行查询并处理返回值，将结果格式化后存入 ret 字典
        self.ret['cpu_usage'] = \
            f"{round(float(self.unified_job(*self.query(expr))), 2)}%"

    def iowait(self):
        """IO wait使用率"""
        # 构造 Prometheus 查询表达式
        expr = f"avg(rate(node_cpu_seconds_total{{env='{self.env}'," \
               f"instance=~'{self.instance}',mode='iowait'}}[5m])) * 100"
        # 执行查询并处理返回值，将结果格式化后存入 ret 字典
        self.ret['iowait'] = \
            f"{round(float(self.unified_job(*self.query(expr))), 2)}%"

    def mem_usage(self):
        """内存使用率"""
        # 构造 Prometheus 查询表达式
        expr = f"(1 - (node_memory_MemAvailable_bytes" \
               f"{{env='{self.env}'," \
               f"instance=~'{self.instance}'}} / " \
               f"(node_memory_MemTotal_bytes{{env='{self.env}'," \
               f"instance=~'{self.instance}'}})))* 100"
        # 执行查询并处理返回值，将结果格式化后存入 ret 字典
        self.ret['mem_usage'] = \
            f"{round(float(self.unified_job(*self.query(expr))), 2)}%"

    def disk_usage_root(self):
        """根分区使用率"""
        # 构造 Prometheus 查询表达式
        expr = f"(node_filesystem_size_bytes{{env='{self.env}'," \
               f"instance=~'{self.instance}'," \
               f"fstype=~'ext.*|xfs',mountpoint='/'}} - " \
               f"node_filesystem_avail_bytes{{env='{self.env}'," \
               f"instance=~'{self.instance}'," \
               f"fstype=~'ext.*|xfs',mountpoint='/'}}) / " \
               f"node_filesystem_size_bytes{{env='{self.env}'," \
               f"instance=~'{self.instance}'," \
               f"fstype=~'ext.*|xfs',mountpoint='/'}} * 100"
        # 执行查询并处理返回值，将结果格式化后存入 ret 字典
        self.ret['disk_usage_root'] = \
            f"{round(float(self.unified_job(*self.query(expr))), 2)}%"

    def disk_usage_data(self):
        """数据分区使用率"""
        # 数据分区应该由主机表中的data_folder目录决定
        # 并协同disk信息判断出数据分区挂载点是哪个
        _data_path = get_host_data_folder(self.instance)
        if not _data_path:
            # 若未获取到数据分区路径，返回占位符
            return "_"
        # 构造 Prometheus 查询表达式
        expr = f"(1-(node_filesystem_free_bytes{{env='{self.env}'," \
               f"instance=~'{self.instance}',mountpoint='{_data_path}', " \
               f"fstype=~'ext.*|xfs'}}" \
               f" / node_filesystem_size_bytes{{env='{self.env}'," \
               f"instance=~'{self.instance}',mountpoint='{_data_path}', " \
               f"fstype=~'ext.*|xfs'}}))" \
               f" * 100"
        # 执行查询并处理返回值
        _ = self.unified_job(*self.query(expr))
        # 将结果格式化后存入 ret 字典，若返回值为 None 则存入占位符
        self.ret['disk_usage_data'] = f"{round(float(_), 2)}%" if _ else '_'

    def rate_exchange_disk(self):
        """交换分区使用率"""
        # 构造 Prometheus 查询表达式
        expr = f"(1 - (node_memory_SwapFree_bytes{{env='{self.env}'," \
               f"instance=~'{self.instance}'}} / " \
               f"node_memory_SwapTotal_bytes{{env='{self.env}'," \
               f"instance=~'{self.instance}'}})) * 100"
        # 执行查询并处理返回值，将结果存入 ret 字典
        self.ret['rate_exchange_disk'] = self.unified_job(*self.query(expr))

    def rate_cpu_io_wait(self):
        """cpu io wait"""
        # 构造 Prometheus 查询表达式
        expr = f"avg(rate(node_cpu_seconds_total" \
               f"{{instance=~'{self.instance}',mode='iowait'}}[5m])) * 100"
        # 执行查询并处理返回值，将结果存入 ret 字典
        self.ret['rate_cpu_io_wait'] = self.unified_job(*self.query(expr))

    def inode_usage(self):
        """inode使用率"""
        # 构造 Prometheus 查询表达式
        expr = f"(1-node_filesystem_files_free{{fstype=~'xfs|ext4'," \
               f"mountpoint='/', env='{self.env}'," \
               f"instance=~'{self.instance}'}} / " \
               f"node_filesystem_files{{fstype=~'xfs|ext4',mountpoint='/', " \
               f"env='{self.env}',instance=~'{self.instance}'}})*100"
        # 执行查询并处理返回值，将结果格式化后存入 ret 字典
        self.ret['inode_usage'] = \
            f"{round(float(self.unified_job(*self.query(expr))), 2)}%"

    def max_openfile(self):
        """总文件描述符"""
        # 构造 Prometheus 查询表达式
        expr = f"avg(node_filefd_maximum{{instance=~'{self.instance}'}})"
        # 执行查询并处理返回值，将结果存入 ret 字典
        self.ret['max_openfile'] = self.unified_job(*self.query(expr))

    def sys_load(self):
        """系统平均负载"""
        # 1分钟负载，构造 Prometheus 查询表达式
        expr = f"node_load1{{env='{self.env}',instance=~'{self.instance}'}}"
        # 执行查询并处理返回值
        load1 = self.unified_job(*self.query(expr))
        # 5分钟负载，构造 Prometheus 查询表达式
        expr = f"node_load5{{env='{self.env}',instance=~'{self.instance}'}}"
        # 执行查询并处理返回值
        load5 = self.unified_job(*self.query(expr))
        # 15分钟负载，构造 Prometheus 查询表达式
        expr = f"node_load15{{env='{self.env}',instance=~'{self.instance}'}}"
        # 执行查询并处理返回值
        load15 = self.unified_job(*self.query(expr))
        # 将不同时间段的负载信息拼接后存入 ret 字典
        self.ret['sys_load'] = f"{load1},{load5},{load15}"

    def bandwidth(self):
        """网络带宽使用"""
        # eth0 下载，构造 Prometheus 查询表达式
        expr = f"sum(rate(node_network_receive_bytes_total{{env='{self.env}'," \
               f"instance=~'{self.instance}',device=~'eth0'}}[2m])*8/1024)"
        # 执行查询并处理返回值，将结果格式化后存入 ret 字典
        self.ret['bandwidth'] = {
            'receive': f"{round(float(self.unified_job(*self.query(expr))), 2)}"
                       f"kb/s"}
        # eth0 上传，构造 Prometheus 查询表达式
        expr = f"sum(rate(node_network_transmit_bytes_total" \
               f"{{env='{self.env}',instance=~'{self.instance}'," \
               f"device=~'eth0'}}[2m])*8/1024)"
        # 执行查询并处理返回值，将结果格式化后存入 ret 字典
        self.ret['bandwidth']['transmit'] = \
            f"{round(float(self.unified_job(*self.query(expr))), 2)}kb/s"

    def throughput(self):
        """磁盘io"""
        # 读，构造 Prometheus 查询表达式
        expr = f"sum(rate(node_disk_read_bytes_total{{env='{self.env}'," \
               f"instance=~'{self.instance}'}}[2m])) / 1024"
        # 执行查询并处理返回值，将结果格式化后存入 ret 字典
        self.ret['throughput'] = \
            {'read': f"{round(float(self.unified_job(*self.query(expr))), 2)}"
                     f"kb/s"}
        # 写，构造 Prometheus 查询表达式
        expr = f"sum(rate(node_disk_written_bytes_total" \
               f"{{env='{self.env}'," \
               f"instance=~'{self.instance}'}}[2m])) / 1024"
        # 执行查询并处理返回值，将结果格式化后存入 ret 字典
        self.ret['throughput']['write'] = \
            f"{round(float(self.unified_job(*self.query(expr))), 2)}kb/s"

    def salt_json(self):
        try:
            # 更新 Salt 自定义模块
            self._obj.salt_module_update()
            # 执行 Salt 命令获取主机检查信息
            ret = self._obj.fun(self.instance, "host_check.main")
            if ret and ret[0]:
                # 若命令执行成功，将返回结果解析为 JSON 格式
                ret = json.loads(ret[1])
            else:
                # 若命令执行失败，初始化返回结果为空字典
                ret = {}
        except Exception as e:
            # 若执行过程中出现异常，记录错误日志
            logger.error(f"Salt host_check.main failed with error: {str(e)}")
            # 初始化返回结果为空字典
            ret = {}

        # 将 Salt 命令返回的内存使用排名靠前的进程信息存入 ret 字典
        self.ret['memory_top'] = ret.get('memory_top', [])
        # 将 Salt 命令返回的 CPU 使用排名靠前的进程信息存入 ret 字典
        self.ret['cpu_top'] = ret.get('cpu_top', [])
        # 将 Salt 命令返回的内核参数信息存入 ret 字典
        self.ret['kernel_parameters'] = ret.get('kernel_parameters', [])
        # 将 Salt 命令返回的内核版本信息存入 ret 字典
        self.ret['kernel_version'] = ret.get('kernel_version')
        # 将 Salt 命令返回的 SELinux 状态信息存入 ret 字典
        self.ret['selinux'] = ret.get('selinux')
        # 将 Salt 命令返回的进程数信息存入 ret 字典
        self.ret['run_process'] = ret.get('run_process')
        # 将 Salt 命令返回的 umask 信息存入 ret 字典
        self.ret['umask'] = ret.get('umask')
        # 将 Salt 命令返回的僵尸进程数信息存入 ret 字典
        self.ret['zombies_process'] = ret.get('zombies_process')

    def run(self):
        """统一执行实例方法"""
        # target为实例方法，目的是统一执行实例方法并统一返回值
        target = ['mem_usage', 'cpu_usage', 'disk_usage_root',
                  'disk_usage_data', 'sys_load', 'run_time', 'max_openfile',
                  'inode_usage', 'iowait', 'bandwidth', 'throughput',
                  'salt_json', 'run_status']
        for t in target:
            if getattr(self, t):
                # 动态调用实例方法
                getattr(self, t)()


if __name__ == '__main__':
    # 创建 HostCrawl 实例
    # 避免使用硬编码的IP地址，可以通过环境变量或配置文件获取
    # h = HostCrawl(env='default', instance='10.0.14.224')
    import os
    instance_ip = os.getenv('HOSTCRAWL_INSTANCE_IP', '10.0.14.224')  # 默认使用10.0.14.224
    h = HostCrawl(env='default', instance=instance_ip)
    # 执行主机指标查询
    h.run()
    # 打印查询结果
    print(h.ret)
