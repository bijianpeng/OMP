# -*- coding: utf-8 -*-
# Project: test_monitor_agent
# Author: omp
# Create time: 2021-10-07 15:47
# IDE: PyCharm
# Version: 1.0
# Introduction:

"""
测试monitor agent脚本
"""

import os
from unittest import mock
import pytest
import unittest

from tests.base import BaseTest
from db_models.models import Env
from db_models.models import Host
from omp_server.settings import PROJECT_DIR
from utils.plugin.salt_client import SaltClient
from promemonitor.prometheus_utils import PrometheusUtils
from utils.plugin.monitor_agent import MonitorAgentManager


class MonitorAgentTest(BaseTest):
    """ 主机Agent的测试类 """

    def setUp(self):
        super(MonitorAgentTest, self).setUp()
        # 默认环境由 BaseTest 保证存在（name/code 均为 "default"）
        env_obj = Env.objects.get(id=1)
        self.correct_host_data = {
            "instance_name": "mysql_instance_1",
            "ip": "127.0.0.10",
            "port": 36000,
            "username": "root",
            "password": "root_password",
            "data_folder": "/data",
            "operate_system": "CentOS",
            "disk": {"/": 90, "/data": 99},
            "env": env_obj
        }
        Host(**self.correct_host_data).save()
        self.host_obj_lst = list(Host.objects.all())
        self.agent_path = os.path.join(
            PROJECT_DIR, "package_hub/omp_monitor_agent.tar.gz")
        if not os.path.exists(self.agent_path):
            with open(self.agent_path, "w") as fp:
                fp.write("test")
        self.monitor_agent_name = "omp_monitor_agent.tar.gz"

    def _install(self):
        manager = MonitorAgentManager(host_objs=self.host_obj_lst)
        manager.monitor_agent_package_name = self.monitor_agent_name
        return manager.install()

    def test_parse_hosts_data_uses_env_code(self):
        """
        下发到监控链路（add_node）的 env 必须是 Env.code（spec §6.4），
        中文名环境不得进入 targets 文件名 / PromQL label
        """
        env_cn = Env.objects.create(name="生产环境", code="prod")
        Host.objects.create(
            instance_name="host-prod", ip="127.0.0.11",
            username="root", password="pwd", operate_system="CentOS",
            data_folder="/data", disk={"/": 90, "/data": 99}, env=env_cn)
        manager = MonitorAgentManager(
            host_objs=list(Host.objects.filter(ip="127.0.0.11")))
        hosts_data = manager.parse_hosts_data()
        self.assertEqual(len(hosts_data), 1)
        self.assertEqual(hosts_data[0]["env"], "prod")

    @mock.patch.object(SaltClient, "cp_file", return_value=(True, "success"))
    @mock.patch.object(SaltClient, "cmd", return_value=(True, "success"))
    @mock.patch.object(SaltClient, "__init__", return_value=None)
    def test_package_do_not_exist(self, *args, **kwargs):
        """
        测试monitor agent安装包不存在场景
        :param args:
        :param kwargs:
        :return:
        """
        manager = MonitorAgentManager(host_objs=self.host_obj_lst)
        manager.monitor_agent_package_name = ""
        flag, msg = manager.install()
        self.assertEqual(flag, False)

    @mock.patch.object(SaltClient, "cp_file", return_value=(False, "success"))
    @mock.patch.object(SaltClient, "cmd", return_value=(True, "success"))
    @mock.patch.object(SaltClient, "__init__", return_value=None)
    def test_install_failed_send_package(self, *args, **kwargs):
        """
        测试成功安装monitor agent场景
        :param args:
        :param kwargs:
        :return:
        """
        flag, msg = self._install()
        self.assertEqual(flag, False)

    @mock.patch.object(SaltClient, "cp_file", return_value=(True, "success"))
    @mock.patch.object(SaltClient, "cmd", return_value=(False, "success"))
    @mock.patch.object(SaltClient, "__init__", return_value=None)
    def test_install_failed_cmd(self, *args, **kwargs):
        """
        测试成功安装monitor agent场景
        :param args:
        :param kwargs:
        :return:
        """
        self.assertEqual(self._install()[0], False)

    @mock.patch.object(SaltClient, "cp_file", return_value=(True, "success"))
    @mock.patch.object(SaltClient, "cmd", return_value=(True, "success"))
    @mock.patch.object(SaltClient, "__init__", return_value=None)
    @mock.patch.object(
        PrometheusUtils, "add_node", return_value=(True, "success"))
    def test_install_success(self, *args, **kwargs):
        """
        测试成功安装monitor agent场景
        :param args:
        :param kwargs:
        :return:
        """
        flag, msg = self._install()
        self.assertEqual(flag, True)

    @mock.patch.object(SaltClient, "cmd", return_value=(False, "success"))
    @mock.patch.object(SaltClient, "__init__", return_value=None)
    def test_uninstall_failed(self, *args, **kwargs):
        """
        测试卸载失败场景
        :param args:
        :param kwargs:
        :return:
        """
        manager = MonitorAgentManager(host_objs=self.host_obj_lst)
        manager.monitor_agent_package_name = self.monitor_agent_name
        self.assertEqual(manager.uninstall()[0], False)

    @mock.patch.object(SaltClient, "cmd", return_value=(True, "success"))
    @mock.patch.object(SaltClient, "__init__", return_value=None)
    def test_uninstall_success(self, *args, **kwargs):
        """
        测试卸载失败场景
        :param args:
        :param kwargs:
        :return:
        """
        manager = MonitorAgentManager(host_objs=self.host_obj_lst)
        manager.monitor_agent_package_name = self.monitor_agent_name
        self.assertEqual(manager.uninstall()[0], True)

