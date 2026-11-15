# -*- coding: utf-8 -*-
"""
EnvContextMiddleware + get_request_env 单元测试（多环境架构 Task 4）

探针视图说明：资源类视图接入 get_request_env 属后续任务（设计 §10），
本任务用测试文件内定义的探针视图（临时 ROOT_URLCONF 挂载）验证中间件
全链路行为，不依赖任何业务视图改造。

关于断言口径：平台统一异常处理器（utils/exception_handler.py）会把视图抛出的
所有异常包成 HTTP 200 + {"code": 1, "message": ...}（与前端 omp-response.ts
识别的「未认证即 code=1」同一约定），因此"缺少环境上下文 400"在响应包上
表现为 code=1；中间件层的授权拒绝按 controller ruling 以真实 HTTP 403 +
统一包格式返回。
"""
import os

import pytest

from django.test import TestCase, override_settings
from django.urls import path

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIClient
from rest_framework.views import APIView
from rest_framework_jwt.utils import jwt_encode_handler, jwt_payload_handler

from db_models.models import Env, UserEnv, UserProfile
from utils.middleware_handler import get_request_env


class ProbeBaseView(APIView):
    """ 探针基类：显式关闭认证与权限，聚焦中间件行为本身 """

    authentication_classes = []
    permission_classes = [AllowAny]


class EnvProbeView(ProbeBaseView):
    """ 探针视图：模拟资源类接口（视图层 required 环境上下文） """

    def get(self, request, *args, **kwargs):
        env = get_request_env(request)
        return Response({"env": env.id})


class EnvExemptProbeView(ProbeBaseView):
    """ 探针视图：env_exempt 豁免授权校验，不要求环境上下文，回显 request.env """

    env_exempt = True

    def get(self, request, *args, **kwargs):
        env = getattr(request, "env", None)
        return Response({"env": env.id if env is not None else None})


urlpatterns = [
    path("api/__env_probe__/", EnvProbeView.as_view()),
    path("api/__env_exempt_probe__/", EnvExemptProbeView.as_view()),
]

PROBE_URL = "/api/__env_probe__/"
EXEMPT_PROBE_URL = "/api/__env_exempt_probe__/"


