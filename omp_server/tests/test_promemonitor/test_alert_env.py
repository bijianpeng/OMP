# -*- coding: utf-8 -*-
"""
告警接收链路与告警列表环境上下文测试（多环境架构 Task 10，spec §6.2/决策 #22）

覆盖：
1. 告警入库 env 三级解析：labels env 标签（值=Env.code）优先；
   无标签按 alert_host_ip 反查 Host.env；均失败归 default(id=1) 并 warning
2. 告警监控/日志跳转 URL 追加 var-env={Env.code}（spec 决策 #22——看板
   PromQL 为 env="$env" AND instance 双过滤，不带 var-env 则新环境看板空白）
3. Alert 列表接口按当前环境过滤（Review Focus #1）
4. WaitSelfHealing 待自愈记录同步写 env

测试基建说明：同 tests/test_promemonitor/test_env_views.py——以同名空 fixture
覆盖 conftest 的全局 mock（mock_requests/mock_models 会把 Host/Service/Alert
manager 替换为 MagicMock），环境解析断言需要真实 DB 查询；继承 BaseTest
（非 AutoLoginTest），涉及视图显式放开认证与权限。
"""
from unittest import mock

import pytest

from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse

from tests.base import BaseTest
from db_models.models import (
    Alert, ApplicationHub, Env, Host, Service, WaitSelfHealing)
from promemonitor import views as prom_views
from promemonitor.alert_util import AlertAnalysis, resolve_alert_env


@pytest.fixture(autouse=True)
def mock_requests():
    """覆盖 conftest 同名全局 mock：本文件需要真实行为"""
    yield


@pytest.fixture(autouse=True)
def mock_models():
    """覆盖 conftest 同名全局 mock：本文件需要真实 DB 查询"""
    yield


def make_host(ip, env):
    """ 落库一个指定环境的主机 """
    return Host.objects.create(
        instance_name=f"host-{ip.replace('.', '-')}",
        ip=ip, port=36000, username="root", password="encrypted",
        data_folder="/data", operate_system="CentOS", env=env)


def host_alert(ip, fingerprint, env_label=None):
    """ 构造一条主机类（nodeExporter）告警报文 """
    labels = {
        "alertname": "host cpu_used critical alert",
        "instance": ip,
        "job": "nodeExporter",
        "severity": "critical",
    }
    if env_label is not None:
        labels["env"] = env_label
    return {
        "status": "firing",
        "labels": labels,
        "annotations": {
            "consignee": "123456789@qq.com",
            "description": f"主机 {ip} CPU 使用率超过阈值",
            "summary": f"cpu_used (instance {ip})",
        },
        "startsAt": "2026-11-14T08:13:32.950510932Z",
        "endsAt": "0001-01-01T00:00:00Z",
        "fingerprint": fingerprint,
    }


