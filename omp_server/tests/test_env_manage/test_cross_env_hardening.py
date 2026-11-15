# -*- coding: utf-8 -*-
"""
跨环境操作收口测试（多环境架构 Task 7b）

统一模式：按 id（URL pk 或 body ids）定位资源的入口，环境 A 上下文操作
环境 B 资源必须被拒绝（400 / 404 / 无效果），本环境内正常路径不回归。
对应 brief 15 项修复点，每个修复点至少一个跨环境拒绝断言。

测试基建说明：同 tests/test_services/test_service_env.py——继承 BaseTest
（非 AutoLoginTest），显式放开本文件涉及视图的认证与权限；显式 X-Env-Id
走完整环境解析链，request.env 为 header 指定环境；未携带标识时 pytest
注入 default 环境。
"""
import json
from importlib import import_module
from unittest import mock

import pytest

from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse
from rest_framework_jwt.utils import jwt_encode_handler, jwt_payload_handler

from tests.base import BaseTest
from db_models.models import (
    Alert, AlertRule, ApplicationHub, BackupHistory, Env, Host,
    HostOperateLog, InspectionCrontab, SelfHealingHistory,
    SelfHealingSetting, Service, UserProfile, UserEnv)
from hosts import views as hosts_views
from hosts import hosts_serializers
from services import views as services_views
from services import self_heal_view as self_heal_views
from promemonitor import views as promemonitor_views
from backups import views as backups_views
from inspection import views as inspection_views


def make_host(instance_name, ip, env, **kwargs):
    """ 直接落库一个指定环境的主机 """
    return Host.objects.create(
        instance_name=instance_name, ip=ip, port=22, username="root",
        password="pass", data_folder="/data", operate_system="CentOS",
        env=env, **kwargs)


def make_app(app_name, version="1.0", **kwargs):
    """ 直接落库一个应用（全局目录，不分环境） """
    return ApplicationHub.objects.create(
        app_name=app_name, app_version=version,
        app_type=kwargs.pop("app_type", ApplicationHub.APP_TYPE_COMPONENT),
        is_release=True, is_base_env=False,
        extend_fields={"base_env": False, "affinity": ""}, **kwargs)


def make_service(app, instance_name, ip, env, **kwargs):
    """ 直接落库一个指定环境的服务实例 """
    return Service.objects.create(
        service_instance_name=instance_name, ip=ip,
        service_status=kwargs.pop("service_status",
                                  Service.SERVICE_STATUS_NORMAL),
        service=app, env=env, **kwargs)


class CrossEnvTestBase(BaseTest):
    """ 两环境造数 + 涉及视图放开认证权限的公共基类 """

    def setUp(self):
        super(CrossEnvTestBase, self).setUp()
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")

    @staticmethod
    def open_views(*view_classes):
        for view_cls in view_classes:
            view_cls.authentication_classes = []
            view_cls.permission_classes = [AllowAny]

    def post_json(self, url, data, env_id=None):
        kwargs = {}
        if env_id is not None:
            kwargs["HTTP_X_ENV_ID"] = str(env_id)
        return self.client.post(
            url, data=json.dumps(data),
            content_type="application/json; charset=utf-8", **kwargs)

    def put_json(self, url, data, env_id=None):
        kwargs = {}
        if env_id is not None:
            kwargs["HTTP_X_ENV_ID"] = str(env_id)
        return self.client.put(
            url, data=json.dumps(data),
            content_type="application/json; charset=utf-8", **kwargs)