@override_settings(ROOT_URLCONF="tests.test_env_manage.test_middleware")
class EnvContextMiddlewareTests(TestCase):
    """ EnvContextMiddleware 解析 / 授权 / pytest 注入 / 豁免行为 """

    def setUp(self):
        self.client = APIClient()
        self.env_default = Env.objects.get(id=1)
        self.env_authorized = Env.objects.create(
            name="预发环境", code="staging")
        self.env_forbidden = Env.objects.create(
            name="隔离环境", code="isolated")
        self.user = UserProfile.objects.create_user(
            username="ro_env", password="ro_password",
            email="ro_env@test.com", role="readonlyuser")
        # ro_env 仅被授权 staging 环境
        UserEnv.objects.create(user=self.user, env=self.env_authorized)

    def _login_cookie(self):
        """ 为 ro_env 签发真实 JWT 写入 client cookie（中间件按 cookie 解码用户） """
        payload = jwt_payload_handler(self.user)
        self.client.cookies["jwtToken"] = jwt_encode_handler(payload)

    def _auth_header(self):
        """ 为 ro_env 签发真实 JWT，按 DRF JWT 口径构造 Authorization header """
        payload = jwt_payload_handler(self.user)
        return "JWT {}".format(jwt_encode_handler(payload))

    @staticmethod
    def _non_pytest():
        """ 脱离 PYTEST_CURRENT_TEST 的上下文管理器（模拟非测试环境） """
        ctx = pytest.MonkeyPatch.context()
        return ctx

    def test_no_header_returns_400(self):
        """ 非 pytest 环境、未携带环境标识：视图层 get_request_env 抛
        ValidationError，统一异常处理器输出缺少环境上下文错误包 """
        with self._non_pytest() as mp:
            mp.delenv("PYTEST_CURRENT_TEST", raising=False)
            resp = self.client.get(PROBE_URL)
        # 平台统一包：语义 400 以 HTTP 200 + code=1 表达
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("code"), 1)
        self.assertEqual(body.get("message"), "缺少环境上下文，请选择环境")

    def test_invalid_env_id_403(self):
        """ X-Env-Id 指向不存在的环境 / 非 int：中间件 403 环境不存在 """
        with self._non_pytest() as mp:
            mp.delenv("PYTEST_CURRENT_TEST", raising=False)
            resp = self.client.get(PROBE_URL, HTTP_X_ENV_ID="999")
            resp_bad = self.client.get(PROBE_URL, HTTP_X_ENV_ID="abc")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json(), {
            "code": 1, "data": None, "message": "环境不存在"})
        self.assertEqual(resp_bad.status_code, 403)
        self.assertEqual(resp_bad.json().get("message"), "环境不存在")

    def test_unauthorized_env_403(self):
        """ 用户存在但未授权目标环境：403 无该环境访问权限 """
        self._login_cookie()
        with self._non_pytest() as mp:
            mp.delenv("PYTEST_CURRENT_TEST", raising=False)
            resp = self.client.get(
                PROBE_URL, HTTP_X_ENV_ID=str(self.env_forbidden.id))
        self.assertEqual(resp.status_code, 403)
        body = resp.json()
        self.assertEqual(body.get("code"), 1)
        self.assertEqual(body.get("message"), "无该环境访问权限")

    def test_authorized_env_passes(self):
        """ 用户已授权目标环境：非 403，request.env 为所选环境 """
        self._login_cookie()
        with self._non_pytest() as mp:
            mp.delenv("PYTEST_CURRENT_TEST", raising=False)
            resp = self.client.get(
                PROBE_URL, HTTP_X_ENV_ID=str(self.env_authorized.id))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("code"), 0)
        self.assertEqual(body.get("data", {}).get("env"),
                         self.env_authorized.id)

    def test_auth_header_unauthorized_env_403(self):
        """ 必修项 4（红线）：token 走 Authorization header（无 cookie）+
            未授权环境 → 403；中间件 token 提取需对齐 DRF，header 携带
            token 的请求不得绕过环境授权 """
        with self._non_pytest() as mp:
            mp.delenv("PYTEST_CURRENT_TEST", raising=False)
            resp = self.client.get(
                PROBE_URL, HTTP_X_ENV_ID=str(self.env_forbidden.id),
                HTTP_AUTHORIZATION=self._auth_header())
        self.assertEqual(resp.status_code, 403)
        body = resp.json()
        self.assertEqual(body.get("code"), 1)
        self.assertEqual(body.get("message"), "无该环境访问权限")

    def test_auth_header_drf_variant_prefixes_unauthorized_403(self):
        """ 必修项 4 复审补强：DRF get_jwt_value 口径（split 任意空白 +
            前缀小写比较）能认证的 header 形态——小写 jwt 前缀与 tab 分隔
            ——同样不得绕过环境授权（未授权环境 → 403） """
        token = self._auth_header().split(" ", 1)[1]
        with self._non_pytest() as mp:
            mp.delenv("PYTEST_CURRENT_TEST", raising=False)
            # 小写前缀：Authorization: jwt <token>
            resp_lower = self.client.get(
                PROBE_URL, HTTP_X_ENV_ID=str(self.env_forbidden.id),
                HTTP_AUTHORIZATION="jwt {}".format(token))
            # tab 分隔：Authorization: JWT\t<token>
            resp_tab = self.client.get(
                PROBE_URL, HTTP_X_ENV_ID=str(self.env_forbidden.id),
                HTTP_AUTHORIZATION="JWT\t{}".format(token))
        for resp in (resp_lower, resp_tab):
            self.assertEqual(resp.status_code, 403)
            body = resp.json()
            self.assertEqual(body.get("code"), 1)
            self.assertEqual(body.get("message"), "无该环境访问权限")

    def test_auth_header_drf_variant_prefixes_authorized_passes(self):
        """ 必修项 4 复审补强：DRF 变体 header 形态 + 已授权环境 → 放行，
            request.env 正确解析 """
        token = self._auth_header().split(" ", 1)[1]
        with self._non_pytest() as mp:
            mp.delenv("PYTEST_CURRENT_TEST", raising=False)
            resp_lower = self.client.get(
                PROBE_URL, HTTP_X_ENV_ID=str(self.env_authorized.id),
                HTTP_AUTHORIZATION="jwt {}".format(token))
            resp_tab = self.client.get(
                PROBE_URL, HTTP_X_ENV_ID=str(self.env_authorized.id),
                HTTP_AUTHORIZATION="JWT\t{}".format(token))
        for resp in (resp_lower, resp_tab):
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body.get("code"), 0)
            self.assertEqual(body.get("data", {}).get("env"),
                             self.env_authorized.id)

    def test_auth_header_authorized_env_passes(self):
        """ 必修项 4：token 走 Authorization header + 已授权环境 → 放行，
            request.env 正确解析（cookie 兜底行为不变） """
        with self._non_pytest() as mp:
            mp.delenv("PYTEST_CURRENT_TEST", raising=False)
            resp = self.client.get(
                PROBE_URL, HTTP_X_ENV_ID=str(self.env_authorized.id),
                HTTP_AUTHORIZATION=self._auth_header())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body.get("code"), 0)
        self.assertEqual(body.get("data", {}).get("env"),
                         self.env_authorized.id)

    def test_pytest_injects_default(self):
        """ pytest 环境、未显式携带标识：自动注入 default 环境（id=1）；
        显式 header 优先，不被注入覆盖 """
        self.assertTrue(os.environ.get("PYTEST_CURRENT_TEST"))
        resp = self.client.get(PROBE_URL)
        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body.get("code"), 0)
        self.assertEqual(body.get("data", {}).get("env"), 1)

        # 显式 header 时仍走完整解析链，request.env 为 header 指定环境
        resp2 = self.client.get(
            PROBE_URL, HTTP_X_ENV_ID=str(self.env_authorized.id))
        body2 = resp2.json()
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(body2.get("code"), 0)
        self.assertEqual(body2.get("data", {}).get("env"),
                         self.env_authorized.id)

    def test_env_exempt_view_skips_auth(self):
        """ 视图类 env_exempt=True：跳过授权校验 """
        with self._non_pytest() as mp:
            mp.delenv("PYTEST_CURRENT_TEST", raising=False)
            # 1) 无 header 非 pytest：中间件放行（非 403/400），request.env 为空
            resp = self.client.get(EXEMPT_PROBE_URL)
            # 2) 未授权环境 header：豁免用户授权校验 → 仍放行并解析出该环境
            self._login_cookie()
            resp2 = self.client.get(
                EXEMPT_PROBE_URL, HTTP_X_ENV_ID=str(self.env_forbidden.id))
            # 对照组：同样请求打到非豁免探针 → 403，证明豁免确实生效
            resp3 = self.client.get(
                PROBE_URL, HTTP_X_ENV_ID=str(self.env_forbidden.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("data", {}).get("env"), None)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(
            resp2.json().get("data", {}).get("env"), self.env_forbidden.id)
        self.assertEqual(resp3.status_code, 403)
