# -*- coding: utf-8 -*-
"""
DataJson 多环境隔离测试

背景（多环境跨环境污染修复）：
- DataJson.run 生成 data.json 时原用 Service.objects.all()（老链路）/
  Service.split_objects.all()（新链路），包含全环境所有服务/主机；
- create_user_and_send_json 再按 json 的 ip_user_map 对每台主机建/补建
  PreInstallHistory 并 cp json + useradd → dev 环境安装的执行详情混入
  default 环境主机（56.108），pre 执行把 json cp 到其它环境主机。

修复：DataJson 增加环境过滤（env_id），两条链路 CreateInstallPlan.run
构造 DataJson 时传入本次安装所属环境；env_id=None 保持存量全量行为
（兼容历史调用方）。
"""
import os
import sys
import uuid as uuid_module
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from django.test import TestCase

from app_store import install_utils
from app_store.new_install_utils import (
    CreateInstallPlan as NewCreateInstallPlan)
from app_store.new_install_utils import DataJson as NewDataJson
from app_store.install_utils import DataJson as OldDataJson
from db_models.models import (
    ApplicationHub, DetailInstallHistory, Env, Host,
    MainInstallHistory, Service, UploadPackageHistory)

IP_A = "10.10.20.1"     # 环境A（default）主机
IP_B = "10.10.20.2"     # 环境B（dev）主机


class DataJsonEnvBase(TestCase):
    """构造两环境 / 两主机 / 两服务最小对象图"""

    def setUp(self):
        # code 唯一：default 环境由迁移创建（code="default"），复用之
        self.env_a, _ = Env.objects.get_or_create(
            code="default", defaults={"name": "default"})
        self.env_b = Env.objects.create(name="dev", code="dj-env-dev")
        for env, ip in ((self.env_a, IP_A), (self.env_b, IP_B)):
            Host.objects.create(
                instance_name=f"host-{ip}", ip=ip, port=22,
                username="root", password="fake_password",
                data_folder="/data", operate_system="CentOS",
                host_name=f"hostname-{ip}", agent_dir="/data", env=env)
        package = UploadPackageHistory.objects.create(
            operation_uuid=str(uuid_module.uuid4()),
            package_name="jdk-8u211.tar.gz",
            package_md5="0" * 32,
            package_path="test/jdk-8u211.tar.gz",
        )
        self.app = ApplicationHub.objects.create(
            app_name="jdk", app_version="8u211",
            app_type=ApplicationHub.APP_TYPE_COMPONENT,
            app_package=package,
        )
        self.main = MainInstallHistory.objects.create(
            operator="test", operation_uuid=str(uuid_module.uuid4()))
        self.ser_a = self._make_service(IP_A, "jdk-20-1", self.env_a)
        self.ser_b = self._make_service(IP_B, "jdk-20-2", self.env_b)

    @staticmethod
    def _make_service(ip, instance_name, env):
        service = Service.objects.create(
            ip=ip, service_instance_name=instance_name,
            service=ApplicationHub.objects.get(app_name="jdk"),
            service_status=Service.SERVICE_STATUS_NORMAL,
            service_port="[]", env=env)
        DetailInstallHistory.objects.create(
            service=service, main_install_history=MainInstallHistory.objects.first(),
            install_detail_args={
                "ip": ip, "name": "jdk",
                "install_args": [{"key": "base_dir", "default": "/jdk"}],
            })
        return service

    @staticmethod
    def _run_capture(data_json_cls, **kwargs):
        """构造 DataJson 并 run，捕获 make_data_json 收到的 json_lst"""
        dj = data_json_cls(
            operation_uuid=str(uuid_module.uuid4()), **kwargs)
        with mock.patch.object(dj, "make_data_json") as mm:
            dj.run()
        return mm.call_args[1]["json_lst"]


class OldDataJsonEnvTestCase(DataJsonEnvBase):
    """ 老链路 install_utils.DataJson 按环境过滤 """

    def test_env_filtered_json_contains_only_this_env(self):
        """ env=B → json 仅含 B 环境服务/主机 ip，A 环境被排除 """
        json_lst = self._run_capture(OldDataJson, env_id=self.env_b.id)
        ips = {el["ip"] for el in json_lst}
        self.assertEqual(ips, {IP_B})
        self.assertNotIn(IP_A, ips)

    def test_env_none_keeps_all(self):
        """ env_id 不传 → 保持存量全量行为（兼容历史调用方） """
        json_lst = self._run_capture(OldDataJson)
        ips = {el["ip"] for el in json_lst}
        self.assertEqual(ips, {IP_A, IP_B})


class NewDataJsonEnvTestCase(DataJsonEnvBase):
    """ 新链路 new_install_utils.DataJson 按环境过滤 """

    def test_env_filtered_json_contains_only_this_env(self):
        """ env=B → json 仅含 B 环境服务/主机 ip """
        json_lst = self._run_capture(NewDataJson, env_id=self.env_b.id)
        ips = {el["ip"] for el in json_lst}
        self.assertEqual(ips, {IP_B})
        self.assertNotIn(IP_A, ips)

    def test_env_none_keeps_all(self):
        """ env_id 不传 → 保持存量全量行为 """
        json_lst = self._run_capture(NewDataJson)
        ips = {el["ip"] for el in json_lst}
        self.assertEqual(ips, {IP_A, IP_B})

    def test_service_obj_takes_priority_over_env(self):
        """ 显式传入 service_obj 时优先（部署计划导入链路语义不变） """
        json_lst = self._run_capture(
            NewDataJson, service_obj=[self.ser_a], env_id=self.env_b.id)
        ips = {el["ip"] for el in json_lst}
        self.assertEqual(ips, {IP_A})


