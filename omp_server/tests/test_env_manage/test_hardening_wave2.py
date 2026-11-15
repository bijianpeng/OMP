# -*- coding: utf-8 -*-
"""
收口第二波（多环境架构 Task 7c，跨环境收口 4 项）

1. tool 发起执行 target 校验：目标主机枚举（target-object）与发起执行
   body 主机集合均按当前环境收口，跨环境主机不可见 / 不可执行
2. can-upgrade / can-rollback 可选列表按当前环境过滤（跨环境元数据
   枚举泄漏）
3. ExecutionRecord 信号透传 env：B 环境安装 / 升级产生的执行记录落在
   B 环境（此前恒为 default，B 环境执行记录不可见）
4. EnvContextMiddleware env_exempt 对 ViewSet 生效：DRF ViewSet 的
   as_view 包装只暴露 .cls 不暴露 .view_class（ViewSetMixin.as_view
   完全重写、不走 Django View.as_view 的 view_class 赋值），中间件
   读取逻辑需兼容两者

基建说明：项 1-3 复用 test_cross_env_hardening.CrossEnvTestBase（两环境
造数 + 视图放开认证权限）；项 4 参照 test_middleware 用临时
ROOT_URLCONF 探针视图（ViewSet 形态，经 as_view(actions) 挂载）。
"""
from unittest import mock

import pytest

from django.test import TestCase, override_settings
from django.urls import path

from rest_framework.mixins import ListModelMixin
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.test import APIClient
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework_jwt.utils import jwt_encode_handler, jwt_payload_handler

from tests.test_env_manage.test_cross_env_hardening import (
    CrossEnvTestBase, make_app, make_host, make_service)
from db_models.models import (
    Env, ExecutionRecord, Host, MainInstallHistory, ToolExecuteMainHistory,
    ToolInfo, UpgradeDetail, UpgradeHistory, UserEnv, UserProfile)
from db_models.mixins import UpgradeStateChoices
from tool import views as tool_views
from service_upgrade import views as upgrade_views
from promemonitor import views as promemonitor_views


def make_host_tool(name):
    """ 直接落库一个主机目标工具（无自定义参数，形态同 test_tool/test_env） """
    return ToolInfo.objects.create(
        name=name, kind=ToolInfo.KIND_CHECK,
        script_type=ToolInfo.SCRIPT_TYPE_SHELL, target_name="host",
        source_package_path=f"tool/tar/{name}.tar.gz",
        tool_folder_path=f"tool/folder/{name}",
        script_path=f"{name}.sh",
        send_package=[], template_filepath=[], obj_connection_args=[],
        script_args=[], output=ToolInfo.OUTPUT_TERMINAL,
        description="收口第二波测试工具")


def make_service_tool(name, app_name):
    """ 直接落库一个服务目标工具（目标为指定 app_name 的服务实例） """
    return ToolInfo.objects.create(
        name=name, kind=ToolInfo.KIND_CHECK,
        script_type=ToolInfo.SCRIPT_TYPE_SHELL, target_name=app_name,
        source_package_path=f"tool/tar/{name}.tar.gz",
        tool_folder_path=f"tool/folder/{name}",
        script_path=f"{name}.sh",
        send_package=[], template_filepath=[], obj_connection_args=[],
        script_args=[], output=ToolInfo.OUTPUT_TERMINAL,
        description="收口第二波服务目标测试工具")


