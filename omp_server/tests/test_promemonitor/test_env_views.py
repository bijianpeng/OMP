# -*- coding: utf-8 -*-
"""
promemonitor 配置类视图 + 仪表盘环境上下文接入测试（多环境架构 Task 9）

覆盖：
1. 阈值配置（主机/服务）按请求环境隔离读写，主机阈值联动
   update_host_threshold(env=env.code, env_id=env.id)
2. 告警推送（邮箱收件）配置按环境隔离（替换原 env_id=0 默认行为）
3. 全局维护模式 matcher 使用当前环境 code（含 list 过滤）
4. 仪表盘各维度（host/service/component/database）计数与明细按环境过滤
5. 指标规则（quota）创建写入请求环境，同表达式跨环境不判重
6. OperateLogMiddleware 记录请求环境

测试基建说明：
- 本文件以同名空 fixture 覆盖 tests/test_promemonitor/conftest.py 的全局
  mock（mock_requests/mock_models 会把 Host/Service/Alert/MonitorUrl 的
  manager 替换为 MagicMock），环境隔离断言需要真实 DB 查询。
- 继承 BaseTest（非 AutoLoginTest），本地 venv 限制说明见
  tests/test_hosts/test_host_env.py 模块注释。
"""
import json
from unittest import mock

import pytest

from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse

from tests.base import BaseTest
from db_models.models import (
    AlertRule, AlertSendWaySetting, ApplicationHub, EmailSMTPSetting,
    Env, Host, HostThreshold, Labels, Maintain, OperateLog, Service,
    ServiceThreshold,
)
from promemonitor import views as prom_views
from promemonitor.alertmanager import Alertmanager
from promemonitor.prometheus import Prometheus
from promemonitor.prometheus_utils import PrometheusUtils


@pytest.fixture(autouse=True)
def mock_requests():
    """覆盖 conftest 同名全局 mock：本文件需要真实行为"""
    yield


@pytest.fixture(autouse=True)
def mock_models():
    """覆盖 conftest 同名全局 mock：本文件需要真实 DB 查询"""
    yield


