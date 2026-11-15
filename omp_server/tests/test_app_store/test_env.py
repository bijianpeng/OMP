# -*- coding: utf-8 -*-
"""
app_store 模块环境上下文接入测试（多环境架构 Task 14）

覆盖：
1. 部署方案（快速部署导入）创建落当前环境；安装历史同环境；
   导入使用的候选主机按方案环境过滤（跨环境主机不可见 → 主机未纳管）
2. 部署方案列表按当前环境过滤
3. 安装/纳管链路 Service.env = 主机.env（spec #10）；
   get_or_create_env 兜底创建补 code="default"
4. 安装向导主机候选（createServiceDistribution host 列表）按环境过滤
5. 安装后注册监控 add_prometheus env 参数取 service.env.code（非写死 default）
6. 安装后触发巡检 env 取安装历史绑定环境（非 Env.objects.last()）
7. 安装历史 / 执行记录列表按当前环境过滤

测试基建说明：同 tests/test_inspection/test_env.py——继承 BaseTest（非
AutoLoginTest），显式放开本文件涉及视图的认证与权限；本地无 Redis，
涉及 BaseRedisData / DataJson / PrometheusUtils / APIClient 处均 mock。
"""
import json
from types import SimpleNamespace
from unittest import mock

import pytest

from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse

from tests.base import BaseTest
from db_models.models import (
    Env, Host, Service, ApplicationHub,
    DeploymentPlan, MainInstallHistory, DetailInstallHistory,
    ExecutionRecord)
from app_store import views as app_store_views
from app_store import views_for_install
from app_store import new_install_view
from app_store.new_install_serializers import (
    CreateServiceDistributionSerializer)
from services.app_check.manage_ser_exec import ManagerService
from app_store import tasks as app_store_tasks


def make_host(ip, env, instance_name=None):
    """ 直接落库一台指定环境的主机 """
    return Host.objects.create(
        instance_name=instance_name or ip, ip=ip,
        username="root", password="pwd", operate_system="CentOS",
        env=env)


def make_app(name, version="1.0.0", monitor=None):
    """ 直接落库一个已发布应用/组件 """
    return ApplicationHub.objects.create(
        is_release=True, app_type=1, app_name=name, app_version=version,
        app_port=json.dumps([
            {"name": "服务端口", "protocol": "TCP",
             "key": "service_port", "default": "18080"}]),
        app_dependence=None,
        app_install_args=json.dumps([
            {"name": "安装目录", "key": "base_dir",
             "default": "{data_path}/app/%s" % name}]),
        app_controllers=json.dumps({"start": "./start.sh"}),
        extend_fields={}, is_base_env=False, app_monitor=monitor)


def make_plan(name, env):
    """ 直接落库一条指定环境的部署方案 """
    return DeploymentPlan.objects.create(
        plan_name=name, host_num=1, product_num=0, service_num=1,
        create_user="admin", operation_uuid="uuid-%s" % name, env=env)


