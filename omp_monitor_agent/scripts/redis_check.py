#!/usr/bin/env python3
# encoding: utf-8
# Auther: Darren Liu
# Description: get redis Inspection data

import os.path as up
import traceback

import psutil
import redis

from ext import logger
from lib.utils import format_desc
from lib.webapp import app
from .inspection_common import PublicQuote

desc_redis = {
    "redis_read_only": format_desc("redis_read_only", "redis's node status slave or master"),
    "redis_slave_status": format_desc("redis_slave_status", "redis's slave status"),
    "redis_cluster_ip": format_desc("redis_cluster_ip", "redis cluster ips"),
    "redis_log_level": format_desc("redis_log_level", "service redis log level")
}


class Redis(PublicQuote):

    def __init__(self, service_name, **kwargs):
        super().__init__("redis-server", is_java=False,
                         service_type="open-source", service_name=service_name)

        self.host = app.config["AGENT_HOST"]
        self.service_port = self.service_info.get("service_port")
        self.password = self.service_info.get("pwd")
        if self.password:
            self.rds = redis.StrictRedis(
                host=self.host, port=self.service_port, password=self.password)
        else:
            self.rds = redis.StrictRedis(
                host=self.host, port=self.service_port)
        try:
            self.info = self.rds.info()
        except redis.RedisError as e:
            traceback.print_exc()
            print(e)
            self.info = None
        self.redis_read_only = "False"
        self.redis_slave_status = ""
        self.redis_cluster_ip = ""
        self.redis_log_level = ""

    def parse_config(self, inp_type='inp_type'):
        """
        解析配置
        :param inp_type:
        :return:
        """
        try:
            return self.rds.config_get(inp_type)[inp_type]
        except redis.RedisError:
            return None

    def GetRedis_SlaveNum(self):
        """
        redis_connected_slaves exporter存在
        获取连接的子节点
        :return:
        """
        try:
            return self.info['connected_slaves']
        except IndexError:
            return None

    def GetRedis_NodeStatus(self):
        """
        获取当前节点服务状态
        :return:
        """
        try:
            return self.info['role']
        except IndexError:
            return None

    def get_redis_read_only(self):
        """
        redis只读状态
        :return:
        """
        if self.GetRedis_NodeStatus() == 'slave':
            try:
                read_only = self.info['slave_read_only']
                self.redis_read_only = desc_redis["redis_read_only"] + \
                    'redis_read_only{content="%s} 1\n' % read_only
            except Exception as e:
                logger.error("获取redis服务的子节点是否只读失败 error={}".format(e))
        else:
            pass

    def get_redis_slave_status(self):
        if self.GetRedis_NodeStatus() == 'master' and int(self.GetRedis_SlaveNum()) > 0:
            pro_text = 'up'
        elif self.GetRedis_NodeStatus() == 'master' and int(self.GetRedis_SlaveNum()) == 0:
            pro_text = 'no slave'
        elif self.GetRedis_NodeStatus() == 'slave':
            pro_text = self.info('master_link_status')
        else:
            pro_text = 'down'
        self.redis_slave_status = desc_redis["redis_slave_status"] + \
            'redis_slave_status{content="%s"} 1\n' % pro_text

    def get_redis_cluster_ip(self):
        """
        获取redis集群的ip信息
        :return:
        """
        pro_text = desc_redis["redis_cluster_ip"]
        cluster_ip = []
        try:
            if self.GetRedis_NodeStatus() == 'master' and int(self.GetRedis_SlaveNum()) > 0:
                start_num = 0
                slave_num = int(self.GetRedis_SlaveNum()) - 1
                for num in range(start_num, slave_num):
                    mark = 'slave' + str(num)
                    reids_line = self.info[mark].strip('\n').split('=')
                    redis_ip = reids_line.split(',')
                    cluster_ip.append(redis_ip[0])
            elif self.GetRedis_NodeStatus() == 'slave' and int(self.GetRedis_SlaveNum()) > 0:
                start_num = 0
                slave_num = int(self.GetRedis_SlaveNum()) - 1
                for num in range(start_num, slave_num):
                    mark = 'slave' + str(num)
                    redis_line = self.info[mark].strip('\n').split('=')
                    redis_ip = redis_line.split(',')
                    cluster_ip.append(redis_ip[0])
                cluster_ip.append(self.info['master_host'])
            elif self.GetRedis_NodeStatus() == 'slave' and int(self.GetRedis_SlaveNum()) == 0:
                cluster_ip.append(self.info['master_host'])
                cluster_ip.append(self.service_node_ip)
            else:
                pass
            self.redis_cluster_ip = pro_text + \
                'redis_cluster_ip{content="%s"}' % ",".join(cluster_ip)
        except Exception as e:
            logger.error("获取redis的集群信息错误 error={}".format(e))

    def get_redis_log_level(self):
        log_level = None
        try:
            p = psutil.Process(self.pid)
            redis_path = up.abspath(up.join(p.exe(), "../.."))
            f = open('%s/redis.conf' % redis_path, 'r')
            for lines_list in f:
                if 'loglevel ' in lines_list:
                    redis_log_level = lines_list.strip('\n').split()
                    log_level = redis_log_level[-1]
            self.redis_log_level = 'redis_log_level{content="%s"}' % log_level
            return log_level
        except Exception as e:
            logger.error("获取redis服务的日志信息错误 error={}".format(e))
