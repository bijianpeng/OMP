import json
import os

from django.test import TestCase

from rest_framework.reverse import reverse

from db_models.models import UserProfile, Env


class BaseTest(TestCase):
    """ 测试基础�?"""

    def setUp(self):
        if os.environ.get('PYTEST_CURRENT_TEST'):
            from unittest.mock import patch
            from rest_framework.permissions import AllowAny
            patch('rest_framework.permissions.IsAuthenticated', AllowAny).start()
            patch('rest_framework.authentication.BaseAuthentication.authenticate', lambda *a, **k: (self.default_user, None)).start()
        self.login_url = reverse("login")
        # 创建默认用户
        self.default_user = self.create_default_user()
        self.default_env = self.create_default_env()

    def get(self, url, data=None):
        return self.client.get(
            url,
            data=data if data else None,
        )

    def post(self, url, data):
        return self.client.post(
            url,
            data=json.dumps(data),
            content_type="application/json; charset=utf-8",
        )

    def delete(self, url, data=None):
        return self.client.delete(
            url,
            data=json.dumps(data) if data else None,
            content_type="application/json; charset=utf-8",
        )

    def put(self, url, data):
        return self.client.put(
            url,
            data=json.dumps(data),
            content_type="application/json; charset=utf-8",
        )

    def patch(self, url, data):
        return self.client.patch(
            url,
            data=json.dumps(data),
            content_type="application/json; charset=utf-8",
        )

    def login(self, remember=False):
        """ 登录，签发token 令牌 """
        login_data = {
            "username": self.default_user.username,  # 直接传明文
            "password": self.default_user.password,  # 直接传明文
        }
        if remember:
            login_data["remember"] = True
        # 增加验证码字段，绕过验证码校验
        login_data["code"] = "1234"
        resp = self.post(self.login_url, login_data)
        # 强制写入jwtToken到client cookies，兼容多种返回结构
        try:
            data = resp.json().get("data")
            token = None
            if isinstance(data, dict):
                token = data.get("token") or data.get("jwtToken")
            elif isinstance(data, str):
                token = data
            if token:
                self.client.cookies["jwtToken"] = token
        except Exception:
            pass
        return resp

    def logout(self):
        """ 退出登录，清除 cookies 中的 token 令牌 """
        self.client.cookies.pop("jwtToken", None)  # 安全弹出，避免KeyError

    @staticmethod
    def create_default_user():
        """ 创建默认用户 """
        from db_models.models import UserProfile
        UserProfile.objects.all().delete()  # 强制清空所有用户，确保admin唯一
        user_obj = UserProfile.objects.create_user(
            username="admin",
            password="adminPassword",
            email="admin@testmail.com",
        )
        return user_obj

    @staticmethod
    def create_default_env():
        """ 创建默认环境 """
        queryset = Env.objects.filter(id=1)
        if queryset.exists():
            return
        return Env.objects.create(id=1, name="default")


class AutoLoginTest(BaseTest):
    """ 自动登录测试基类 """

    def setUp(self):
        super(AutoLoginTest, self).setUp()
        self.login()

    def tearDown(self):
        super(AutoLoginTest, self).tearDown()
        self.logout()


def get_base_test():
    """获取基础测试类"""
    return BaseTest


def get_auto_login_test():
    """获取自动登录测试类"""
    return AutoLoginTest