@pytest.mark.django_db
class HostsCrossEnvTest(CrossEnvTestBase):
    """ hosts 模块按 id/ips 操作入口的跨环境收口（brief 1-4 项） """

    def setUp(self):
        super(HostsCrossEnvTest, self).setUp()
        self.open_views(
            hosts_views.HostUpdateView, hosts_views.IpListView,
            hosts_views.HostMaintenanceView, hosts_views.HostAgentRestartView,
            hosts_views.HostInitView, hosts_views.HostUninstallView,
            hosts_views.HostReinstallView, hosts_views.MonitorReinstallView,
            hosts_views.HostOperateLogView, hosts_views.HostsAgentStatusView)
        self.host_a = make_host("host_env_a", "10.20.0.1", self.env_default)
        self.host_b = make_host("host_env_b", "10.20.0.2", self.env_b)

    def test_host_update_cross_env_rejected(self):
        """ 项1 HostUpdateView：B 环境上下文 PUT/PATCH default 环境主机 ->
            统一包 404（未找到），主机数据不变；本环境 PATCH 正常 """
        with mock.patch.object(hosts_serializers.SSH, "check",
                               return_value=(True, "")), \
            mock.patch.object(hosts_serializers.SSH, "is_sudo",
                              return_value=(True, "sudo")), \
            mock.patch.object(hosts_serializers.SSH, "cmd",
                              return_value=(True, "")):
            resp = self.put_json(
                reverse("hosts-detail", args=[self.host_a.id]),
                {"instance_name": "hacked", "ip": self.host_a.ip,
                 "port": 22, "username": "root", "password": "new_password",
                 "data_folder": "/data", "operate_system": "CentOS",
                 "use_ntpd": False},
                env_id=self.env_b.id).json()
            self.assertEqual(resp.get("code"), 1)
            self.host_a.refresh_from_db()
            self.assertEqual(self.host_a.instance_name, "host_env_a")

            # 本环境 PATCH 正常
            resp_ok = self.client.patch(
                reverse("hosts-detail", args=[self.host_b.id]),
                data=json.dumps({"instance_name": "host_env_b_new"}),
                content_type="application/json; charset=utf-8",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
            self.assertEqual(resp_ok.get("code"), 0)
            self.host_b.refresh_from_db()
            self.assertEqual(self.host_b.instance_name, "host_env_b_new")

    def test_ip_list_cross_env_filtered(self):
        """ 项2 IpListView：IP 枚举按当前环境过滤，不串环境 """
        resp_b = self.client.get(
            reverse("ips-list"), HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        self.assertEqual(resp_b.get("data"), [self.host_b.ip])

        resp_default = self.client.get(reverse("ips-list")).json()
        self.assertEqual(resp_default.get("code"), 0)
        self.assertEqual(resp_default.get("data"), [self.host_a.ip])

    def test_maintain_cross_env_rejected(self):
        """ 项3 HostMaintenanceView：B 上下文携带 default 主机 id ->
            校验拒绝（视为不存在），告警 API 不下发、状态不变 """
        with mock.patch.object(
                hosts_serializers.Alertmanager,
                "set_maintain_by_host_list") as maintain_mock:
            resp = self.post_json(
                reverse("maintain-list"),
                {"is_maintenance": True,
                 "host_ids": [self.host_a.id]},
                env_id=self.env_b.id).json()
            self.assertEqual(resp.get("code"), 1)
            maintain_mock.assert_not_called()
        self.host_a.refresh_from_db()
        self.assertFalse(self.host_a.is_maintenance)

    def test_agent_restart_cross_env_no_dispatch(self):
        """ 项3 HostAgentRestartView：跨环境 id 不下发 celery 任务，
            主机 agent 状态不变 """
        with mock.patch.object(
                hosts_serializers.host_agent_restart, "delay") as delay_mock:
            resp = self.post_json(
                reverse("restartHostAgent-list"),
                {"host_ids": [self.host_a.id]},
                env_id=self.env_b.id).json()
            self.assertEqual(resp.get("code"), 1)
            delay_mock.assert_not_called()
        self.host_a.refresh_from_db()
        self.assertNotEqual(self.host_a.host_agent, Host.AGENT_RESTART)

    def test_init_and_reinstall_cross_env_no_dispatch(self):
        """ 项3 HostInitView / HostReinstallView / MonitorReinstallView：
            跨环境 id 校验拒绝，init/deploy/reinstall 任务均不下发 """
        for url_name, delay_attr in (
                ("hostInit-list", "init_host"),
                ("hostReinstall-list", "deploy_agent"),
                ("monitorReinstall-list", "reinstall_monitor_celery_task")):
            url = reverse(url_name)
            with mock.patch.object(
                    getattr(hosts_serializers, delay_attr),
                    "delay") as delay_mock:
                resp = self.post_json(
                    url, {"host_ids": [self.host_a.id]},
                    env_id=self.env_b.id).json()
                self.assertEqual(resp.get("code"), 1, url_name)
                delay_mock.assert_not_called()
        self.host_a.refresh_from_db()
        self.assertNotEqual(self.host_a.init_status, Host.INIT_EXECUTING)

    def test_uninstall_cross_env_rejected(self):
        """ 项3 HostUninstallView：跨环境 id 校验拒绝，卸载任务不下发，
            主机 agent 状态不变 """
        with mock.patch.object(
                hosts_serializers.delete_hosts, "delay") as delay_mock:
            resp = self.post_json(
                reverse("hostUninstall-list"),
                {"id": self.host_a.id, "host_ids": [self.host_a.id]},
                env_id=self.env_b.id).json()
            self.assertEqual(resp.get("code"), 1)
            delay_mock.assert_not_called()
        self.host_a.refresh_from_db()
        self.assertNotEqual(
            self.host_a.host_agent, Host.AGENT_DEPLOY_DELETE)

    def test_operate_log_cross_env_hidden(self):
        """ 项3 HostOperateLogView（按 host_id 定位）：B 上下文查不到
            default 主机的操作日志，反之亦然 """
        HostOperateLog.objects.create(
            username="admin", description="a-log", host=self.host_a)
        HostOperateLog.objects.create(
            username="admin", description="b-log", host=self.host_b)

        resp_b = self.client.get(
            reverse("operateLog-list"),
            {"host_id": self.host_a.id},
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        self.assertEqual(resp_b.get("data"), [])

        resp_default = self.client.get(
            reverse("operateLog-list"),
            {"host_id": self.host_b.id}).json()
        self.assertEqual(resp_default.get("code"), 0)
        self.assertEqual(resp_default.get("data"), [])

        resp_own = self.client.get(
            reverse("operateLog-list"),
            {"host_id": self.host_b.id},
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(len(resp_own.get("data")), 1)
        self.assertEqual(resp_own.get("data")[0].get("description"), "b-log")

    def test_agent_status_cross_env_invisible(self):
        """ 项3 HostsAgentStatusView：跨环境 IP 的 agent 状态不可见
            （均在线的 IP 在 B 上下文判为不在）"""
        make_host("host_env_a2", "10.20.0.3", self.env_default,
                  host_agent=Host.AGENT_RUNNING, monitor_agent=0)
        make_host("host_env_b2", "10.20.0.4", self.env_b,
                  host_agent=Host.AGENT_RUNNING, monitor_agent=0)
        resp_cross = self.client.post(
            reverse("hostsAgentStatus-list"),
            data=json.dumps({"ip_list": ["10.20.0.3"]}),
            content_type="application/json; charset=utf-8",
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_cross.get("code"), 0)
        self.assertFalse(resp_cross.get("data"))

        resp_own = self.client.post(
            reverse("hostsAgentStatus-list"),
            data=json.dumps({"ip_list": ["10.20.0.4"]}),
            content_type="application/json; charset=utf-8",
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertTrue(resp_own.get("data"))


@pytest.mark.django_db
class ServicesCrossEnvTest(CrossEnvTestBase):
    """ services / 自愈模块按 id 操作入口的跨环境收口（brief 5-9 项） """

    def setUp(self):
        super(ServicesCrossEnvTest, self).setUp()
        self.open_views(
            services_views.ServiceActionView, services_views.ServiceDeleteView,
            self_heal_views.UpdateSelfHealingHistoryView,
            self_heal_views.SelfHealingSettingView)
        self.app_mysql = make_app("mysql")
        self.app_web = make_app(
            "webapp",
            app_dependence=json.dumps([{"name": "mysql", "version": "1.0"}]))
        self.service_a = make_service(
            self.app_mysql, "svc_mysql_a", "10.30.0.1", self.env_default)
        self.service_a2 = make_service(
            self.app_web, "svc_web_a", "10.30.0.1", self.env_default)
        self.service_b = make_service(
            self.app_mysql, "svc_mysql_b", "10.30.0.2", self.env_b)

    def test_service_action_cross_env_rejected(self):
        """ 项5 ServiceActionView：B 上下文对 default 环境服务下发启停 ->
            拒绝且 exec_action 任务不下发、服务状态不变；本环境正常下发 """
        with mock.patch.object(
                services_views.exec_action, "delay") as delay_mock:
            resp = self.post_json(
                reverse("action-list"),
                {"data": [{"action": 1, "id": self.service_a.id,
                           "operation_user": "admin"}]},
                env_id=self.env_b.id).json()
            self.assertEqual(resp.get("code"), 1)
            delay_mock.assert_not_called()
        self.service_a.refresh_from_db()
        self.assertEqual(
            self.service_a.service_status, Service.SERVICE_STATUS_NORMAL)

        with mock.patch.object(
                services_views.exec_action, "delay") as delay_mock:
            resp_ok = self.post_json(
                reverse("action-list"),
                {"data": [{"action": 1, "id": self.service_b.id,
                           "operation_user": "admin"}]},
                env_id=self.env_b.id).json()
            self.assertEqual(resp_ok.get("code"), 0)
            delay_mock.assert_called_once()

    def test_service_delete_check_cross_env_no_leak(self):
        """ 项6 ServiceDeleteView：依赖校验只看当前环境内服务——
            B 上下文传 default 环境服务 id 不再泄漏其依赖关系；
            default 上下文同 id 仍能给出本环境依赖提示 """
        url = reverse("delete-list")
        resp_cross = self.post_json(
            url, {"data": [{"id": self.service_a.id}]},
            env_id=self.env_b.id).json()
        self.assertEqual(resp_cross.get("code"), 0)
        self.assertEqual(resp_cross.get("data"), "无依赖信息")

        resp_own = self.post_json(
            url, {"data": [{"id": self.service_a.id}]}).json()
        self.assertEqual(resp_own.get("code"), 0)
        self.assertEqual(resp_own.get("data"), "存在依赖信息:webapp-1.0")

    def test_update_self_healing_history_cross_env_ignored(self):
        """ 项7 UpdateSelfHealingHistoryView：B 上下文批量置已读，
            default 环境记录不受影响；本环境记录正常更新 """
        history_a = SelfHealingHistory.objects.create(
            host_ip="10.30.0.1", service_name="svc_a",
            instance_name="svc_mysql_a", env=self.env_default)
        history_b = SelfHealingHistory.objects.create(
            host_ip="10.30.0.2", service_name="svc_b",
            instance_name="svc_mysql_b", env=self.env_b)

        resp = self.post_json(
            reverse("UpdateSelfHealingHistory-list"),
            {"ids": [history_a.id], "is_read": 1},
            env_id=self.env_b.id).json()
        self.assertEqual(resp.get("code"), 0)
        history_a.refresh_from_db()
        history_b.refresh_from_db()
        self.assertEqual(history_a.is_read, 0)
        self.assertEqual(history_b.is_read, 0)

        resp_own = self.post_json(
            reverse("UpdateSelfHealingHistory-list"),
            {"ids": [history_b.id], "is_read": 1},
            env_id=self.env_b.id).json()
        self.assertEqual(resp_own.get("code"), 0)
        history_b.refresh_from_db()
        self.assertEqual(history_b.is_read, 1)

    def test_self_heal_setting_dedup_scoped_by_env(self):
        """ 项8 自愈设置查重按环境隔离：default 已配置 redis，B 环境
            仍可配置 redis / all；B 环境内重复 / 已有 all 再加服务仍拒绝 """
        SelfHealingSetting.objects.create(
            env=self.env_default, repair_instance=["redis"], used=True)

        # B 环境配置与 default 相同实例：允许（此前全局查重误拒）
        resp_b = self.post_json(
            reverse("SelfHealingSetting-list"),
            {"used": True, "repair_instance": ["redis"]},
            env_id=self.env_b.id)
        self.assertEqual(resp_b.status_code, 201)
        setting_b = SelfHealingSetting.objects.filter(
            env=self.env_b).first()
        self.assertIsNotNone(setting_b)

        # B 环境已有 all 后再配置其它服务：拒绝（同环境内查重）
        SelfHealingSetting.objects.filter(env=self.env_b).update(
            repair_instance=["all"])
        resp_repeat = self.post_json(
            reverse("SelfHealingSetting-list"),
            {"used": True, "repair_instance": ["mysql"]},
            env_id=self.env_b.id).json()
        self.assertEqual(resp_repeat.get("code"), 1)

    def test_self_heal_setting_update_no_self_collision(self):
        """ 项8 更新自身行不触发查重自撞：B 行改自己的 repair_instance
            成功（排除自身行）"""
        setting_b = SelfHealingSetting.objects.create(
            env=self.env_b, repair_instance=["redis"])
        resp = self.put_json(
            reverse("SelfHealingSetting-detail", args=[setting_b.id]),
            {"used": True, "repair_instance": ["redis", "mysql"]},
            env_id=self.env_b.id).json()
        self.assertEqual(resp.get("code"), 0)
        setting_b.refresh_from_db()
        self.assertEqual(setting_b.repair_instance, ["redis", "mysql"])

    def test_self_heal_setting_unique_per_env(self):
        """ 项9 每环境至多一行自愈设置：同环境重复创建被 400 拒绝
            （unique 约束前的显式校验，避免 500）"""
        SelfHealingSetting.objects.create(env=self.env_default)
        resp = self.post_json(
            reverse("SelfHealingSetting-list"),
            {"used": False, "repair_instance": []}).json()
        self.assertEqual(resp.get("code"), 1)


@pytest.mark.django_db
class PromemonitorCrossEnvTest(CrossEnvTestBase):
    """ promemonitor 两个收口视图（brief 10-11 项） """

    def setUp(self):
        super(PromemonitorCrossEnvTest, self).setUp()
        self.open_views(
            promemonitor_views.BatchUpdateRuleView,
            promemonitor_views.UpdateAlertViewSet)
        rule_kwargs = dict(
            expr="up == 1", threshold_value=1, compare_str="==",
            for_time="1m", severity="critical", alert="a", service="s",
            status=1)
        self.rule_a = AlertRule.objects.create(
            env=self.env_default, **rule_kwargs)
        self.rule_b = AlertRule.objects.create(
            env=self.env_b, **rule_kwargs)

    def test_batch_update_rule_cross_env_ignored(self):
        """ 项10 BatchUpdateRuleView：B 上下文批量启停 default 环境规则 ->
            DB 不生效，且规则文件按 B 环境 code 生成（env 参数传递）"""
        with mock.patch.object(
                promemonitor_views.PrometheusUtils, "update_rule_file",
                return_value=True) as rule_file_mock, \
            mock.patch.object(
                promemonitor_views.PrometheusUtils, "reload_prometheus",
                return_value=True):
            resp = self.post_json(
                reverse("batchUpdateRule-list"),
                {"ids": [self.rule_a.id], "status": 0},
                env_id=self.env_b.id).json()
            self.assertEqual(resp.get("code"), 0)
            self.rule_a.refresh_from_db()
            self.rule_b.refresh_from_db()
            self.assertEqual(self.rule_a.status, 1)
            self.assertEqual(self.rule_b.status, 1)
            rule_file_mock.assert_called_once()
            self.assertEqual(
                rule_file_mock.call_args.kwargs.get("env"),
                self.env_b.code)

            # 本环境规则正常启停
            resp_own = self.post_json(
                reverse("batchUpdateRule-list"),
                {"ids": [self.rule_b.id], "status": 0},
                env_id=self.env_b.id).json()
            self.assertEqual(resp_own.get("code"), 0)
            self.rule_b.refresh_from_db()
            self.assertEqual(self.rule_b.status, 0)

    def test_update_alert_cross_env_ignored(self):
        """ 项11 UpdateAlertViewSet：B 上下文批量置已读，default 环境
            告警不受影响；本环境告警正常更新 """
        import django.utils.timezone as timezone
        alert_a = Alert.objects.create(
            alert_host_ip="10.40.0.1", alert_time=timezone.now(),
            env=self.env_default)
        alert_b = Alert.objects.create(
            alert_host_ip="10.40.0.2", alert_time=timezone.now(),
            env=self.env_b)

        resp = self.post_json(
            reverse("updateAlert-list"),
            {"ids": [alert_a.id], "is_read": 1},
            env_id=self.env_b.id).json()
        self.assertEqual(resp.get("code"), 0)
        alert_a.refresh_from_db()
        alert_b.refresh_from_db()
        self.assertEqual(alert_a.is_read, 0)
        self.assertEqual(alert_b.is_read, 0)

        resp_own = self.post_json(
            reverse("updateAlert-list"),
            {"ids": [alert_b.id], "is_read": 1},
            env_id=self.env_b.id).json()
        self.assertEqual(resp_own.get("code"), 0)
        alert_b.refresh_from_db()
        self.assertEqual(alert_b.is_read, 1)


@pytest.mark.django_db
class BackupsCrossEnvTest(CrossEnvTestBase):
    """ backups 模块收口（brief 12-13 项） """

    def setUp(self):
        super(BackupsCrossEnvTest, self).setUp()
        self.open_views(backups_views.BackupHistoryView)
        self.history_a = BackupHistory.objects.create(
            backup_name="bk-a", content="mysql-a", file_name="bk-a.tar.gz",
            result=BackupHistory.ING, env=self.env_default)
        self.history_b = BackupHistory.objects.create(
            backup_name="bk-b", content="mysql-b", file_name="bk-b.tar.gz",
            result=BackupHistory.ING, env=self.env_b)
        self.history_list_url = reverse("backupHistory-list")

    def test_history_ids_serializer_cross_env_rejected(self):
        """ 项13 BackupHistoryIdsSerializer：default 上下文删 B 环境记录
            文件 -> id 不存在校验拒绝，rm_backend_file 不执行；本环境正常 """
        with mock.patch.object(
                backups_views, "rm_backend_file",
                return_value=[]) as rm_mock:
            resp = self.post_json(
                self.history_list_url, {"ids": [self.history_b.id]}).json()
            self.assertEqual(resp.get("code"), 1)
            rm_mock.assert_not_called()

            resp_own = self.client.post(
                self.history_list_url,
                data=json.dumps({"ids": [self.history_a.id]}),
                content_type="application/json; charset=utf-8",
                HTTP_X_ENV_ID=str(self.env_default.id)).json()
            self.assertEqual(resp_own.get("code"), 0)
            rm_mock.assert_called_once()

    def test_history_list_env_authorization_enforced(self):
        """ 项12 BackupHistoryView env_exempt 类级宽度收窄：未授权用户
            显式携带 B 环境标识 -> 中间件 403（list 不再被类级豁免放行）；
            已授权环境正常返回本环境列表 """
        ro_user = UserProfile.objects.create_user(
            username="ro_bk", password="ro_password",
            email="ro_bk@test.com", role="readonlyuser")
        # 仅授权 default 环境
        UserEnv.objects.create(user=ro_user, env=self.env_default)
        self.client.cookies["jwtToken"] = jwt_encode_handler(
            jwt_payload_handler(ro_user))

        resp_forbidden = self.client.get(
            self.history_list_url, HTTP_X_ENV_ID=str(self.env_b.id))
        self.assertEqual(resp_forbidden.status_code, 403)
        self.assertEqual(resp_forbidden.json().get("message"),
                         "无该环境访问权限")

        resp_allowed = self.client.get(
            self.history_list_url, HTTP_X_ENV_ID=str(self.env_default.id))
        self.assertEqual(resp_allowed.status_code, 200)
        body = resp_allowed.json()
        self.assertEqual(body.get("code"), 0)
        results = body.get("data").get("results")
        self.assertEqual([r.get("id") for r in results],
                         [self.history_a.id])

    def test_backup_callback_patch_without_header_still_ok(self):
        """ 项12 收窄不伤回调：被管节点 PATCH 无 X-Env-Id / 无 cookie ->
            200 正常更新，记录 env 不变（豁免收窄为视图内回调分支处理）"""
        resp = self.client.patch(
            reverse("backupHistory-detail", args=[self.history_b.id]),
            data=json.dumps({"result": "0", "ip": "10.50.0.2"}),
            content_type="application/json; charset=utf-8")
        self.assertEqual(resp.status_code, 200)
        resp_json = resp.json()
        self.assertEqual(resp_json.get("code"), 0)
        self.history_b.refresh_from_db()
        self.assertEqual(self.history_b.result, BackupHistory.SUCCESS)
        self.assertEqual(self.history_b.env, self.env_b)


@pytest.mark.django_db
class InspectionCrossEnvTest(CrossEnvTestBase):
    """ inspection 模块收口（brief 14-15 项） """

    def setUp(self):
        super(InspectionCrossEnvTest, self).setUp()
        self.open_views(inspection_views.InspectionServiceView,
                        inspection_views.InspectionCrontabView)
        self.app_mysql = make_app("mysql", app_port="3306")
        self.service_a = make_service(
            self.app_mysql, "svc_mysql_a", "10.60.0.1", self.env_default)
        self.service_b = make_service(
            self.app_mysql, "svc_mysql_b", "10.60.0.2", self.env_b)
        self.crontab_url = reverse("crontab-list")
        self.inspection_services_url = "/api/inspection/services/"

    def test_inspection_service_list_filtered(self):
        """ 项15 InspectionServiceView：组件巡检可选服务按当前环境过滤，
            跨环境服务 id 不可选入 """
        resp_b = self.client.get(
            self.inspection_services_url,
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        self.assertEqual(
            [s.get("service__id") for s in resp_b.get("data")],
            [self.service_b.id])

        resp_default = self.client.get(
            self.inspection_services_url).json()
        self.assertEqual(resp_default.get("code"), 0)
        self.assertEqual(
            [s.get("service__id") for s in resp_default.get("data")],
            [self.service_a.id])

    def _crontab_payload(self, job_type):
        return {
            "crontab_detail": {"hour": "09", "minute": "41", "month": "*",
                               "day_of_week": "1", "day": "*"},
            "is_start_crontab": 0, "job_name": "深度分析",
            "job_type": job_type}

    def test_crontab_task_name_per_env(self):
        """ 项14 巡检定时任务名 per-env：任务名带环境 code，两环境同类型
            任务并存不冲突；更新链路（删除重建）同名一致 """
        from django_celery_beat.models import PeriodicTask

        # default 环境（pytest 注入）创建 host 巡检任务
        resp_default = self.post_json(
            self.crontab_url, self._crontab_payload(1)).json()
        self.assertEqual(resp_default.get("code"), 0)
        # B 环境创建 deep 巡检任务
        resp_b = self.post_json(
            self.crontab_url, self._crontab_payload(0),
            env_id=self.env_b.id).json()
        self.assertEqual(resp_b.get("code"), 0)

        # 两环境任务并存且各自携带环境 code 前缀（此前全局同名互斥）
        self.assertTrue(PeriodicTask.objects.filter(
            name="inspection_cron_task_default_host").exists())
        task_b = PeriodicTask.objects.filter(
            name="inspection_cron_task_staging_deep").first()
        self.assertIsNotNone(task_b)
        self.assertEqual(
            json.loads(task_b.kwargs).get("env"), self.env_b.id)

        # B 环境创建 host 巡检任务也不与 default 冲突
        resp_b2 = self.post_json(
            self.crontab_url, self._crontab_payload(1),
            env_id=self.env_b.id).json()
        self.assertEqual(resp_b2.get("code"), 0)
        self.assertTrue(PeriodicTask.objects.filter(
            name="inspection_cron_task_staging_host").exists())

    def test_crontab_update_recreates_same_env_scoped_name(self):
        """ 项14 更新链路：按 job_type 更新后定时任务仍为环境前缀命名，
            kwargs 环境为当前环境 """
        from django_celery_beat.models import PeriodicTask

        self.post_json(self.crontab_url, self._crontab_payload(0),
                       env_id=self.env_b.id)
        resp_upd = self.client.put(
            f"{self.crontab_url}0/",
            data=json.dumps(self._crontab_payload(0)),
            content_type="application/json; charset=utf-8",
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_upd.get("code"), 0)
        task = PeriodicTask.objects.filter(
            name="inspection_cron_task_staging_deep").first()
        self.assertIsNotNone(task)
        self.assertEqual(
            json.loads(task.kwargs).get("env"), self.env_b.id)

    def test_crontab_row_env_kept(self):
        """ 项14 配套：InspectionCrontab 行 env 与任务归属一致 """
        self.post_json(self.crontab_url, self._crontab_payload(0),
                       env_id=self.env_b.id)
        crontab_b = InspectionCrontab.objects.filter(
            job_type=0).first()
        self.assertIsNotNone(crontab_b)
        self.assertEqual(crontab_b.env, self.env_b)


# ---------------------------------------------------------------------------
# 迁移行为测试（brief 第 9 / 14 项的 data migration）
# ---------------------------------------------------------------------------

DEDUP_MIGRATION = "0035_self_healing_setting_env_unique"
RENAME_MIGRATION = "0036_inspection_cron_task_env_prefix"


@pytest.mark.django_db(transaction=True)
def test_migration_dedup_self_healing_setting_and_unique():
    """ 项9 迁移：同环境重复行保留首行（防御性去重）+ env 加唯一约束；
    去重函数前向幂等 """
    executor = MigrationExecutor(connection)
    executor.migrate([("db_models", "0034_multi_env_ten_fk")])
    old_apps = executor.loader.project_state(
        ("db_models", "0034_multi_env_ten_fk")).apps
    old_setting = old_apps.get_model("db_models", "SelfHealingSetting")
    old_env = old_apps.get_model("db_models", "Env")
    # 前序 transaction 用例的 flush 可能清掉了默认环境行，env_id=1 的
    # 存量数据需要它存在（FK 约束）
    if not old_env.objects.filter(id=1).exists():
        old_env.objects.create(id=1, name="default", code="default")
    env2 = old_env.objects.create(name="迁移环境", code="migr")
    keep = old_setting.objects.create(env_id=1, repair_instance=["redis"])
    old_setting.objects.create(env_id=1, repair_instance=["mysql"])
    old_setting.objects.create(env_id=env2.id)

    executor.loader.build_graph()
    executor.migrate([("db_models", DEDUP_MIGRATION)])

    from db_models.models import SelfHealingSetting as NewSetting
    assert NewSetting.objects.filter(env_id=1).count() == 1
    assert NewSetting.objects.filter(env_id=1).first().id == keep.id
    assert NewSetting.objects.filter(env_id=env2.id).count() == 1
    # 模型层唯一约束已生效
    field = NewSetting._meta.get_field("env")
    assert field.unique is True
    # 去重函数幂等
    migration = import_module("db_models.migrations." + DEDUP_MIGRATION)
    head_apps = executor.loader.project_state(
        ("db_models", DEDUP_MIGRATION)).apps
    migration.dedup_self_healing_setting(head_apps, None)
    assert NewSetting.objects.filter(env_id=1).count() == 1


@pytest.mark.django_db(transaction=True)
def test_migration_renames_inspection_cron_tasks():
    """ 项14 存量迁移：无前缀任务名按 kwargs 环境补 env code 前缀，
    kwargs 其余键无损；已带前缀 / 严格签名任务不动；函数幂等 """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    executor = MigrationExecutor(connection)
    executor.migrate([("db_models", "0034_multi_env_ten_fk")])
    old_apps = executor.loader.project_state(
        ("db_models", "0034_multi_env_ten_fk")).apps
    old_env = old_apps.get_model("db_models", "Env")
    # 前序 transaction 用例的 flush 可能清掉了默认环境行，补齐（默认
    # 环境任务名前缀按 default 解析依赖 env 1 存在与否的真实映射）
    if not old_env.objects.filter(id=1).exists():
        old_env.objects.create(id=1, name="default", code="default")
    env2 = old_env.objects.create(name="预发环境", code="staging")
    schedule = CrontabSchedule.objects.create()
    legacy_default = PeriodicTask.objects.create(
        name="inspection_cron_task_deep", crontab=schedule,
        task="inspection.tasks.inspection_crontab",
        kwargs=json.dumps({"job_type": 0, "job_name": "深度巡检", "env": 1}))
    legacy_b = PeriodicTask.objects.create(
        name="inspection_cron_task_host", crontab=schedule,
        task="inspection.tasks.inspection_crontab",
        kwargs=json.dumps({"job_type": 1, "job_name": "主机巡检",
                           "env": env2.id}))
    legacy_no_env = PeriodicTask.objects.create(
        name="inspection_cron_task_service", crontab=schedule,
        task="inspection.tasks.inspection_crontab",
        kwargs=json.dumps({"job_type": 2, "job_name": "组件巡检"}))
    strict_task = PeriodicTask.objects.create(
        name="self_health_cron_task_5", crontab=schedule,
        task="services.tasks.self_healing",
        kwargs=json.dumps({"task_id": 5}))

    executor.loader.build_graph()
    executor.migrate([("db_models", RENAME_MIGRATION)])

    legacy_default.refresh_from_db()
    assert legacy_default.name == "inspection_cron_task_default_deep"
    legacy_b.refresh_from_db()
    assert legacy_b.name == "inspection_cron_task_staging_host"
    legacy_no_env.refresh_from_db()
    assert legacy_no_env.name == "inspection_cron_task_default_service"
    strict_task.refresh_from_db()
    assert strict_task.name == "self_health_cron_task_5"
    # kwargs 除 name 外无损
    assert json.loads(legacy_default.kwargs) == {
        "job_type": 0, "job_name": "深度巡检", "env": 1}

    # 幂等：已带前缀的任务再跑不报错、不重复加前缀
    migration = import_module("db_models.migrations." + RENAME_MIGRATION)
    head_apps = executor.loader.project_state(
        ("db_models", RENAME_MIGRATION)).apps
    migration.rename_inspection_cron_tasks(head_apps, None)
    legacy_default.refresh_from_db()
    assert legacy_default.name == "inspection_cron_task_default_deep"