class TestMonitorAgent(BaseTest):
    """测试monitor_agent模块的补充函数"""
    
    def test_execute_success(self):
        class DummyHost:
            def __init__(self, ip): self.ip = ip
        def func(host): return (True, "ok")
        hosts = [DummyHost("127.0.0.1"), DummyHost("127.0.0.2")]
        flag, msg = MonitorAgentManager.execute(hosts, "test", func)
        assert flag is True
        assert msg == "success!"

    def test_execute_fail(self):
        class DummyHost:
            def __init__(self, ip): self.ip = ip
        def func(host): return (False, "fail")
        hosts = [DummyHost("127.0.0.1")]
        flag, msg = MonitorAgentManager.execute(hosts, "test", func)
        assert flag is False
        assert "127.0.0.1" in msg

# ================== alert_util.py 补全测试 ==================
import pytest
from promemonitor import alert_util

@pytest.mark.django_db
class TestAlertUtil(unittest.TestCase):
    def test_get_service_type(self):
        name, typ = alert_util.get_service_type('1.1.1.1', 'mysql')
        assert name == 'mysql'
        assert typ == '1.1.1.1'

    def test_get_monitor_url_normal(self, mocker):
        mocker.patch('promemonitor.alert_util.explain_url', return_value=([{'monitor_url': 'url'}],))
        assert alert_util.get_monitor_url([1]) == 'url'

    def test_get_monitor_url_typeerror(self, mocker, caplog):
        mocker.patch('promemonitor.alert_util.explain_url', side_effect=TypeError)
        with caplog.at_level('ERROR'):
            assert alert_util.get_monitor_url([1]) is None
            assert 'get monitor url failed' in caplog.text

    def test_get_log_url_normal(self, mocker):
        mocker.patch('promemonitor.alert_util.explain_url', return_value=([{'log_url': 'log'}],))
        assert alert_util.get_log_url([1]) == 'log'

    def test_get_log_url_typeerror(self, mocker, caplog):
        mocker.patch('promemonitor.alert_util.explain_url', side_effect=TypeError)
        with caplog.at_level('ERROR'):
            assert alert_util.get_log_url([1]) is None
            assert 'get monitor log url failed' in caplog.text

    def test_utc_to_local_normal(self, mocker):
        mocker.patch('promemonitor.alert_util.pytz.timezone', return_value=alert_util.pytz.utc)
        utc = '2023-01-01T00:00:00Z'
        res = alert_util.utc_to_local(utc)
        assert isinstance(res, str)

    def test_utc_to_local_exception(self, mocker, caplog):
        with caplog.at_level('ERROR'):
            res = alert_util.utc_to_local('bad-format')
            assert isinstance(res, str)
            assert '在转化时间格式时报错' in caplog.text

    def test_alert_analysis_basic(self):
        item = {'labels': {'job': 'nodeExporter'}, 'annotations': {}, 'status': 'firing'}
        aa = alert_util.AlertAnalysis(item)
        res = aa.analysis_labels()
        assert 'alert_type' in res
        assert 'status' in res
        assert 'alert_level' in res
        assert 'alertname' in res
        assert 'fingerprint' in res
        assert 'alert_time' in res

    def test_alert_analysis_exporter(self, mocker):
        item = {'labels': {'job': 'mysqlExporter', 'app': 'mysql'}, 'annotations': {}, 'status': 'firing'}
        mocker.patch('promemonitor.alert_util.Service.objects.filter', return_value=[])
        aa = alert_util.AlertAnalysis(item)
        res = aa.analysis_labels()
        assert res['alert_type'] in ['service', 'component']

    def test_alert_analysis_other(self, mocker):
        item = {'labels': {'job': 'other'}, 'annotations': {}, 'status': 'firing'}
        mocker.patch('promemonitor.alert_util.Service.objects.filter', return_value=[])
        aa = alert_util.AlertAnalysis(item)
        res = aa.analysis_labels()
        assert res['alert_type'] in ['service', 'component']

class TestMonitorAgentManagerExtra(BaseTest):
    def test_execute_exception(self):
        from utils.plugin.monitor_agent import MonitorAgentManager
        class DummyHost:
            def __init__(self, ip): self.ip = ip
        def func(host): return (False, 'fail')
        hosts = [DummyHost('127.0.0.1')]
        flag, msg = MonitorAgentManager.execute(hosts, 'test', func)
        assert flag is False
        assert '127.0.0.1' in msg

class TestMyThread(BaseTest):
    def test_thread_result(self):
        from utils.prometheus.thread import MyThread
        def add(x, y): return x + y
        t = MyThread(add, (1, 2))
        t.start()
        t.join()
        assert t.result() == 3