FRONTEND_ITEM_TMPL = {
    "install_type": 0,
    "install_services": [
        {
            "name": "jdk",
            "version": "8u211",
            "ip": IP_B,
            "cluster_name": "test_cluster_1",
            "app_install_args": [
                {"name": "安装目录", "key": "base_dir",
                 "default": "/jdk", "dir_key": "{data_path}"},
            ],
            "app_port": [
                {"name": "服务端口", "protocol": "TCP",
                 "key": "service_port", "default": 19001},
            ],
            "service_instance_name": "jdk-20-2",
        },
    ],
}

STANDARD_ITEM_TMPL = [{
    "name": "jdk", "version": "8u211", "ip": IP_B,
    "install_args": [{"key": "base_dir", "default": "/jdk"}],
    "ports": [{"key": "service_port", "default": 19001}],
    "instance_name": "jdk-20-2", "cluster_name": None,
    "data_folder": "/data", "run_user": "omp",
}]


class CreatePlanDataJsonEnvTestCase(DataJsonEnvBase):
    """ 两条链路 CreateInstallPlan.run 构造 DataJson 时传入环境 """

    def _run_old_plan(self, env):
        plan = install_utils.CreateInstallPlan(
            install_data=FRONTEND_ITEM_TMPL, env=env)
        with mock.patch.object(install_utils.CreateInstallPlan,
                              "create_service",
                              return_value=self.ser_b), \
                mock.patch.object(install_utils.CreateInstallPlan,
                                  "create_product_instance"), \
                mock.patch.object(install_utils.CreateInstallPlan,
                                  "check_if_has_post_action",
                                  return_value=False), \
                mock.patch.object(install_utils, "install_service") as mt, \
                mock.patch("app_store.install_utils.DataJson") as mdj:
            mt.delay.return_value = "fake-task-id"
            flag, msg = plan.run()
        self.assertTrue(flag, str(msg))
        return mdj.call_args[1].get("env_id")

    def _run_new_plan(self, env):
        plan = NewCreateInstallPlan(
            all_install_service_lst=STANDARD_ITEM_TMPL,
            unique_key="uk-env-test", env=env)
        with mock.patch.object(NewCreateInstallPlan, "create_service",
                              return_value=self.ser_b), \
                mock.patch.object(NewCreateInstallPlan,
                                  "create_product_instance"), \
                mock.patch.object(NewCreateInstallPlan,
                                  "check_if_has_post_action",
                                  return_value=False), \
                mock.patch.object(NewCreateInstallPlan,
                                  "create_pre_install_history"), \
                mock.patch.object(NewCreateInstallPlan,
                                  "create_post_install_history"), \
                mock.patch("app_store.new_install_utils.BaseRedisData"), \
                mock.patch(
                    "app_store.new_install_utils.install_service_task") as mt, \
                mock.patch("app_store.new_install_utils.DataJson") as mdj:
            mt.delay.return_value = "fake-task-id"
            flag, msg = plan.run()
        self.assertTrue(flag, str(msg))
        return mdj.call_args[1].get("env_id")

    def test_old_chain_passes_request_env(self):
        """ 老链路：显式 env → DataJson(env_id=env.id) """
        self.assertEqual(
            self._run_old_plan(self.env_b), self.env_b.id)

    def test_old_chain_derives_env_from_install_ips(self):
        """ 老链路：env 缺失 → 按本次安装 ip 反查主机环境（spec #10） """
        self.assertEqual(self._run_old_plan(None), self.env_b.id)

    def test_new_chain_passes_request_env(self):
        """ 新链路：显式 env → DataJson(env_id=env.id) """
        self.assertEqual(
            self._run_new_plan(self.env_b), self.env_b.id)

    def test_new_chain_derives_env_from_install_ips(self):
        """ 新链路：env 缺失 → 按本次安装 ip 反查主机环境（重装链路） """
        self.assertEqual(self._run_new_plan(None), self.env_b.id)

    def test_old_chain_cross_env_ips_fallback_none(self):
        """ 老链路：安装 ip 跨环境/反查不到唯一环境 → env_id=None 兜底 """
        data = {
            "install_type": 0,
            "install_services": [
                dict(FRONTEND_ITEM_TMPL["install_services"][0]),
                dict(FRONTEND_ITEM_TMPL["install_services"][0], ip=IP_A),
            ],
        }
        plan = install_utils.CreateInstallPlan(install_data=data)
        self.assertIsNone(plan.get_env_id_for_data_json())

    def test_new_chain_cross_env_ips_fallback_none(self):
        """ 新链路：安装 ip 跨环境 → env_id=None 兜底 """
        items = [dict(STANDARD_ITEM_TMPL[0]),
                 dict(STANDARD_ITEM_TMPL[0], ip=IP_A)]
        plan = NewCreateInstallPlan(
            all_install_service_lst=items, unique_key="uk-env-test2")
        self.assertIsNone(plan.get_env_id_for_data_json())
