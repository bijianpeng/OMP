# -*- coding: utf-8 -*-
"""
service_upgrade 模块环境上下文接入测试（多环境架构 Task 13）

覆盖：
1. 升级 / 回滚历史列表按当前环境过滤；跨环境详情（GET / PUT 重试共用
   get_object）走过滤 queryset -> 统一包 code=1
2. 发起升级：default 上下文升级 env_b 服务 -> 统一包 code=1 且不落记录；
   本环境发起 -> 成功且 UpgradeHistory 写入当前环境
3. 发起回滚：跨环境升级明细 -> code=1；本环境发起 -> RollbackHistory
   写入当前环境
4. 升级 / 回滚维护模式静默按 env.code 匹配（T11 审查遗留：告警 matcher
   env 的取值是 Env.code，name != code 的环境传 name 会得到无效静默）

测试基建说明：同 tests/test_backups/test_env.py——继承 BaseTest（非
AutoLoginTest），显式放开本文件涉及视图的认证与权限；涉及 operator
外键落库的发起操作使用 APIClient force_authenticate 注入真实用户。
"""
import json
from unittest import mock

import pytest

from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

from tests.base import BaseTest
from db_models.mixins import UpgradeStateChoices
from db_models.models import (
    Env, ApplicationHub, Service, UpgradeHistory, UpgradeDetail,
    RollbackHistory)
from service_upgrade import views as upgrade_views
from service_upgrade.tasks import upgrade_service, rollback_service


def make_app(app_name, app_version):
    """ 直接落库一个应用中心安装包 """
    return ApplicationHub.objects.create(
        app_name=app_name, app_version=app_version,
        app_type=ApplicationHub.APP_TYPE_COMPONENT,
        is_release=True, is_base_env=False,
        extend_fields={"base_env": False, "affinity": ""})


def make_service(app, instance_name, ip, env):
    """ 直接落库一个指定环境的服务实例 """
    return Service.objects.create(
        service_instance_name=instance_name,
        ip=ip,
        service_status=Service.SERVICE_STATUS_NORMAL,
        service=app,
        env=env,
    )


