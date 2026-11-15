# -*- coding: utf-8 -*-
"""
升级链路 DataJsonUpdate 多环境隔离测试

背景（data.json 跨环境污染的姊妹问题）：
- 升级前置 update_data_json 用 DataJsonUpdate 生成升级用 data.json，
  服务来源为 Service.split_objects.all()（全量、无环境过滤）；
- 多环境下混入其它环境的服务（install_args 携带其它环境主机的部署
  数据），send_data_json_all 再把该 json cp 到所有环境主机——与安装
  链路 DataJson 已修复的跨环境污染同款（见 test_data_json_env.py）。

修复：DataJsonUpdate 增加 env_id，按升级所属环境过滤服务来源与下发
主机；env_id=None 保持存量全量行为（兼容历史调用方）。
UpgradeHistory.env（升级历史所属环境）由调用链传入。
"""
import os
import sys
import uuid as uuid_module
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from django.test import TestCase

from db_models.models import (
    ApplicationHub, Env, Host, MainInstallHistory,
    Service, UpgradeHistory, UploadPackageHistory, UserProfile)
from service_upgrade import tasks
from service_upgrade.update_data_json import DataJsonUpdate

IP_A = "10.10.20.1"     # 环境A（default）主机
IP_B = "10.10.20.2"     # 环境B（dev）主机


class DataJsonUpdateEnvBase(TestCase):
    """构造两环境 / 两主机 / 两服务最小对象图"""

    def setUp(self):
        self.env_a, _ = Env.objects.get_or_create(
            code="default", defaults={"name": "default"})
        self.env_b = Env.objects.create(name="dev", code="up-dev")
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
        self.ser_a = Service.objects.create(
            ip=IP_A, service_instance_name="jdk-20-1", service=self.app,
            service_status=Service.SERVICE_STATUS_NORMAL,
            service_port="[]", env=self.env_a)
        self.ser_b = Service.objects.create(
            ip=IP_B, service_instance_name="jdk-20-2", service=self.app,
            service_status=Service.SERVICE_STATUS_NORMAL,
            service_port="[]", env=self.env_b)
        self.main = MainInstallHistory.objects.create(
            operator="test", operation_uuid=str(uuid_module.uuid4()))
        # 升级历史保存信号（execution_record）要求 operator 可取 username
        self.operator = UserProfile.objects.create(
            username="up-admin")


class DataJsonUpdateEnvTestCase(DataJsonUpdateEnvBase):
    """ DataJsonUpdate 按环境过滤服务来源与下发主机 """

    def test_load_json_lst_env_filtered(self):
        """ env=B → json 仅含 B 环境服务，A 环境被排除（RED 用例）"""
        dj = DataJsonUpdate(
            str(uuid_module.uuid4()), env_id=self.env_b.id)
        ips = {el["ip"] for el in dj.load_json_lst({})}
        self.assertEqual(ips, {IP_B})
        self.assertNotIn(IP_A, ips)

    def test_load_json_lst_env_none_keeps_all(self):
        """ env_id 不传 → 保持存量全量行为（兼容历史调用方）"""
        dj = DataJsonUpdate(str(uuid_module.uuid4()))
        ips = {el["ip"] for el in dj.load_json_lst({})}
        self.assertEqual(ips, {IP_A, IP_B})

    def test_send_data_json_all_env_filtered(self):
        """ env=B → 仅向 B 环境主机 cp json，不再下发其它环境 """
        dj = DataJsonUpdate(
            str(uuid_module.uuid4()), env_id=self.env_b.id)
        with mock.patch(
                "service_upgrade.update_data_json.SaltClient") as mock_salt:
            mock_salt.return_value.cp_file.return_value = (True, "")
            fail_message = dj.send_data_json_all()
        self.assertEqual(fail_message, [])
        targets = [call.kwargs.get("target")
                   for call in mock_salt.return_value.cp_file.call_args_list]
        self.assertEqual(targets, [IP_B])


class UpdateDataJsonCallerTestCase(DataJsonUpdateEnvBase):
    """ 调用链传入升级所属环境 """

    def test_update_data_json_passes_env_id(self):
        """ tasks.update_data_json 透传 env_id 给 DataJsonUpdate """
        with mock.patch("service_upgrade.tasks.DataJsonUpdate") as mdj:
            mdj.return_value.send_data_json_all.return_value = []
            state, msg = tasks.update_data_json(
                "fake-uuid", [], env_id=self.env_b.id)
        self.assertTrue(state)
        self.assertEqual(
            mdj.call_args,
            mock.call("fake-uuid", env_id=self.env_b.id))

    def test_update_data_json_env_none_default(self):
        """ env_id 缺省为 None → DataJsonUpdate 走存量全量行为 """
        with mock.patch("service_upgrade.tasks.DataJsonUpdate") as mdj:
            mdj.return_value.send_data_json_all.return_value = []
            tasks.update_data_json("fake-uuid", [])
        self.assertEqual(
            mdj.call_args, mock.call("fake-uuid", env_id=None))

    def test_upgrade_service_passes_history_env(self):
        """ upgrade_service 任务按 UpgradeHistory.env 过滤 data.json """
        history = UpgradeHistory.objects.create(
            operator=self.operator, env=self.env_b)
        with mock.patch(
                "service_upgrade.tasks.update_data_json",
                return_value=(True, "ok")) as m_up, \
                mock.patch("service_upgrade.tasks.set_alert_maintain"), \
                mock.patch("service_upgrade.tasks.update_product_version"):
            tasks.upgrade_service(history.id)
        args, kwargs = m_up.call_args
        self.assertEqual(args[0], self.main.operation_uuid)
        # 本次升级未含明细 → 详情查询集为空
        self.assertEqual(list(args[1]), [])
        self.assertEqual(kwargs.get("env_id"), self.env_b.id)
        history.refresh_from_db()
        # data.json 更新成功 → 升级前置置为成功
        from db_models.mixins import UpgradeStateChoices
        self.assertEqual(
            history.pre_upgrade_state,
            UpgradeStateChoices.UPGRADE_SUCCESS)
