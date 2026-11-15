# -*- coding: utf-8 -*-
"""
删除当前环境的两处防御回归测试（多环境 e2e 修复）

问题：DELETE /api/env/{id} 删除 X-Env-Id 指向的自身环境时，删除已生效
但响应 500——OperationLogMiddleware 在 process_response 阶段用内存中
的 request.env（指向已删行）写 OperateLog 触发 FK 违反。

防御 a：env_manage.views.EnvView.destroy 删除成功后清掉同 id 的
request.env，响应链不再携带失效环境实例；
防御 b：OperationLogMiddleware 写 OperateLog 包 try/except，审计写
失败仅记日志，不炸掉业务响应。

断言口径：平台统一异常处理器把视图异常包成 HTTP 200 + {"code": 1}；
防御 a 生效时删除成功为 HTTP 200 + code=0（OperateLog 落库且 env 为
NULL）；防御 b 单测直接调用 process_response，断言不抛异常。
"""
from unittest import mock

from django.db.utils import IntegrityError
from django.test import RequestFactory
from django.test import TestCase

from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response as DRFResponse
from rest_framework.reverse import reverse
from rest_framework_jwt.utils import jwt_encode_handler, jwt_payload_handler

from db_models.models import Env, OperateLog, UserProfile
from tests.base import BaseTest
from utils.middleware_handler import OperationLogMiddleware

ENV_LIST_URL = reverse("env-list")


class DeleteCurrentEnvTests(BaseTest):
    """ DELETE /api/env/{id}/ 删除 X-Env-Id 指向的当前环境 """

    def setUp(self):
        super(DeleteCurrentEnvTests, self).setUp()
        UserProfile.objects.filter(id=self.default_user.id).update(
            role="superuser")
        # 签发真实 jwtToken cookie：完整走认证 + 中间件链路，
        # OperationLogMiddleware 可解析到用户名并写 OperateLog
        self.client.cookies["jwtToken"] = jwt_encode_handler(
            jwt_payload_handler(self.default_user))

    def test_delete_current_env_response_not_500(self):
        """ 删除当前环境：响应 200 + code=0，环境已删，审计 env 为空 """
        env = Env.objects.create(name="当前环境", code="current-env")
        url = reverse("env-detail", args=[env.id])
        resp = self.client.delete(url, HTTP_X_ENV_ID=str(env.id))

        # 修复前：视图删除成功，process_response 写 OperateLog 触发
        # IntegrityError → 500；修复后：request.env 已清，正常返回
        assert resp.status_code == 200, resp.status_code
        resp_json = resp.json()
        assert resp_json["code"] == 0, resp_json
        assert not Env.objects.filter(id=env.id).exists()
        # 审计日志正常落库（防御 a 路径：env 置空而非依赖兜底 try/except）
        assert OperateLog.objects.filter(
            request_url=url, env__isnull=True).exists()

    def test_delete_other_env_keeps_request_env(self):
        """ X-Env-Id 指向别的环境时删除不受影响，审计 env 保持指向该环境 """
        env_other = Env.objects.create(name="待删环境", code="other-del")
        url = reverse("env-detail", args=[env_other.id])
        resp = self.client.delete(url, HTTP_X_ENV_ID="1")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert not Env.objects.filter(id=env_other.id).exists()
        assert OperateLog.objects.filter(
            request_url=url, env__id=1).exists()


class OperationLogMiddlewareStaleEnvTests(TestCase):
    """ 防御 b：request.env 失效时审计写失败不抛异常、不影响响应 """

    def setUp(self):
        self.user = UserProfile.objects.create_user(
            username="audit_user", password="pwd_audit",
            email="audit@test.com", role="superuser")

    def _build_request_response(self, env_instance):
        """
        构造与真实链路同构的 request/response（DELETE /api/env/）：
        真实 jwtToken cookie（可解析用户名，走 OperateLog 写库分支）+
        已绑定渲染器的 DRF Response（rendered_content 可读）
        """
        request = RequestFactory().delete(ENV_LIST_URL)
        request.COOKIES = {"jwtToken": jwt_encode_handler(
            jwt_payload_handler(self.user))}
        # 模拟视图删除后未清理的失效 request.env（指向已删行的内存实例）
        request.env = env_instance
        response = DRFResponse({"code": 0, "data": None, "message": "success"})
        response.accepted_renderer = JSONRenderer()
        response.accepted_media_type = "application/json"
        response.renderer_context = {}
        return request, response

    def test_save_failure_not_raise(self):
        """ OperateLog 写库失败（env 已删 FK 违反等）：不抛异常、原样返回响应 """
        env = Env.objects.create(name="已删环境", code="gone-env")
        request, response = self._build_request_response(env)

        # 生产（MySQL）上 env 指向已删行时 save 即刻抛 IntegrityError；
        # sqlite 测试库 FK 延迟校验，直接 mock save 抛错以确定性覆盖该分支
        with mock.patch.object(
                OperateLog, "save",
                side_effect=IntegrityError("FOREIGN KEY constraint failed")):
            # 修复前：异常从 process_response 冒泡（Django 转 500）
            result = OperationLogMiddleware().process_response(
                request, response)
        assert result is response

    def test_valid_env_still_logged(self):
        """ request.env 有效：审计日志正常落库（防御 b 不改变正常路径） """
        env = Env.objects.create(name="有效环境", code="ok-env")
        request, response = self._build_request_response(env)

        OperationLogMiddleware().process_response(request, response)
        assert OperateLog.objects.filter(
            request_url=ENV_LIST_URL, env__id=env.id).exists()
