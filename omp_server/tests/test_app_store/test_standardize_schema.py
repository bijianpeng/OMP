# -*- coding: utf-8 -*-
"""
detail 参数 install_detail_args 写入侧 schema 标准化测试

背景（安装链路统一收尾第二步）：
- 两种 detail schema 并存：
  a) 标准 schema（键 install_args/ports/instance_name 等，
     DeploymentPlanImportView 与新链路 item 构造）；
  b) 前端 payload 原样 item（键 app_install_args/app_port/
     service_instance_name——老链路 executeInstall →
     install_utils.CreateInstallPlan 直接落库）。
- 读取侧执行器已双键兼容（bd017fe）；本步在写入侧统一收敛：
  两个 CreateInstallPlan.run() 落库前经 standardize_detail_args
  标准化，新数据统一写标准 schema，存量数据不动（读取侧兜底）。
- 转换必须幂等：已是标准 schema 的 item 原样返回（重装重放
  install_with_package 会把历史 detail 原样传回 NewCreateInstallPlan）。
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
from app_store.new_install_utils import standardize_detail_args
from db_models.models import (
    ApplicationHub, DetailInstallHistory, Env, Host,
    MainInstallHistory, Service, UploadPackageHistory)

IP = "10.10.10.31"

# 标准 schema 全键（与 app_store/views.py DeploymentPlanImportView
# 构造的 detail_install_args 一致）
STANDARD_KEYS = {
    "ip", "name", "ports", "version", "run_user",
    "data_folder", "cluster_name", "install_args", "instance_name",
}

# 老链路前端 payload 的三个独有键（标准化后不再落库）
LEGACY_KEYS = {"app_install_args", "app_port", "service_instance_name"}


def _make_env_host():
    """构造 Env / Host 最小对象图（data_folder 供标准化取数）"""
    if not Env.objects.filter(id=1).exists():
        Env.objects.create(id=1, name="default")
    if not Host.objects.filter(ip=IP).exists():
        Host.objects.create(
            instance_name=f"host-{IP}", ip=IP, port=22, username="root",
            password="fake_password", data_folder="/data/std",
            operate_system="CentOS", host_name=f"hostname-{IP}",
            agent_dir="/data/std",
        )


FRONTEND_ITEM = {
    "name": "jdk",
    "version": "8u211",
    "ip": IP,
    "cluster_name": "test_cluster_1",
    "product_instance_name": "pi-1",
    "app_install_args": [
        {"name": "安装目录", "key": "base_dir", "default": "/jdk",
         "dir_key": "{data_path}"},
        {"name": "安装用户", "key": "run_user", "default": "omp"},
    ],
    "app_port": [
        {"name": "服务端口", "protocol": "TCP", "key": "service_port",
         "default": 19001},
    ],
    "service_instance_name": "jdk-10-31",
}


class StandardizeDetailArgsTestCase(TestCase):
    """ standardize_detail_args 转换函数行为 """

    def setUp(self):
        _make_env_host()

    def test_frontend_item_converted_to_standard_schema(self):
        """ 前端原样 item → 标准 schema，全键断言，老键剔除 """
        std = standardize_detail_args(FRONTEND_ITEM)
        self.assertEqual(
            set(std.keys()), STANDARD_KEYS | {"product_instance_name"})
        self.assertEqual(std["ip"], IP)
        self.assertEqual(std["name"], "jdk")
        self.assertEqual(std["version"], "8u211")
        self.assertEqual(std["ports"], FRONTEND_ITEM["app_port"])
        self.assertEqual(std["install_args"], FRONTEND_ITEM["app_install_args"])
        self.assertEqual(std["instance_name"], "jdk-10-31")
        self.assertEqual(std["cluster_name"], "test_cluster_1")
        # run_user 从 app_install_args 中提取（主机映射/默认已写入 default）
        self.assertEqual(std["run_user"], "omp")
        # data_folder 从 Host 表补齐
        self.assertEqual(std["data_folder"], "/data/std")
        # 老键不再落库，扩展键（product_instance_name）保留
        for key in LEGACY_KEYS:
            self.assertNotIn(key, std)

    def test_standard_schema_item_idempotent(self):
        """ 已是标准 schema 的 item 原样返回（重装重放场景）"""
        std = standardize_detail_args(dict(FRONTEND_ITEM))
        again = standardize_detail_args(std)
        self.assertEqual(again, std)
        self.assertIn("install_args", again)

    def test_item_without_legacy_keys_not_crash(self):
        """ 缺老键的 item（如仅 ip/name/version）不崩溃，键补默认值 """
        std = standardize_detail_args(
            {"ip": IP, "name": "jdk", "version": "1.8.0"})
        self.assertEqual(std["install_args"], [])
        self.assertEqual(std["ports"], [])
        self.assertIsNone(std["instance_name"])
        self.assertIsNone(std["cluster_name"])
        self.assertEqual(std["run_user"], "")
        self.assertEqual(std["data_folder"], "/data/std")

    def test_run_user_defaults_empty_when_absent(self):
        """ app_install_args 无 run_user 时 run_user 落空串 """
        item = dict(FRONTEND_ITEM)
        item["app_install_args"] = [
            {"name": "安装目录", "key": "base_dir", "default": "/jdk"}]
        std = standardize_detail_args(item)
        self.assertEqual(std["run_user"], "")


class OldChainRunWritesStandardSchemaTestCase(TestCase):
    """ 老链路 install_utils.CreateInstallPlan.run 落库标准 schema """

    def test_run_detail_has_install_args_key(self):
        _make_env_host()
        package = UploadPackageHistory.objects.create(
            operation_uuid=str(uuid_module.uuid4()),
            package_name="jdk-8u211.tar.gz",
            package_md5="0" * 32,
            package_path="test/jdk-8u211.tar.gz",
        )
        app = ApplicationHub.objects.create(
            app_name="jdk", app_version="8u211",
            app_type=ApplicationHub.APP_TYPE_SERVICE,
            app_package=package,
        )
        service = Service.objects.create(
            ip=IP, service_instance_name="jdk-10-31",
            service=app, service_status=Service.SERVICE_STATUS_INSTALLING,
            service_port="[]",
        )
        plan = install_utils.CreateInstallPlan(install_data={
            "install_type": 0,
            "install_services": [dict(FRONTEND_ITEM)],
        })
        with mock.patch.object(install_utils.CreateInstallPlan, "create_service",
                              return_value=service), \
                mock.patch.object(install_utils.CreateInstallPlan,
                                  "create_product_instance"), \
                mock.patch.object(install_utils.CreateInstallPlan,
                                  "check_if_has_post_action",
                                  return_value=False), \
                mock.patch.object(install_utils, "install_service") as mock_task, \
                mock.patch.object(install_utils.DataJson, "run"):
            mock_task.delay.return_value = "fake-task-id"
            flag, msg = plan.run()
        self.assertTrue(flag, msg)
        detail = DetailInstallHistory.objects.get(service=service)
        self.assertIn("install_args", detail.install_detail_args)
        self.assertNotIn("app_install_args", detail.install_detail_args)
        self.assertNotIn("service_instance_name", detail.install_detail_args)
        self.assertEqual(
            detail.install_detail_args["instance_name"], "jdk-10-31")


class NewChainRunKeepsStandardSchemaTestCase(TestCase):
    """ 新链路 run() 对标准 item 幂等（原样落库，不丢键不变形）"""

    def test_run_detail_unchanged_for_standard_item(self):
        _make_env_host()
        package = UploadPackageHistory.objects.create(
            operation_uuid=str(uuid_module.uuid4()),
            package_name="redis-5.tar.gz",
            package_md5="0" * 32,
            package_path="test/redis-5.tar.gz",
        )
        app = ApplicationHub.objects.create(
            app_name="redis", app_version="5.0.0",
            app_type=ApplicationHub.APP_TYPE_COMPONENT,
            app_package=package,
        )
        service = Service.objects.create(
            ip=IP, service_instance_name="redis-10-31",
            service=app, service_status=Service.SERVICE_STATUS_INSTALLING,
            service_port="[]",
        )
        item = {
            "name": "redis", "version": "5.0.0", "ip": IP,
            "install_args": [{"key": "base_dir", "default": "/redis"}],
            "ports": [{"key": "service_port", "default": 6379}],
            "instance_name": "redis-10-31", "cluster_name": None,
            "data_folder": "/data/std", "run_user": "omp",
        }
        plan = NewCreateInstallPlan(
            all_install_service_lst=[item], unique_key="uk-std-schema")
        with mock.patch.object(NewCreateInstallPlan, "create_service",
                              return_value=service), \
                mock.patch.object(NewCreateInstallPlan,
                                  "create_product_instance"), \
                mock.patch.object(NewCreateInstallPlan,
                                  "check_if_has_post_action",
                                  return_value=False), \
                mock.patch.object(NewCreateInstallPlan,
                                  "create_pre_install_history"), \
                mock.patch.object(NewCreateInstallPlan,
                                  "create_post_install_history"), \
                mock.patch("app_store.new_install_utils.DataJson"), \
                mock.patch("app_store.new_install_utils.BaseRedisData"), \
                mock.patch(
                    "app_store.new_install_utils.install_service_task"
                ) as mock_task:
            mock_task.delay.return_value = "fake-task-id"
            flag, msg = plan.run()
        self.assertTrue(flag, str(msg))
        detail = DetailInstallHistory.objects.get(service=service)
        for key, value in item.items():
            self.assertEqual(detail.install_detail_args.get(key), value)
        self.assertNotIn("app_install_args", detail.install_detail_args)


class OldDataJsonDualKeyTestCase(TestCase):
    """ 老链路 DataJson.get_ser_install_args 双键兼容（读取侧兜底）

    老链路 run() 写入标准 schema 后，其 DataJson 原单读 app_install_args
    会取到 None，data.json 缺 install_args → 目标机安装参数不全。
    与 bd017fe 同模式补 install_args 回退。
    """

    def _make_service_with_detail(self, detail_args):
        if not Env.objects.filter(id=1).exists():
            Env.objects.create(id=1, name="default")
        package = UploadPackageHistory.objects.create(
            operation_uuid=str(uuid_module.uuid4()),
            package_name="p.tar.gz", package_md5="0" * 32,
            package_path="test/p.tar.gz")
        app = ApplicationHub.objects.create(
            app_name="kafka", app_version="2.0.0",
            app_type=ApplicationHub.APP_TYPE_COMPONENT,
            app_package=package)
        service = Service.objects.create(
            ip=IP, service_instance_name="kafka-10-31",
            service=app, service_status=Service.SERVICE_STATUS_NORMAL,
            service_port="[]")
        main = MainInstallHistory.objects.create(
            operator="test", operation_uuid=str(uuid_module.uuid4()))
        return service, DetailInstallHistory.objects.create(
            service=service, main_install_history=main,
            install_detail_args=detail_args)

    def test_reads_standard_schema(self):
        """ 标准 schema（新写入）→ install_args 正常取出 """
        service, _ = self._make_service_with_detail({
            "ip": IP, "name": "kafka",
            "install_args": [{"key": "base_dir", "default": "/kafka"}],
        })
        res = install_utils.DataJson(
            operation_uuid=str(uuid_module.uuid4())
        ).get_ser_install_args(service)
        self.assertEqual(
            res["install_args"], [{"key": "base_dir", "default": "/kafka"}])

    def test_reads_legacy_schema(self):
        """ 存量老 schema → 兼容回退 app_install_args（行为不回归）"""
        service, _ = self._make_service_with_detail({
            "ip": IP, "name": "kafka",
            "app_install_args": [{"key": "base_dir", "default": "/kafka"}],
        })
        res = install_utils.DataJson(
            operation_uuid=str(uuid_module.uuid4())
        ).get_ser_install_args(service)
        self.assertEqual(
            res["install_args"], [{"key": "base_dir", "default": "/kafka"}])