@pytest.mark.django_db
class AppStoreEnvContextTest(BaseTest):
    """ app_store 模块环境上下文行为 """

    def setUp(self):
        super(AppStoreEnvContextTest, self).setUp()
        # 显式放开本文件涉及视图的认证与权限（说明同 inspection 环境测试）
        for view_cls in (
                app_store_views.DeploymentPlanListView,
                app_store_views.DeploymentPlanImportView,
                app_store_views.DeploymentOperableView,
                app_store_views.ExecutionRecordAPIView,
                views_for_install.InstallHistoryView,
                views_for_install.ServiceInstallHistoryDetailView,
                new_install_view.MainInstallHistoryView):
            view_cls.authentication_classes = []
            view_cls.permission_classes = [AllowAny]
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")
        self.plan_list_url = reverse("deploymentPlanList-list")
        self.plan_import_url = reverse("deploymentPlanImport-list")
        self.exec_record_url = reverse("ExecutionRecord-list")
        self.install_history_url = reverse("installHistory-list")
        self.main_history_url = reverse("mainInstallHistory-list")

    # ------------------------------------------------------------------
    # 1. 部署方案创建落当前环境（快速部署导入链路）
    # ------------------------------------------------------------------
    def test_plan_created_with_request_env(self):
        """ 快速部署导入：方案/安装历史落请求环境，服务继承主机环境 """
        host_b = make_host("192.0.2.20", self.env_b, "host-b")
        make_app("demo")
        payload = {
            "instance_info_ls": [{"instance_name": "host-b",
                                  "run_user": ""}],
            "service_data_ls": [{"instance_name": "host-b",
                                 "service_name": "demo",
                                 "vip": None, "role": None,
                                 "memory": ""}],
        }
        # DataJson 落盘文件与本次断言无关，mock 掉
        with mock.patch("app_store.views.DataJson"):
            resp = self.client.post(
                self.plan_import_url, data=json.dumps(payload),
                content_type="application/json; charset=utf-8",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp.get("code"), 0)

        plan = DeploymentPlan.objects.order_by("-id").first()
        self.assertEqual(plan.env, self.env_b)
        main = MainInstallHistory.objects.order_by("-id").first()
        self.assertEqual(main.env, self.env_b)
        service = Service.objects.filter(ip=host_b.ip).first()
        self.assertIsNotNone(service)
        self.assertEqual(service.env, self.env_b)

    def test_import_rejects_host_from_other_env(self):
        """ 跨环境主机对导入不可见：按未纳管报错，不落任何数据 """
        # 主机属于 default 环境，导入请求携带 B 环境上下文
        make_host("192.0.2.21", self.env_default, "host-a")
        make_app("demo")
        payload = {
            "instance_info_ls": [{"instance_name": "host-a",
                                  "run_user": ""}],
            "service_data_ls": [{"instance_name": "host-a",
                                 "service_name": "demo",
                                 "vip": None, "role": None,
                                 "memory": ""}],
        }
        with mock.patch("app_store.views.DataJson"):
            resp = self.client.post(
                self.plan_import_url, data=json.dumps(payload),
                content_type="application/json; charset=utf-8",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp.get("code"), 1)
        self.assertIn("主机未纳管", resp.get("message", ""))
        self.assertEqual(DeploymentPlan.objects.count(), 0)
        self.assertEqual(Service.objects.count(), 0)

    # ------------------------------------------------------------------
    # 2. 部署方案列表过滤
    # ------------------------------------------------------------------
    def test_plan_list_filtered(self):
        """ 两环境各一条方案，列表按当前环境上下文过滤 """
        plan_a = make_plan("方案-default", self.env_default)
        plan_b = make_plan("方案-B", self.env_b)

        resp_b = self.client.get(
            self.plan_list_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        self.assertEqual(
            [p.get("id") for p in resp_b.get("data").get("results")],
            [plan_b.id])

        # 未携带标识（pytest 注入 default 环境）：仅见 default 方案
        resp_a = self.client.get(self.plan_list_url).json()
        self.assertEqual(resp_a.get("code"), 0)
        self.assertEqual(
            [p.get("id") for p in resp_a.get("data").get("results")],
            [plan_a.id])

    # ------------------------------------------------------------------
    # 3. 安装/纳管链路服务继承主机环境
    # ------------------------------------------------------------------
    def test_install_service_inherits_host_env(self):
        """ 纳管入库 create_database_one：Service.env = 主机.env """
        host_b = make_host("192.0.2.10", self.env_b)
        app_obj = make_app("demo")
        manager = ManagerService(info={}, is_extend=True)
        main_obj = MainInstallHistory.objects.create(
            operation_uuid="envtest-manage", install_status=0)
        data = {
            "app_name": "demo",
            "app_version": app_obj.app_version,
            "app_ip": [host_b.ip],
            "dependence_instance": [],
            "is_use_exist": False,
            "exist_instance": [],
            "install_args": {"service_port": "18080",
                             "base_dir": "/data/app/demo"},
        }
        manager.create_database_one(data, main_obj)

        service = Service.objects.get(ip=host_b.ip)
        # 主机 env 为 B：服务继承 B，而非 get_or_create_env 的 default
        self.assertEqual(service.env, self.env_b)
        self.assertNotEqual(service.env, self.env_default)

    def test_get_or_create_env_fallback_with_code(self):
        """ 兜底创建 default 环境时补 code="default"（对齐幂等迁移） """
        Env.objects.filter(id=1).delete()
        manager = ManagerService(info={}, is_extend=True)
        env = manager.get_or_create_env()
        self.assertEqual(env.id, 1)
        self.assertEqual(env.name, "default")
        self.assertEqual(env.code, "default")

    # ------------------------------------------------------------------
    # 4. 安装向导主机候选按环境过滤
    # ------------------------------------------------------------------
    def test_operable_hosts_limited_to_plan_env(self):
        """ createServiceDistribution 主机候选仅含当前环境主机 """
        make_host("192.0.2.11", self.env_default)
        host_b = make_host("192.0.2.12", self.env_b)

        def fetch_host_ips(env):
            serializer = CreateServiceDistributionSerializer(
                context={"request": SimpleNamespace(env=env)})
            with mock.patch(
                    "app_store.new_install_serializers.BaseRedisData") as brd:
                brd.return_value.get_step_3_checked_data.return_value = {
                    "data": {"basic": [], "dependence": []}}
                brd.return_value.get_step_2_origin_data.return_value = {
                    "install": {}}
                brd.return_value.get_with_ser.return_value = []
                result = serializer.create(
                    {"unique_key": "uk-env", "data": {}})
            return [el["ip"] for el in result["data"]["host"]]

        self.assertEqual(fetch_host_ips(self.env_b), [host_b.ip])
        self.assertEqual(fetch_host_ips(self.env_default),
                         ["192.0.2.11"])

    # ------------------------------------------------------------------
    # 5. 安装后注册监控使用服务环境 code
    # ------------------------------------------------------------------
    def test_add_service_uses_service_env_code(self):
        """ add_prometheus env 参数 = service.env.code（staging 非 default） """
        app_obj = make_app(
            "demo", monitor={"type": "JavaSpringBoot",
                             "metric_port": "{service_port}",
                             "process_name": ""})
        service = Service.objects.create(
            ip="192.0.2.13",
            service_instance_name="demo-56-13",
            service=app_obj,
            service_port=json.dumps([
                {"key": "service_port", "default": "18080"}]),
            service_status=Service.SERVICE_STATUS_NORMAL,
            env=self.env_b)
        main_obj = MainInstallHistory.objects.create(
            operation_uuid="envtest-monitor", install_status=2,
            env=self.env_b)
        DetailInstallHistory.objects.create(
            service=service, main_install_history=main_obj,
            install_step_status=DetailInstallHistory.INSTALL_STATUS_SUCCESS,
            install_detail_args={"install_args": []})

        with mock.patch.object(app_store_tasks, "PrometheusUtils") as prom_cls:
            prom_cls.return_value.add_service.return_value = (True, "")
            app_store_tasks.add_prometheus(main_obj.id)

        self.assertTrue(prom_cls.return_value.add_service.called)
        service_data = prom_cls.return_value.add_service.call_args[0][0]
        self.assertEqual(service_data.get("env"), "staging")

    # ------------------------------------------------------------------
    # 6. 安装后触发巡检使用安装环境
    # ------------------------------------------------------------------
    def test_make_inspection_uses_install_env(self):
        """ make_inspection 提交的巡检 env = 安装历史绑定环境 id """
        main_obj = MainInstallHistory.objects.create(
            operation_uuid="envtest-inspect", install_status=2,
            env=self.env_b)
        with mock.patch("rest_framework.test.APIClient") as client_cls:
            client_cls.return_value.post.return_value.json.return_value = {
                "code": 0}
            app_store_tasks.make_inspection(
                "admin", env_id=main_obj.env_id)
        posted = client_cls.return_value.post.call_args
        posted_data = json.loads(posted.kwargs.get("data"))
        # 安装环境为 B：非 Env.objects.last() 兜底值
        self.assertEqual(posted_data.get("env"), self.env_b.id)

    def test_install_service_task_passes_env_to_inspection(self):
        """ install_service 任务按安装历史 env 触发巡检 """
        main_obj = MainInstallHistory.objects.create(
            operation_uuid="envtest-task", install_status=2,
            env=self.env_b)
        with mock.patch.object(app_store_tasks, "InstallServiceExecutor"), \
                mock.patch.object(app_store_tasks, "add_prometheus"), \
                mock.patch.object(app_store_tasks,
                                  "make_inspection") as mock_inspection:
            app_store_tasks.install_service.run(main_obj.id, "admin")
        self.assertTrue(mock_inspection.called)
        self.assertEqual(
            mock_inspection.call_args.kwargs.get("env_id"), self.env_b.id)

    # ------------------------------------------------------------------
    # 7. 安装历史 / 执行记录列表过滤
    # ------------------------------------------------------------------
    def test_install_history_and_execution_record_filtered(self):
        """ 安装历史（新旧两入口）与执行记录列表按当前环境过滤 """
        main_a = MainInstallHistory.objects.create(
            operation_uuid="envtest-his-a", install_status=2,
            env=self.env_default)
        main_b = MainInstallHistory.objects.create(
            operation_uuid="envtest-his-b", install_status=2,
            env=self.env_b)
        # 执行记录由信号生成时不带环境（env 默认 1），此处直接按展示口径造数
        record_a = ExecutionRecord.objects.create(
            module="MainInstallHistory", module_id=main_a.operation_uuid,
            count=1, env=self.env_default)
        record_b = ExecutionRecord.objects.create(
            module="MainInstallHistory", module_id=main_b.operation_uuid,
            count=1, env=self.env_b)

        headers = {"HTTP_X_ENV_ID": str(self.env_b.id)}
        resp_exec = self.client.get(
            self.exec_record_url, **headers).json()
        self.assertEqual(resp_exec.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_exec.get("data").get("results")],
            [record_b.id])

        resp_install = self.client.get(
            self.install_history_url, **headers).json()
        self.assertEqual(resp_install.get("code"), 0)
        # installHistory 无分页器（data 为列表），序列化字段为 operation_uuid
        install_data = resp_install.get("data")
        if isinstance(install_data, dict):
            install_data = install_data.get("results")
        self.assertEqual(
            [r.get("operation_uuid") for r in install_data],
            [main_b.operation_uuid])

        resp_main = self.client.get(self.main_history_url, **headers).json()
        self.assertEqual(resp_main.get("code"), 0)
        # mainInstallHistory 序化字段同样无 id，用 operation_uuid 断言
        self.assertEqual(
            [r.get("operation_uuid")
             for r in resp_main.get("data").get("results")],
            [main_b.operation_uuid])