@pytest.mark.django_db
class PromemonitorEnvContextTest(BaseTest):
    """ promemonitor 配置类视图 + 仪表盘环境上下文行为 """

    def setUp(self):
        super(PromemonitorEnvContextTest, self).setUp()
        # 与 test_host_env.py 相同的认证放开方式，规避模块导入顺序差异
        for view_cls in (
                prom_views.GetSendAlertSettingView,
                prom_views.UpdateSendAlertSettingView,
                prom_views.HostThresholdView,
                prom_views.ServiceThresholdView,
                prom_views.CustomThresholdView,
                prom_views.MaintainViewSet,
                prom_views.InstrumentPanelView,
                prom_views.QuotaView):
            view_cls.authentication_classes = []
            view_cls.permission_classes = [AllowAny]
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")

    # ------------------------------------------------------------------
    # 阈值隔离
    # ------------------------------------------------------------------
    def test_threshold_isolated_per_env(self):
        """ env1（default）设阈值不影响 env2（staging）读写；主机阈值
            create 联动 update_host_threshold(env=code, env_id=id) """
        HostThreshold.objects.create(
            index_type="cpu_used", condition=">", condition_value="80%",
            alert_level="warning", env=self.env_default)
        ServiceThreshold.objects.create(
            index_type="service_cpu_used", condition=">", condition_value="70%",
            alert_level="warning", env=self.env_default)

        # default（pytest 注入）：可见 cpu_used=80% / service_cpu_used=70%
        resp_a = self.client.get(
            reverse("hostThreshold-list")).json()
        self.assertEqual(resp_a.get("code"), 0)
        self.assertEqual(len(resp_a.get("data").get("cpu_used")), 1)
        self.assertEqual(
            resp_a.get("data").get("cpu_used")[0].get("value"), "80%")
        resp_svc_a = self.client.get(
            reverse("serviceThreshold-list")).json()
        self.assertEqual(resp_svc_a.get("code"), 0)
        self.assertEqual(len(
            resp_svc_a.get("data").get("service_cpu_used")), 1)

        # staging：无主机阈值记录 → 原 env 校验语义（code=1）
        resp_b = self.client.get(
            reverse("hostThreshold-list"),
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 1)

        # staging 写入阈值：联动调用按新签名传当前环境 code / id
        with mock.patch.object(
                PrometheusUtils, "update_host_threshold",
                return_value=(True, "success")) as mock_uht, \
            mock.patch.object(
                PrometheusUtils, "update_node_data_rule",
                return_value=None):
            resp_create = self.client.post(
                reverse("hostThreshold-list"),
                data=json.dumps({"update_data": {"cpu_used": [
                    {"condition": ">", "value": "90%", "level": "warning"}]}}),
                content_type="application/json; charset=utf-8",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_create.get("code"), 0)
        mock_uht.assert_called_once_with(
            env=self.env_b.code, env_id=self.env_b.id)

        # staging 现为 90%，default 仍为 80%（互不影响）
        resp_b_after = self.client.get(
            reverse("hostThreshold-list"),
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b_after.get("code"), 0)
        self.assertEqual(
            resp_b_after.get("data").get("cpu_used")[0].get("value"), "90%")
        resp_a_after = self.client.get(
            reverse("hostThreshold-list")).json()
        self.assertEqual(
            resp_a_after.get("data").get("cpu_used")[0].get("value"), "80%")

        # 操作日志记录请求环境（OperateLogMiddleware 从 request.env 取）
        last_log = OperateLog.objects.order_by("-id").first()
        self.assertIsNotNone(last_log)
        self.assertEqual(last_log.env, self.env_b)

    # ------------------------------------------------------------------
    # 告警推送配置隔离
    # ------------------------------------------------------------------
    def test_send_way_setting_per_env(self):
        """ 邮箱收件配置按环境隔离：更新 staging 不影响 default；
            body 中冗余 env_id 被忽略（替换原 env_id=0 默认行为） """
        AlertSendWaySetting.objects.create(
            env=self.env_default, way_name="email",
            server_url="default@omp.com", used=True)
        EmailSMTPSetting.objects.create(
            email_host="smtp.test.com", email_port=25,
            email_host_user="omp@test.com", email_host_password="pwd")

        # staging 无配置 → v1.5 兼容分支回填 default 的配置内容
        resp_get_b = self.client.get(
            reverse("getSendAlertSetting-list"),
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_get_b.get("code"), 0)
        self.assertEqual(
            resp_get_b.get("data").get("email").get("server_url"),
            "default@omp.com")

        # 更新 staging 收件配置（body 携带恶意 env_id 应被忽略）
        with mock.patch.object(
                EmailSMTPSetting, "update_setting_config",
                return_value=(True, "http://alertmanager")):
            resp_post = self.client.post(
                reverse("updateSendAlertSetting-list"),
                data=json.dumps({
                    "used": True, "server_url": "staging@omp.com",
                    "env_id": self.env_default.id}),
                content_type="application/json; charset=utf-8",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_post.get("code"), 0)

        way_b = AlertSendWaySetting.objects.filter(
            env=self.env_b, way_name="email").first()
        self.assertIsNotNone(way_b)
        self.assertEqual(way_b.server_url, "staging@omp.com")
        self.assertTrue(way_b.used)
        # default 环境配置未被波及
        way_a = AlertSendWaySetting.objects.get(
            env=self.env_default, way_name="email")
        self.assertEqual(way_a.server_url, "default@omp.com")

        # default 环境查询仍返回自身配置
        resp_get_a = self.client.get(
            reverse("getSendAlertSetting-list")).json()
        self.assertEqual(
            resp_get_a.get("data").get("email").get("server_url"),
            "default@omp.com")

    # ------------------------------------------------------------------
    # 维护模式 matcher
    # ------------------------------------------------------------------
    def test_maintain_matcher_uses_env_code(self):
        """ 维护模式下发给当前环境 code（非客户端传入值/写死 default）；
            列表只返回当前环境的维护记录 """
        with mock.patch.object(
                Alertmanager, "add_setting",
                return_value="silence-staging") as mock_add:
            resp = self.client.post(
                reverse("globalMaintain-list"),
                data=json.dumps({"matcher_name": "env",
                                 "matcher_value": "client-evil-value"}),
                content_type="application/json; charset=utf-8",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp.get("code"), 0)
        mock_add.assert_called_once_with(value=self.env_b.code, name="env")
        self.assertTrue(Maintain.objects.filter(
            matcher_name="env", matcher_value=self.env_b.code,
            maintain_id="silence-staging").exists())

        # default 环境维护记录不应出现在 staging 列表
        Maintain.objects.create(
            matcher_name="env", matcher_value=self.env_default.code,
            maintain_id="silence-default")
        resp_list_b = self.client.get(
            reverse("globalMaintain-list"),
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_list_b.get("code"), 0)
        self.assertEqual(
            [item.get("matcher_value") for item in resp_list_b.get("data")],
            [self.env_b.code])
        resp_list_a = self.client.get(
            reverse("globalMaintain-list")).json()
        self.assertEqual(
            [item.get("matcher_value") for item in resp_list_a.get("data")],
            [self.env_default.code])

    # ------------------------------------------------------------------
    # 仪表盘过滤
    # ------------------------------------------------------------------
    def test_instrument_panel_filtered(self):
        """ 仪表盘各维度（host/service/component/database）计数与明细
            只统计当前环境 """
        Host.objects.create(
            instance_name="host_env_a1", ip="10.1.1.1", port=36000,
            username="root", password="encrypted", data_folder="/data",
            operate_system="CentOS", env=self.env_default)
        Host.objects.create(
            instance_name="host_env_a2", ip="10.1.1.2", port=36000,
            username="root", password="encrypted", data_folder="/data",
            operate_system="CentOS", env=self.env_default)
        Host.objects.create(
            instance_name="host_env_b1", ip="10.2.2.1", port=36000,
            username="root", password="encrypted", data_folder="/data",
            operate_system="CentOS", env=self.env_b)

        db_label = Labels.objects.create(
            label_type=Labels.LABEL_TYPE_COMPONENT, label_name="数据库")
        db_app = ApplicationHub.objects.create(
            app_name="mysql", app_version="5.7",
            app_type=ApplicationHub.APP_TYPE_COMPONENT, is_base_env=False)
        db_app.app_labels.add(db_label)
        svc_app = ApplicationHub.objects.create(
            app_name="ompweb", app_version="1.0",
            app_type=ApplicationHub.APP_TYPE_SERVICE, is_base_env=False)
        # 数据库组件服务属 staging，自研服务属 default
        Service.objects.create(
            ip="10.2.2.1", service=db_app,
            service_instance_name="mysql-10-2-2-1",
            service_status=Service.SERVICE_STATUS_NORMAL,
            service_controllers={"start": "start.sh"}, env=self.env_b)
        Service.objects.create(
            ip="10.1.1.1", service=svc_app,
            service_instance_name="ompweb-10-1-1-1",
            service_status=Service.SERVICE_STATUS_NORMAL,
            service_controllers={"start": "start.sh"}, env=self.env_default)

        url = reverse("instrumentPanel-list")
        with mock.patch.object(
                prom_views.InstrumentPanelView, "get_prometheus_alerts",
                return_value=(False, "Failed")), \
            mock.patch.object(
                Prometheus, "get_all_host_targets",
                return_value=(True, [])), \
            mock.patch.object(
                Prometheus, "get_all_service_targets",
                return_value=(True, [])):
            # default（pytest 注入）：2 主机 / 1 服务 / 0 数据库 / 0 组件
            resp_a = self.client.get(url).json()
            self.assertEqual(resp_a.get("code"), 0)
            data_a = resp_a.get("data")
            self.assertEqual(data_a.get("host").get("host_info_all_count"), 2)
            self.assertEqual(
                data_a.get("service").get("service_info_all_count"), 1)
            self.assertEqual(
                data_a.get("database").get("database_info_all_count"), 0)
            self.assertEqual(
                data_a.get("component").get("component_info_all_count"), 0)
            self.assertEqual(
                sorted(item.get("ip") for item in
                       data_a.get("host").get("host_info_list")),
                ["10.1.1.1", "10.1.1.2"])

            # staging：1 主机 / 0 服务 / 1 数据库（同时计入组件）
            resp_b = self.client.get(
                url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
            self.assertEqual(resp_b.get("code"), 0)
            data_b = resp_b.get("data")
            self.assertEqual(data_b.get("host").get("host_info_all_count"), 1)
            self.assertEqual(
                data_b.get("service").get("service_info_all_count"), 0)
            self.assertEqual(
                data_b.get("database").get("database_info_all_count"), 1)
            self.assertEqual(
                data_b.get("component").get("component_info_all_count"), 1)
            self.assertEqual(
                [item.get("ip") for item in
                 data_b.get("host").get("host_info_list")], ["10.2.2.1"])

    # ------------------------------------------------------------------
    # 指标规则
    # ------------------------------------------------------------------
    def test_quota_rule_created_with_request_env(self):
        """ 指标规则创建写入请求环境；同一表达式跨环境不判重；列表按
            环境过滤；body 冗余 env_id 被忽略 """
        with mock.patch.object(
                PrometheusUtils, "update_rule_file", return_value=True), \
            mock.patch.object(
                PrometheusUtils, "reload_prometheus", return_value=True):
            # quota_type=1（自定义 promql）
            resp_create = self.client.post(
                reverse("quota-list"),
                data=json.dumps({
                    "quota_type": 1, "expr": "up{env='staging'} == 0",
                    "threshold_value": 1, "compare_str": ">",
                    "severity": "critical", "alert": "staging down",
                    "service": "mysql", "for_time": "1m",
                    "env_id": self.env_default.id}),
                content_type="application/json; charset=utf-8",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
            self.assertEqual(resp_create.get("code"), 0)
            rule_b = AlertRule.objects.filter(
                expr="up{env='staging'} == 0").first()
            self.assertIsNotNone(rule_b)
            self.assertEqual(rule_b.env, self.env_b)
            self.assertEqual(
                rule_b.labels.get("job"), "mysqlExporter")

            # 同表达式 + 同级别在 default 环境可再建（判重按环境隔离）
            resp_create_a = self.client.post(
                reverse("quota-list"),
                data=json.dumps({
                    "quota_type": 1, "expr": "up{env='staging'} == 0",
                    "threshold_value": 1, "compare_str": ">",
                    "severity": "critical", "alert": "default down",
                    "service": "mysql", "for_time": "1m"}),
                content_type="application/json; charset=utf-8").json()
            self.assertEqual(resp_create_a.get("code"), 0)
            self.assertEqual(
                AlertRule.objects.filter(
                    expr="up{env='staging'} == 0").count(), 2)

            # quota_type=0（内置指标）：$env$ 用环境 code 替换
            resp_builtin = self.client.post(
                reverse("quota-list"),
                data=json.dumps({
                    "quota_type": 0, "threshold_value": 80,
                    "compare_str": ">=", "severity": "warning",
                    "builtins_quota": {
                        "name": "CPU使用率", "service": "node",
                        "description": "CPU使用率超$compare_str$$threshold_value%",
                        "expr": "cpu_usage{env='$env$'} > $threshold_value"}}),
                content_type="application/json; charset=utf-8",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
            self.assertEqual(resp_builtin.get("code"), 0)
            rule_builtin = AlertRule.objects.filter(
                name="CPU使用率").first()
            self.assertIsNotNone(rule_builtin)
            self.assertEqual(rule_builtin.env, self.env_b)
            self.assertIn(f"env='{self.env_b.code}'", rule_builtin.expr)

        # 列表按环境过滤：staging 2 条，default 1 条
        resp_list_b = self.client.get(
            reverse("quota-list"),
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_list_b.get("code"), 0)
        self.assertEqual(
            len(resp_list_b.get("data").get("results")), 2)
        resp_list_a = self.client.get(reverse("quota-list")).json()
        self.assertEqual(
            len(resp_list_a.get("data").get("results")), 1)