@pytest.mark.django_db
class ToolTargetCrossEnvTest(CrossEnvTestBase):
    """ 项1：工具目标主机枚举 + 发起执行按当前环境收口 """

    def setUp(self):
        super(ToolTargetCrossEnvTest, self).setUp()
        self.open_views(
            tool_views.ToolTargetObjectAPIView,
            tool_views.ToolFormAnswerAPIView)
        self.tool = make_host_tool("wave2_check")
        self.host_a = make_host(
            "tool_host_a", "10.70.0.1", self.env_default,
            host_agent=str(Host.AGENT_RUNNING))
        self.host_b = make_host(
            "tool_host_b", "10.70.0.2", self.env_b,
            host_agent=str(Host.AGENT_RUNNING))
        self.target_url = reverse("target-object", args=[self.tool.id])
        self.answer_url = reverse("answer", args=[self.tool.id])

    def _answer_payload(self, host):
        return {"default_form": {
            "task_name": "task-wave2",
            "target_objs": [{"id": host.id, "ip": host.ip}],
            "runuser": "root", "timeout": 60}}

    def test_target_object_host_list_cross_env_filtered(self):
        """ 项1 枚举：B 上下文仅见 B 环境主机，default 上下文（pytest
            注入）仅见 default 主机 """
        resp_b = self.client.get(
            self.target_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        results_b = resp_b.get("data").get("results")
        self.assertEqual([h.get("id") for h in results_b], [self.host_b.id])

        resp_default = self.client.get(self.target_url).json()
        self.assertEqual(resp_default.get("code"), 0)
        results_a = resp_default.get("data").get("results")
        self.assertEqual([h.get("id") for h in results_a], [self.host_a.id])

    def test_execute_cross_env_host_rejected(self):
        """ 项1 发起执行：B 上下文提交 default 环境主机 -> 统一包 code=1，
            不落执行记录、任务不下发；本环境主机正常发起并写入当前环境 """
        with mock.patch("tool.serializers.exec_tools_main.delay") \
                as delay_mock:
            resp = self.post_json(
                self.answer_url, self._answer_payload(self.host_a),
                env_id=self.env_b.id).json()
        self.assertEqual(resp.get("code"), 1)
        delay_mock.assert_not_called()
        self.assertEqual(ToolExecuteMainHistory.objects.count(), 0)

        with mock.patch("tool.serializers.exec_tools_main.delay") \
                as delay_ok:
            resp_ok = self.post_json(
                self.answer_url, self._answer_payload(self.host_b),
                env_id=self.env_b.id).json()
        self.assertEqual(resp_ok.get("code"), 0)
        delay_ok.assert_called_once()
        history = ToolExecuteMainHistory.objects.first()
        self.assertIsNotNone(history)
        self.assertEqual(history.env, self.env_b)


@pytest.mark.django_db
class ToolServiceTargetCrossEnvTest(CrossEnvTestBase):
    """ 项1 追补：服务目标工具的枚举与发起执行按当前环境收口 """

    def setUp(self):
        super(ToolServiceTargetCrossEnvTest, self).setUp()
        self.open_views(
            tool_views.ToolTargetObjectAPIView,
            tool_views.ToolFormAnswerAPIView)
        self.app_mysql = make_app("mysql")
        self.tool = make_service_tool("wave2_svc_check", "mysql")
        self.service_a = make_service(
            self.app_mysql, "mysql-default", "10.72.0.1", self.env_default,
            service_port="[]")
        self.service_b = make_service(
            self.app_mysql, "mysql-b", "10.72.0.2", self.env_b,
            service_port="[]")
        self.target_url = reverse("target-object", args=[self.tool.id])
        self.answer_url = reverse("answer", args=[self.tool.id])

    def _answer_payload(self, service):
        return {"default_form": {
            "task_name": "task-wave2-svc",
            "target_objs": [{"id": service.id, "ip": service.ip,
                             "modifiable_kwargs": {}}],
            "runuser": "root", "timeout": 60}}

    def test_target_object_service_list_cross_env_filtered(self):
        """ 追补 枚举：B 上下文仅见 B 环境服务，default 上下文仅见
            default 服务（服务目标工具同 host 目标口径） """
        resp_b = self.client.get(
            self.target_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        results_b = resp_b.get("data").get("results")
        self.assertEqual([s.get("id") for s in results_b],
                         [self.service_b.id])

        resp_default = self.client.get(self.target_url).json()
        self.assertEqual(resp_default.get("code"), 0)
        results_a = resp_default.get("data").get("results")
        self.assertEqual([s.get("id") for s in results_a],
                         [self.service_a.id])

    def test_execute_cross_env_service_rejected(self):
        """ 追补 发起执行：B 上下文提交 default 环境服务 id -> 统一包
            code=1，不落执行记录、任务不下发；本环境服务正常发起并写入
            当前环境 """
        with mock.patch("tool.serializers.exec_tools_main.delay") \
                as delay_mock:
            resp = self.post_json(
                self.answer_url, self._answer_payload(self.service_a),
                env_id=self.env_b.id).json()
        self.assertEqual(resp.get("code"), 1)
        delay_mock.assert_not_called()
        self.assertEqual(ToolExecuteMainHistory.objects.count(), 0)

        with mock.patch("tool.serializers.exec_tools_main.delay") \
                as delay_ok:
            resp_ok = self.post_json(
                self.answer_url, self._answer_payload(self.service_b),
                env_id=self.env_b.id).json()
        self.assertEqual(resp_ok.get("code"), 0)
        delay_ok.assert_called_once()
        history = ToolExecuteMainHistory.objects.first()
        self.assertIsNotNone(history)
        self.assertEqual(history.env, self.env_b)


@pytest.mark.django_db
class UpgradeChoiceCrossEnvTest(CrossEnvTestBase):
    """ 项2：can-upgrade / can-rollback 可选列表按环境过滤 """

    def setUp(self):
        super(UpgradeChoiceCrossEnvTest, self).setUp()
        self.open_views(
            upgrade_views.UpgradeChoiceMaxVersionListAPIView,
            upgrade_views.UpgradeChoiceAllVersionListAPIView,
            upgrade_views.RollbackChoiceListAPIView)
        self.app_v1 = make_app("mysql", "1.0")
        self.app_v2 = make_app("mysql", "2.0")
        self.service_a = make_service(
            self.app_v1, "mysql-default", "10.71.0.1", self.env_default)
        self.service_b = make_service(
            self.app_v1, "mysql-b", "10.71.0.2", self.env_b)
        self.can_upgrade_url = "/api/upgrade/can-upgrade"
        self.can_rollback_url = "/api/rollback/can-rollback"

    def _can_upgrade_instances(self, env_id=None):
        kwargs = {}
        if env_id is not None:
            kwargs["HTTP_X_ENV_ID"] = str(env_id)
        resp = self.client.get(self.can_upgrade_url, **kwargs).json()
        self.assertEqual(resp.get("code"), 0)
        names = []
        for group in resp.get("data").get("results"):
            for child in group.get("children"):
                names.append(child.get("instance_name"))
        return names

    def _can_rollback_service_ids(self, env_id=None):
        kwargs = {}
        if env_id is not None:
            kwargs["HTTP_X_ENV_ID"] = str(env_id)
        resp = self.client.get(self.can_rollback_url, **kwargs).json()
        self.assertEqual(resp.get("code"), 0)
        service_ids = []
        for group in resp.get("data").get("results"):
            for child in group.get("children"):
                service_ids.append(child.get("service_id"))
        return service_ids

    def test_can_upgrade_list_cross_env_filtered(self):
        """ 项2 可升级列表：B 上下文仅见 B 环境服务（mysql-b），
            default 上下文仅见 default 服务（mysql-default）"""
        self.assertEqual(
            self._can_upgrade_instances(self.env_b.id), ["mysql-b"])
        self.assertEqual(
            self._can_upgrade_instances(), ["mysql-default"])

    def test_can_rollback_list_cross_env_filtered(self):
        """ 项2 可回滚列表：升级明细经所属升级记录过滤，B 上下文仅见
            B 环境服务的明细，default 上下文仅见 default 服务明细 """
        def make_rollbackable_detail(service, env):
            history = UpgradeHistory.objects.create(
                env=env, operator=self.default_user,
                upgrade_state=UpgradeStateChoices.UPGRADE_SUCCESS)
            return UpgradeDetail.objects.create(
                history=history, service=service,
                union_server=f"{service.ip}-mysql",
                target_app=self.app_v2, current_app=self.app_v1,
                upgrade_state=UpgradeStateChoices.UPGRADE_SUCCESS)

        make_rollbackable_detail(self.service_a, self.env_default)
        make_rollbackable_detail(self.service_b, self.env_b)

        self.assertEqual(
            self._can_rollback_service_ids(self.env_b.id),
            [self.service_b.id])
        self.assertEqual(
            self._can_rollback_service_ids(), [self.service_a.id])


@pytest.mark.django_db
class ExecutionRecordEnvSignalTest(CrossEnvTestBase):
    """ 项3：执行记录信号透传 env（B 环境记录不再落 default） """

    def test_install_signal_passes_env(self):
        """ MainInstallHistory 保存 -> 执行记录 env 跟随实例环境 """
        main_b = MainInstallHistory.objects.create(
            operation_uuid="wave2-main-b", install_status=2, env=self.env_b)
        record_b = ExecutionRecord.objects.filter(
            module="MainInstallHistory", module_id="wave2-main-b").first()
        self.assertIsNotNone(record_b)
        self.assertEqual(record_b.env, self.env_b)

    def test_upgrade_signal_passes_env(self):
        """ UpgradeHistory 保存 -> 执行记录 env 跟随实例环境 """
        upgrade_b = UpgradeHistory.objects.create(
            env=self.env_b, operator=self.default_user)
        record_b = ExecutionRecord.objects.filter(
            module="UpgradeHistory", module_id=str(upgrade_b.id)).first()
        self.assertIsNotNone(record_b)
        self.assertEqual(record_b.env, self.env_b)

    def test_default_env_record_and_get_or_create_scoped(self):
        """ default 环境实例仍落 default；状态推进重复保存不新建记录
            （get_or_create 查找键含 env） """
        main_a = MainInstallHistory.objects.create(
            operation_uuid="wave2-main-a", env=self.env_default)
        record_a = ExecutionRecord.objects.filter(
            module="MainInstallHistory", module_id="wave2-main-a").first()
        self.assertIsNotNone(record_a)
        self.assertEqual(record_a.env, self.env_default)

        main_a.install_status = 3
        main_a.save()
        self.assertEqual(
            ExecutionRecord.objects.filter(
                module="MainInstallHistory",
                module_id="wave2-main-a").count(), 1)


# ---------------------------------------------------------------------------
# 项4：env_exempt 对 ViewSet 生效（探针视图走 ViewSet 的 as_view 包装）
# ---------------------------------------------------------------------------

class ProbeViewSetBase(GenericViewSet, ListModelMixin):
    """ 探针 ViewSet 基类：经 as_view(actions) 挂载，回调只携带 .cls """

    authentication_classes = []
    permission_classes = [AllowAny]
    queryset = None

    def list(self, request, *args, **kwargs):
        env = getattr(request, "env", None)
        return Response({"env": env.id if env is not None else None})


class EnvExemptProbeViewSet(ProbeViewSetBase):
    """ 豁免探针：env_exempt=True（形态同 ReceiveAlertViewSet） """

    env_exempt = True


class PlainProbeViewSet(ProbeViewSetBase):
    """ 对照探针：无 env_exempt，其余一致 """


urlpatterns = [
    path("api/__wave2_exempt_vs__/",
         EnvExemptProbeViewSet.as_view({"get": "list"})),
    path("api/__wave2_plain_vs__/",
         PlainProbeViewSet.as_view({"get": "list"})),
]

EXEMPT_VS_URL = "/api/__wave2_exempt_vs__/"
PLAIN_VS_URL = "/api/__wave2_plain_vs__/"


@override_settings(ROOT_URLCONF="tests.test_env_manage.test_hardening_wave2")
class EnvExemptViewSetMiddlewareTest(TestCase):
    """ 项4：env_exempt 对 ViewSet（仅 .cls 包装）真正生效 """

    def setUp(self):
        self.client = APIClient()
        self.env_default = Env.objects.get(id=1)
        self.env_forbidden = Env.objects.create(name="隔离环境", code="isolated")
        self.user = UserProfile.objects.create_user(
            username="ro_wave2", password="ro_password",
            email="ro_wave2@test.com", role="readonlyuser")
        # ro_wave2 无任何 UserEnv 授权记录

    def _login_cookie(self):
        self.client.cookies["jwtToken"] = jwt_encode_handler(
            jwt_payload_handler(self.user))

    def test_viewset_callback_exposes_cls_not_view_class(self):
        """ 机制证据：ViewSet as_view 回调只带 .cls 不带 .view_class
            （APIView 两者皆有）——ReceiveAlertViewSet 的豁免标志在
            仅读 view_class 的旧实现下不可达 """
        vs_callback = EnvExemptProbeViewSet.as_view({"get": "list"})
        self.assertFalse(hasattr(vs_callback, "view_class"))
        self.assertIs(vs_callback.cls, EnvExemptProbeViewSet)

        class PlainAPIView(APIView):
            def get(self, request):
                return Response()

        api_callback = PlainAPIView.as_view()
        self.assertIs(api_callback.view_class, PlainAPIView)

        receive_callback = promemonitor_views.ReceiveAlertViewSet.as_view(
            {"post": "create"})
        self.assertFalse(hasattr(receive_callback, "view_class"))
        self.assertTrue(getattr(receive_callback.cls, "env_exempt", False))

    def test_env_exempt_viewset_with_header_and_unauthorized_not_403(self):
        """ 显式 X-Env-Id + 未授权用户：豁免放行（非 403）且解析出环境；
            同请求打到无豁免 ViewSet -> 403 对照 """
        self._login_cookie()

        resp = self.client.get(
            EXEMPT_VS_URL, HTTP_X_ENV_ID=str(self.env_forbidden.id))
        self.assertNotEqual(resp.status_code, 403)
        body = resp.json()
        self.assertEqual(body.get("code"), 0)
        self.assertEqual(body.get("data", {}).get("env"),
                         self.env_forbidden.id)

        resp_ctrl = self.client.get(
            PLAIN_VS_URL, HTTP_X_ENV_ID=str(self.env_forbidden.id))
        self.assertEqual(resp_ctrl.status_code, 403)
        self.assertEqual(resp_ctrl.json().get("message"), "无该环境访问权限")