@pytest.mark.django_db
class ServiceUpgradeEnvContextTest(BaseTest):
    """ service_upgrade 模块环境上下文行为 """

    def setUp(self):
        super(ServiceUpgradeEnvContextTest, self).setUp()
        # 显式放开本文件涉及视图的认证与权限（说明同 backups 环境测试）
        for view_cls in (upgrade_views.UpgradeHistoryListAPIView,
                         upgrade_views.UpgradeHistoryDetailAPIView,
                         upgrade_views.DoUpgradeAPIView,
                         upgrade_views.RollbackHistoryListAPIView,
                         upgrade_views.RollbackHistoryDetailAPIView,
                         upgrade_views.DoRollbackAPIView):
            view_cls.authentication_classes = []
            view_cls.permission_classes = [AllowAny]
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")
        self.upgrade_list_url = "/api/upgrade/history"
        self.rollback_list_url = "/api/rollback/history"

    def test_upgrade_history_filtered(self):
        """ 升级 / 回滚历史：两环境各 1 条，列表按当前环境过滤；跨环境
            详情经统一闸门 404 -> 统一包 code=1，本环境详情正常 """
        upgrade_a = UpgradeHistory.objects.create(
            env=self.env_default, operator=self.default_user)
        upgrade_b = UpgradeHistory.objects.create(
            env=self.env_b, operator=self.default_user)
        rollback_a = RollbackHistory.objects.create(
            env=self.env_default, operator=self.default_user)
        rollback_b = RollbackHistory.objects.create(
            env=self.env_b, operator=self.default_user)

        # 升级历史列表：B 上下文仅见 B 记录；无标识（pytest 注入 default）
        # 仅见 default 记录
        resp_b = self.client.get(
            self.upgrade_list_url,
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_b.get("data").get("results")],
            [upgrade_b.id])
        resp_default = self.client.get(self.upgrade_list_url).json()
        self.assertEqual(resp_default.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_default.get("data").get("results")],
            [upgrade_a.id])

        # 回滚历史列表：同样按环境隔离
        resp_rb = self.client.get(
            self.rollback_list_url,
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_rb.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_rb.get("data").get("results")],
            [rollback_b.id])
        resp_rdefault = self.client.get(self.rollback_list_url).json()
        self.assertEqual(resp_rdefault.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_rdefault.get("data").get("results")],
            [rollback_a.id])

        # 跨环境详情：B 上下文访问 default 升级记录 -> 统一包 code=1
        resp_detail = self.client.get(
            f"{self.upgrade_list_url}/{upgrade_a.id}",
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_detail.get("code"), 1)
        self.assertIsNone(resp_detail.get("data"))
        # 跨环境回滚详情同理
        resp_rdetail = self.client.get(
            f"{self.rollback_list_url}/{rollback_a.id}",
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_rdetail.get("code"), 1)
        # 本环境详情正常
        resp_detail_ok = self.client.get(
            f"{self.upgrade_list_url}/{upgrade_b.id}",
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_detail_ok.get("code"), 0)

    def test_upgrade_cross_env_rejected(self):
        """ 发起升级：default 上下文升级 env_b 服务 -> 统一包 code=1 且
            不落记录；本环境发起 -> UpgradeHistory 写入当前环境；
            发起回滚：B 上下文回滚 default 明细 -> code=1，本环境发起 ->
            RollbackHistory 写入当前环境 """
        client = APIClient()
        client.force_authenticate(user=self.default_user)

        app_v1 = make_app("mysql", "1.0")
        app_v2 = make_app("mysql", "2.0")
        service_default = make_service(
            app_v1, "mysql-default", "10.10.0.1", self.env_default)
        service_b = make_service(
            app_v1, "mysql-b", "10.10.0.2", self.env_b)

        # 跨环境发起升级：default 上下文选择 env_b 服务 -> code=1，
        # 不创建升级记录
        with mock.patch("service_upgrade.views.upgrade_service"):
            resp_cross = client.post(
                "/api/upgrade/do-upgrade",
                data=json.dumps({"choices": [
                    {"service_id": service_b.id, "app_id": app_v2.id}]}),
                content_type="application/json",
                HTTP_X_ENV_ID=str(self.env_default.id)).json()
        self.assertEqual(resp_cross.get("code"), 1)
        self.assertIsNone(resp_cross.get("data"))
        self.assertEqual(UpgradeHistory.objects.count(), 0)

        # 本环境发起升级：成功且升级记录写入当前环境
        with mock.patch("service_upgrade.views.upgrade_service"):
            resp_ok = client.post(
                "/api/upgrade/do-upgrade",
                data=json.dumps({"choices": [
                    {"service_id": service_default.id,
                     "app_id": app_v2.id}]}),
                content_type="application/json",
                HTTP_X_ENV_ID=str(self.env_default.id)).json()
        self.assertEqual(resp_ok.get("code"), 0)
        history = UpgradeHistory.objects.first()
        self.assertIsNotNone(history)
        self.assertEqual(history.env, self.env_default)
        # 推进到终态，避免阻塞后续回滚发起的进行中校验
        UpgradeHistory.objects.update(
            upgrade_state=UpgradeStateChoices.UPGRADE_SUCCESS)

        # 构造两环境的可回滚升级明细（升级成功、未回滚）
        detail_default = UpgradeDetail.objects.create(
            history=UpgradeHistory.objects.create(
                env=self.env_default, operator=self.default_user,
                upgrade_state=UpgradeStateChoices.UPGRADE_SUCCESS),
            service=service_default,
            union_server=f"{service_default.ip}-mysql",
            upgrade_state=UpgradeStateChoices.UPGRADE_SUCCESS)
        detail_b = UpgradeDetail.objects.create(
            history=UpgradeHistory.objects.create(
                env=self.env_b, operator=self.default_user,
                upgrade_state=UpgradeStateChoices.UPGRADE_SUCCESS),
            service=service_b,
            union_server=f"{service_b.ip}-mysql",
            upgrade_state=UpgradeStateChoices.UPGRADE_SUCCESS)

        # 跨环境发起回滚：B 上下文回滚 default 环境明细 -> code=1，
        # 不创建回滚记录
        with mock.patch("service_upgrade.views.rollback_service"):
            resp_rb_cross = client.post(
                "/api/rollback/do-rollback",
                data=json.dumps({"choices": [detail_default.id]}),
                content_type="application/json",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_rb_cross.get("code"), 1)
        self.assertEqual(RollbackHistory.objects.count(), 0)

        # 本环境发起回滚：成功且回滚记录写入当前环境
        with mock.patch("service_upgrade.views.rollback_service"):
            resp_rb_ok = client.post(
                "/api/rollback/do-rollback",
                data=json.dumps({"choices": [detail_b.id]}),
                content_type="application/json",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_rb_ok.get("code"), 0)
        rollback_history = RollbackHistory.objects.first()
        self.assertIsNotNone(rollback_history)
        self.assertEqual(rollback_history.env, self.env_b)

    def test_maintain_mode_uses_env_code(self):
        """ 升级 / 回滚进入维护模式的静默按 env.code 匹配：name != code
            的环境（如"生产环境"/prod）传入的 matcher 值应为 code """
        env_prod = Env.objects.create(name="生产环境", code="prod")
        upgrade_h = UpgradeHistory.objects.create(
            env=env_prod, operator=self.default_user,
            pre_upgrade_state=UpgradeStateChoices.UPGRADE_SUCCESS)
        rollback_h = RollbackHistory.objects.create(
            env=env_prod, operator=self.default_user)

        with mock.patch(
                "service_upgrade.tasks.MainInstallHistory.objects") \
                as mock_main_install, \
                mock.patch("service_upgrade.tasks.computer_operation_sorted",
                           return_value=[]), \
                mock.patch("service_upgrade.tasks.update_product_version"), \
                mock.patch(
                    "service_upgrade.tasks.set_alert_maintain") \
                as mock_maintain:
            mock_main_install.order_by.return_value.first.return_value = \
                mock.Mock(operation_uuid="test-uuid")
            upgrade_service(upgrade_h.id)
        mock_maintain.assert_called_once_with("prod")

        with mock.patch(
                "service_upgrade.tasks.MainInstallHistory.objects") \
                as mock_main_install, \
                mock.patch("service_upgrade.tasks.computer_operation_sorted",
                           return_value=[]), \
                mock.patch("service_upgrade.tasks.update_product_version"), \
                mock.patch(
                    "service_upgrade.tasks.set_alert_maintain") \
                as mock_maintain:
            mock_main_install.order_by.return_value.first.return_value = \
                mock.Mock(operation_uuid="test-uuid")
            rollback_service(rollback_h.id)
        mock_maintain.assert_called_once_with("prod")