@pytest.mark.django_db
class AlertEnvTest(BaseTest):
    """ 告警接收（webhook）与告警列表的环境上下文行为 """

    def setUp(self):
        super(AlertEnvTest, self).setUp()
        # 列表视图放开认证（环境上下文走 pytest 默认注入 / X-Env-Id header）
        for view_cls in (prom_views.ListAlertViewSet,):
            view_cls.authentication_classes = []
            view_cls.permission_classes = [AllowAny]
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")
        self.receive_url = reverse("receiveAlert-list")
        self.list_alert_url = reverse("listAlert-list")

    def _post_alerts(self, *alerts):
        return self.post(self.receive_url, {
            "receiver": "test", "status": "firing",
            "alerts": list(alerts)}).json()

    # ------------------------------------------------------------------
    # 告警入库 env 来源
    # ------------------------------------------------------------------
    def test_receive_alert_writes_env_from_label(self):
        """ labels env="default"（Env.code）→ 告警入库 env_id=1；
            待自愈记录同步写 env """
        make_host("10.20.1.1", self.env_default)
        resp = self._post_alerts(
            host_alert("10.20.1.1", "task10host000001", env_label="default"))
        self.assertEqual(resp.get("code"), 0)
        alert = Alert.objects.filter(fingerprint="task10host000001").first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.env_id, 1)
        wait = WaitSelfHealing.objects.filter(
            service_name="host", env=self.env_default).first()
        self.assertIsNotNone(wait)

    def test_receive_alert_env_fallback_by_ip(self):
        """ 无 env 标签 → 按告警主机 IP 反查 Host.env → 告警落 staging """
        make_host("10.20.2.2", self.env_b)
        resp = self._post_alerts(host_alert("10.20.2.2", "task10host000002"))
        self.assertEqual(resp.get("code"), 0)
        alert = Alert.objects.filter(fingerprint="task10host000002").first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.env_id, self.env_b.id)
        wait = WaitSelfHealing.objects.filter(
            service_name="host", env=self.env_b).first()
        self.assertIsNotNone(wait)

    def test_resolve_alert_env_fallback_default_with_warning(self):
        """ 标签与 IP 反查均失败 → 归 default(id=1) 并记录 warning """
        with mock.patch("promemonitor.alert_util.logger") as mock_logger:
            env = resolve_alert_env(
                {"env": "not-exists"}, "10.20.9.9")  # 无该主机
        self.assertIsNotNone(env)
        self.assertEqual(env.id, 1)
        mock_logger.warning.assert_called()

    # ------------------------------------------------------------------
    # 告警列表按环境过滤
    # ------------------------------------------------------------------
    def test_alert_list_filtered_by_env(self):
        """ 两环境各 1 条告警：staging 上下文仅见 staging 告警；
            无标识（pytest 注入 default）仅见 default 告警 """
        Alert.objects.create(
            alert_type="host", alert_host_ip="10.20.1.1",
            alert_level="critical", alert_describe="default 环境告警",
            alert_time="2026-11-14 08:00:00", env=self.env_default)
        Alert.objects.create(
            alert_type="host", alert_host_ip="10.20.2.2",
            alert_level="critical", alert_describe="staging 环境告警",
            alert_time="2026-11-14 08:00:00", env=self.env_b)

        resp_b = self.client.get(
            self.list_alert_url,
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        rows_b = resp_b.get("data", {}).get("results")
        self.assertEqual(
            sorted(row.get("alert_describe") for row in rows_b),
            ["staging 环境告警"])

        resp_default = self.client.get(self.list_alert_url).json()
        self.assertEqual(resp_default.get("code"), 0)
        rows_default = resp_default.get("data", {}).get("results")
        self.assertEqual(
            sorted(row.get("alert_describe") for row in rows_default),
            ["default 环境告警"])

    # ------------------------------------------------------------------
    # 跳转 URL 追加 var-env（spec 决策 #22）
    # ------------------------------------------------------------------
    def test_monitor_url_carries_var_env(self):
        """ staging 环境的服务告警 → 监控/日志跳转 URL 均含 var-env=staging """
        app = ApplicationHub.objects.create(
            app_name="mysql", app_version="5.7",
            app_type=ApplicationHub.APP_TYPE_COMPONENT, is_base_env=False)
        Service.objects.create(
            ip="10.20.3.3", service=app,
            service_instance_name="mysql-10-20-3-3",
            service_status=Service.SERVICE_STATUS_NORMAL,
            env=self.env_b)
        item = {
            "status": "firing",
            "labels": {
                "alertname": "app state",
                "app": "mysql",
                "env": "staging",
                "instance": "10.20.3.3",
                "job": "mysqlExporter",
                "severity": "critical",
            },
            "annotations": {
                "consignee": "123456789@qq.com",
                "description": "主机 10.20.3.3 中的 mysql 已经down掉超过一分钟.",
                "summary": "app state(instance 10.20.3.3)",
            },
            "startsAt": "2026-11-14T08:13:32.950510932Z",
            "fingerprint": "task10svc000003",
        }
        alert_info = AlertAnalysis(item)()
        self.assertTrue(alert_info)
        # 解析出的环境信息：env_code 供入库与跳转 URL 使用
        self.assertEqual(alert_info.get("env_code"), "staging")
        self.assertIn("var-env=staging", alert_info.get("monitor") or "")
        self.assertIn("var-env=staging", alert_info.get("monitor_log") or "")
