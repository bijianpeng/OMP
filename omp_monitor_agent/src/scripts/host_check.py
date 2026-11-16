#!/usr/bin/env python3
# encoding: utf-8
# Author: Jayden Liu
# Description: get host Inspection data

import os
import re
import socket
import time
import subprocess
import psutil
import sys

sys.path.append("../../monitor_agent")
from ext import logger


def format_desc(quote, pro_help, pro_type="gauge"):
    return "# HELP {} {}.\n# TYPE {} {}\n".format(quote, pro_help, quote, pro_type)


def run_cmd(cmd):
    """
    运行系统命令，返回标准输出，标准错误输出及执行状态码
    :param cmd:
    :return:
    """
    p = subprocess.run(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    cmd_stdout = bytes.decode(p.stdout)
    if cmd_stdout.endswith('\n'):
        cmd_stdout = cmd_stdout.strip()
    # cmd_stderr = bytes.decode(p.stderr)

    if p.returncode == '0':
        return None
    else:
        # return cmd_stdout, cmd_stderr, p.returncode
        return cmd_stdout


desc_map = {
    "node_ip": format_desc("node_ip", "node's ip"),
    "node_selinux": format_desc("node_selinux", "node's selinux status"),
    "node_umask": format_desc("node_umask", "the user file-creation mask"),
    "node_runtime": format_desc("node_runtime", "node's runtime"),
    "node_inode": format_desc("node_inode", "node inode usage"),
    "node_services_port_connection": format_desc("node_services_port_connection", "test services port alive",
                                                 "counter"),
    "node_bandwidth_sent": format_desc("node_bandwidth_sent", "node's bandwidth set bytes"),
    "node_bandwidth_receive": format_desc("node_bandwidth_receive", "node's bandwidth receive bytes"),
    "node_disk_read": format_desc("node_disk_read", "node's disk read bytes 1s"),
    "node_disk_write": format_desc("node_dis_write", "node's disk write bytes 1s"),
    "node_memory_top_10": format_desc("node_memory_top_10", "node's app usage top 10 of memory", "counter"),
    "node_cpu_top_10": format_desc("node_cpu_top_10", "node's app usage top 10 of cpu", "counter"),
    "node_kernel_parameters": format_desc("node_kernel_info", "node's kernel parameters"),
    "node_boot_start": format_desc("node_boot_start", "node's boot start", "counter"),
    "node_zombies_status": format_desc("node_zombies_status", "node's zombies process", "counter"),
    "node_run_process_num": format_desc("node_run_process_num", "node's run process num"),
    "node_firewall_info": format_desc("node_fire_wall_info", "node's fire wall info", "counter")

}


# 所有的指标返回都要变成prometheus的文本格式
class Host(object):
    """
    所有的指标返回都要变成prometheus的文本格式返回
    """

    def __init__(self, *kwargs):
        self.service_name = "host"
        self.node_ip = "127.0.0.1"
        self.node_selinux = ""
        self.node_umask = ""
        self.node_runtime = ""
        self.node_inode = ""
        self.node_services_port_connection = ""
        self.node_bandwidth_sent = ""
        self.node_bandwidth_receive = ""
        self.node_disk_read = ""
        self.node_disk_write = ""
        self.node_memory_top_10 = ""
        self.node_cpu_top_10 = ""
        self.node_kernel_parameters = ""
        self.node_boot_start = ""
        self.node_zombies_status = ""
        self.node_run_process_num = ""
        self.node_firewall_info = ""
        self.service_live = True

    def get_node_ip(self):
        try:
            csock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            csock.connect(('8.8.8.8', 80))
            (addr, port) = csock.getsockname()
            csock.close()
        except socket.error as e:
            logger.error("get_node_ip error={}".format(e))
            addr = "127.0.0.1"
        pro_text = desc_map.get("node_ip") + 'node_ip{ip="%s"} 1\n' % addr
        self.node_ip = pro_text

    def get_node_selinux(self):
        """
        获取selinux状态
        :return:
        """
        try:
            cmd = 'getenforce'
            selinux_status = run_cmd(cmd)
            pro_text = desc_map.get(
                "node_selinux") + 'node_selinux{selinux="%s"} 1\n' % selinux_status
            self.node_selinux = pro_text
        except Exception as e:
            logger.error("get_node_selinux error={}".format(e))
            return ""

    def get_node_umask(self):
        """
        获取文件预创建的权限编码
        :return:
        """
        try:
            user_cmd = 'whoami'
            user = run_cmd(user_cmd)
            cmd = 'umask'
            umask_status = run_cmd(cmd)
            pro_text = desc_map["node_umask"] + \
                'node_umask{user="%s","umask"="%s"}\n' % (user, umask_status)
            self.node_umask = pro_text
        except Exception as e:
            logger.error("get_node_umask error={}".format(e))

    def get_node_runtime(self):
        """
        获取系统运行时间
        :return:
        """
        try:
            cmd = "uptime"
            uptime_list = run_cmd(cmd).strip().split('up')
            run_time = uptime_list[1].strip().split(',')
            if 'user' in run_time[1]:
                time_run = run_time[0]
            else:
                time_run = run_time[0] + run_time[1]
            pro_text = desc_map["node_runtime"] + \
                'node_runtime{content="%s"} 1\n' % time_run
            print(pro_text)
            self.node_runtime = pro_text
        except Exception as e:
            logger.error("get_node_runtime error={}".format(e))

    def get_node_inode(self, data_path='/data'):
        """
        获取inode使用量信息
        :return:
        """
        try:
            # inode_usage_json = {}
            '''
            /dev/mapper/centos-root 2883584  111117 2772467       4% /
            /dev/sda1                524288     327  523961       1% /boot

            '''
            inode_cmd = "df -i | grep -v 'tmpfs' | tail -n +2"
            result = run_cmd(inode_cmd).strip().split('\n')
            path = ""
            percent = ""
            for total_list in result:
                total = total_list.split()
                if total[-1] == '/':
                    path = "/"
                    percent = total[-2]
                if total[-1] == data_path:
                    path = data_path
                    percent = total[-2]

            pro_text = desc_map["node_inode"] + \
                'node_inode{path="%s",percent="%s"} 1\n' % (path, percent)
            self.node_inode = pro_text
        except Exception as e:
            logger.error("get_node_inode error={}".format(e))

    def get_node_services_port_connection(self, port_list=None):
        """
        测试服务端口是否存活
        :param port_list:
        :return:
        """
        pro_text = desc_map["node_services_port_connection"]
        if port_list is None:
            port_list = [{"name": "ssh", "ip": "127.0.0.1", "port": "36000"}]
        try:
            for port in port_list:
                sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sk.settimeout(2)
                status = sk.connect_ex((port['ip'], int(port['port'])))
                if status != 0:
                    status_str = "False"
                else:
                    status_str = "True"
                pro_text += 'node_services_port_connection{name="%s",ip="%s",port="%s",status="%s"} 1\n' % (
                    port["name"], port["ip"], port["port"], status_str)
                sk.close()
            self.node_services_port_connection = pro_text
        except socket.error as e:
            logger.error("get_node_inode error={}".format(e))

    def get_node_bandwidth_sent(self):
        try:
            bandwidth_1 = psutil.net_io_counters()
            time.sleep(1)
            bandwidth_2 = psutil.net_io_counters()
            bandwidth_sent = bandwidth_2.bytes_sent - bandwidth_1.bytes_sent
            pro_text = desc_map["node_bandwidth_sent"] + \
                "node_bandwidth_sent %s\n" % bandwidth_sent
            self.node_bandwidth_sent = pro_text
        except Exception as e:
            logger.error("get_node_bandwidth_sent error={}".format(e))

    def get_node_bandwidth_receive(self):
        try:
            bandwidth_1 = psutil.net_io_counters()
            time.sleep(1)
            bandwidth_2 = psutil.net_io_counters()
            bandwidth_receive = bandwidth_2.bytes_recv - bandwidth_1.bytes_recv
            pro_text = desc_map["node_bandwidth_receive"] + \
                "node_bandwidth_receive %s\n" % bandwidth_receive
            self.node_bandwidth_receive = pro_text
        except Exception as e:
            logger.error("get_node_bandwidth_receive error={}".format(e))

    def get_node_disk_read(self):
        """
        获取主机的硬盘读取速度
        :return:
        """
        try:
            disk_1 = psutil.disk_io_counters()
            time.sleep(1)
            disk_2 = psutil.disk_io_counters()
            disk_read = disk_2.read_bytes - disk_1.read_bytes
            pro_text = desc_map["node_disk_read"] + \
                "node_disk_read %s\n" % disk_read
            self.node_disk_read = pro_text
        except Exception as e:
            logger.error("get_node_disk_read error={}".format(e))

    def get_node_disk_write(self):
        """
        获取主机的硬盘读取速度
        :return:
        """
        try:
            disk_1 = psutil.disk_io_counters()
            time.sleep(1)
            disk_2 = psutil.disk_io_counters()
            disk_write = disk_2.write_bytes - disk_1.write_bytes
            pro_text = desc_map["node_disk_write"] + \
                "node_disk_write {}\n".format(disk_write)
            self.node_disk_read = pro_text
        except Exception as e:
            logger.error("get_node_disk_write error={}".format(e))

    def get_node_memory_top_10(self):
        """
              获取占用内存前10的应用
              :return:
              """

        class Cwp:
            def __init__(self, pid, memory_percent, cmdline):
                self.pid = pid
                self.cmdline = cmdline
                self.memory_percent = memory_percent

        all_pids = psutil.pids()
        cw_ps = []
        for ele in all_pids:
            try:
                p = psutil.Process(ele)
                cw_p = Cwp(p.pid, p.memory_percent(), ' '.join(p.cmdline()))
                cw_ps.append(cw_p)
            except psutil.Error:
                continue
        cw_ps.sort(key=lambda c: c.memory_percent, reverse=True)
        pro_text = desc_map["node_memory_top_10"]
        """
        {"TOP1": {"PID": 9524, "P_RATE": "3.33%", "P_CMD": "clickhouse-server start"}
        """
        i = 0
        for ele in cw_ps[:10]:
            i += 1
            pro_text += 'node_memory_top_10{top="%s",percent="%s",command="%s"} %s\n' % (
                i, round(ele.memory_percent, 2), ele.cmdline, ele.pid)
        self.node_memory_top_10 = pro_text

    def get_node_cpu_top_10(self):
        """
               获取cpu使用率前10的应用
               :return:
               """

        class Cwp:
            def __init__(self, pid, cpu_percent, cmdline):
                self.pid = pid
                self.cmdline = cmdline
                self.cpu_percent = cpu_percent

        all_pids = psutil.pids()
        cw_ps = []
        for ele in all_pids:
            try:
                p = psutil.Process(ele)
                cw_p = Cwp(p.pid, p.cpu_percent(
                    interval=0.1), ' '.join(p.cmdline()))
                cw_ps.append(cw_p)
            except psutil.Error:
                continue
        cw_ps.sort(key=lambda c: c.cpu_percent, reverse=True)
        pro_text = desc_map["node_cpu_top_10"]
        i = 0
        for ele in cw_ps[:10]:
            i += 1
            pro_text += 'node_cpu_top_10{top="%s",percent="%s",command="%s"} %s\n' % (
                i, round(ele.cpu_percent, 2), ele.cmdline, ele.pid)
        self.node_cpu_top_10 = pro_text

    def get_node_kernel_parameters(self):
        """
        获取内核参数
        :return:
        """
        try:
            cmd = "egrep -v '^#|^$' /etc/sysctl.conf"
            sysctl = run_cmd(cmd).strip().split('\n')
            pro_text = desc_map["node_kernel_parameters"]
            if len(sysctl) > 0:
                label = " ".join(sysctl)
                self.node_kernel_parameters = pro_text + \
                    'node_kernel_parameters{label="%s"} 1\n' % label
        except Exception as e:
            logger.error("get_node_kernel_parameters error={}".format(e))

    def get_node_boot_start(self):
        """
        获取自启动服务
        :return:
        """
        try:
            cmd = None
            version = 0
            if os.path.exists("/etc/redhat-release"):
                with open("/etc/redhat-release") as f:
                    content = f.readlines()
                    line = content[0].split(" ")[3]
                    version = line.split(".")[0]
                    print(version)
            if version == "6":
                cmd = "chkconfig --list"
            elif version == "7":
                cmd = 'systemctl list-unit-files | grep enabled'
            else:
                logger.error("获取系统版本信息错误 error={}".format(version))
            if cmd:
                boot_start_list = run_cmd(cmd).strip().split('\n')
            else:
                boot_start_list = []
            pro_text = desc_map["node_boot_start"]
            for line_list in boot_start_list:
                line = line_list.split()
                pro_text += 'node_boot_start{command="%s"} 1\n' % line[0]
            self.node_boot_start = pro_text
        except Exception as e:
            logger.error("get_node_boot_start error = {}".format(e))

    def get_node_zombies_status(self):
        """
       获取系统的僵尸进程
       :return:
       """
        try:
            cmd = "ps -A -ostat,ppid,cmd |grep -e '^[Zz]'"
            zombies_status_list = run_cmd(cmd).strip().split('\n')
            pro_text = desc_map["node_zombies_status"]
            if len(zombies_status_list) > 0:
                for i in zombies_status_list:
                    pro_text += 'node_zombies_status{label="%s"} 1\n' % i
            self.node_zombies_status = pro_text
        except Exception as e:
            logger.error("get_node_zombies_status error = {}".format(e))

    def get_node_run_process_num(self):
        """
        获取主机正在运行的进程数
        :return:
        """
        try:
            all_process_num = len(psutil.pids())
        except Exception as e:
            all_process_num = 0
        self.node_run_process_num = desc_map["node_run_process_num"] + 'node_run_process_num {}\n'.format(
            all_process_num)

    def get_node_firewall_info(self):
        """
        获取防火墙的信息
        :return:
        """
        try:
            get_firewall_cmd = "iptables -nL"
            result = run_cmd(get_firewall_cmd)
            new_str = "".join(
                [s for s in result.splitlines(True) if s.strip()])
            if len(new_str.split('\n')) == 6:
                return None
            fw_block_list = result.split('\n\n')
            pro_text = desc_map["node_firewall_info"]
            for block in fw_block_list:
                block_rules_list = list()
                tmp_rules = block.split('\n')
                fw_title = tmp_rules[0]
                for line in tmp_rules:
                    rule_dict = dict()
                    if line.startswith('Chain') or line.startswith('target'):
                        continue
                    items = re.split(r'\s+', line)
                    rule_dict.update({'target': items[0]})
                    rule_dict.update({'port': items[1]})
                    rule_dict.update({'opt': items[2]})
                    rule_dict.update({'source': items[3]})
                    rule_dict.update({'destination': items[4]})
                    rule_dict.update({'others': ' '.join(items[5:])})
                    block_rules_list.append(rule_dict)
                if len(block_rules_list) > 0:
                    pro_text += 'node_firewall_info{name="%s",rule="%s"} 1\n' % (
                        fw_title, block_rules_list)

            self.node_firewall_info = pro_text
        except Exception as e:
            logger.error("get_node_firewall_info error = {}".format(e))
            return None


if __name__ == "__main__":
    host = Host()
    for func in host.__dir__():
        if func.startswith("get"):
            getattr(host, func)()
            content = func.split("get_")[1]
            print(getattr(host, content))
