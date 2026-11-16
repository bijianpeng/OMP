#!/usr/bin/env python3
# encoding: utf-8
# Author: Jayden Liu
# Description: common function for inspection
import os
import socket
import time

import psutil

from ext import logger
from lib.utils import format_desc, get_exporter_info

Desc_Public = {
    "service_process_survive": format_desc("service_process_survive", "judge service is alive"),
    "service_process_internet_port": format_desc("service_process_internet_port", "get all internet ports for service"),
    "service_process_runtime": format_desc("service_process_runtime", "get service process run time"),
    "service_process_cpu_percent": format_desc("service_process_cpu_percent", "get service cpu percent moment"),
    "service_process_memory_percent": format_desc("service_process_memory_percent", "get service percent moment"),
    "service_process_max_memory": format_desc("service_process_max_memory", "get java service max memory")
}


class PublicQuote(object):

    def __init__(self, pid_service_name, is_java=False, service_type=None, service_name=None, **kwargs):
        self.pid = 0
        self.service_live = False
        self.service_node_ip = self.GetLocal_Ip()
        self.pid_service_name = pid_service_name
        self.is_java = is_java
        self.service_type = service_type
        self.GetProcess_Pid()
        self.service_process_survive = ""
        self.service_process_port = ""
        self.service_process_runtime = ""
        self.service_process_cpu_percent = ""
        self.service_process_memory_percent = ""
        self.service_process_max_memory = ""
        self.service_info = get_exporter_info(service_name)

    def timer(self):
        _timer = getattr(time, 'monotonic', time.time)
        try:
            num_cpus = psutil.cpu_count() or 1
        except Exception as e:
            num_cpus = 1
        return _timer() * num_cpus

    def GetLocal_Ip(self):
        """
        获取服务所在的ip地址
        :return:
        """
        try:
            csock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            csock.connect(('8.8.8.8', 80))
            (addr, port) = csock.getsockname()
            csock.close()
            return addr
        except socket.error:
            return "127.0.0.1"

    def get_service_process_survive(self):
        """
        根据获取的进程号判断服务是否存活
        :return:
        """
        desc = Desc_Public["service_process_survive"]
        if self.pid and type(self.pid).__name__ == 'int':
            pro_text = desc + "service_process_survive {}\n".format(1)
        else:
            pro_text = desc + "service_process_survive {}\n".format(0)
        self.service_process_survive = pro_text

    def get_service_process_internet_port(self):
        """
        获取服务占用几个端口号
        :return:
        """
        desc = Desc_Public["service_process_internet_port"]

        try:
            # port = []
            # p = psutil.Process(self.pid)
            cmd = 'ss -tnlp | grep ' + str(self.pid)
            port_list = os.popen(cmd).read().strip('\n').split('\n')
            for line_list in port_list:
                line = line_list.split()
                port_aa = line[3].split(':')
                # port.append(port_aa[-1])
                desc += "service_process_internet_port {}\n".format(
                    port_aa[-1])
            self.service_process_port = desc
        except Exception as e:
            logger.error("获取服务{}的网络端口号失败error={}".format(
                self.pid_service_name, e))

    def get_service_process_runtime(self):
        """
        获取服务的存活时间
        :return:
        """
        desc = Desc_Public["service_process_runtime"]
        if self.pid and type(self.pid).__name__ == 'int':
            try:
                cmd = 'ps -eo pid,etime|grep ' + str(self.pid)
                etime = os.popen(cmd).read().strip('\n').split()
                if '-' in etime[1]:
                    runtime = etime[1].replace('-', ' day ')
                else:
                    runtime = etime[1]
                self.service_process_runtime = desc + \
                    "service_process_runtime {}\n".format(runtime)
            except Exception as e:
                logger.error("获取服务{}的运行时间失败 error={}".format(
                    self.pid_service_name, e))
        else:
            logger.error("获取服务{}的运行时间失败,服务进程号类型异常".format(
                self.pid_service_name))

    def get_service_process_cpu_percent(self):
        """
        获取服务的cpu占用量
        :return:
        """
        try:
            pid_cpuinfo = {}
            p = psutil.Process(self.pid)
            pt = p.cpu_times()
            st1, pt1_0, pt1_1 = self.timer(), pt.user, pt.system  # new
            st0, pt0_0, pt0_1 = pid_cpuinfo.get(self.pid, (0, 0, 0))  # old
            delta_proc = (pt1_0 - pt0_0) + (pt1_1 - pt0_1)
            delta_time = st1 - st0
            cpus_percent = ((delta_proc / delta_time) * 100)
            pid_cpuinfo[self.pid] = [st1, pt1_0, pt1_1]
            cpu_usage = "{:.2f}".format(cpus_percent)
            self.service_process_cpu_percent = Desc_Public[
                "service_process_cpu_percent"] + "service_process_cpu_count {}\n".format(
                cpu_usage)
        except Exception as e:
            logger.error("获取服务{}的cpu使用率错误 error={}".format(
                self.pid_service_name, e))

    def get_service_process_memory_percent(self):
        """
        获取服务的内存占用量
        :return:
        """

        try:
            p = psutil.Process(self.pid)
            process_mem = p.memory_percent()
            mem_usage = "{:.2f}".format(process_mem)
            self.service_process_memory_percent = Desc_Public[
                "service_process_memory_percent"] + "service_process_memory_percent {}".format(
                mem_usage)
        except Exception as e:
            logger.error("获取服务{}的内存使用率失败 error={}".format(
                self.pid_service_name, e))

    def get_service_process_max_memory(self):
        """
        获取服务最大内存使用量，只有java服务才有
        :param is_java:
        :return:
        """
        if self.is_java:
            try:
                cmd = 'ps -eo pid,command|grep %s' % self.pid
                process_list = os.popen(cmd).read().strip('\n').split('-Xms')
                process_mem = process_list[-1].split()
                max_mem = process_mem[0]
                self.service_process_max_memory = Desc_Public[
                    "service_process_max_memory"] + "service_process_max_memory {}\n".format(
                    max_mem)
            except Exception as e:
                logger.error("获取服务{}的最大使用内存错误 error={}".format(
                    self.pid_service_name, e))
        else:
            logger.info("服务{}非java服务，不存在内存限制".format(self.pid_service_name))

    def GetProcess_Pid(self):
        """
        获取服务的进程号，区分java服务
        :return:
        """

        try:
            for pnum in psutil.pids():
                p = psutil.Process(pnum)
                if self.is_java:
                    if p.name() == 'java' and p.name() == self.pid_service_name:
                        self.pid = pnum
                        break
                else:
                    if p.name() == self.pid_service_name:
                        self.pid = pnum
                        break
                self.service_live = True
        except Exception as e:
            logger.error("获取服务{}的进程号错误,服务不存在 {}".format(
                self.pid_service_name, e))
            self.service_live = False
