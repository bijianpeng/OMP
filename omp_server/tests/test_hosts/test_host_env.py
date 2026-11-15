# -*- coding: utf-8 -*-
"""
hosts 模块环境上下文接入测试（多环境架构 Task 7）

覆盖：
1. 主机列表按当前环境上下文过滤（两环境数据隔离）+ 列表输出 env_name
2. 单个创建自动继承请求环境（不接受客户端 env 值）
3. 批量导入落当前环境
4. 导入 IP 已存在（任意环境）时该行显式报错并提示归属环境（决策 #19，
   不再静默跳过），冲突行未入库、非冲突行照常入库

测试基建说明：
- 继承 BaseTest（非 AutoLoginTest）：本地 venv 下 login() 返回的 fake token
  签名不可校验，携带 cookie 的请求会被 JWT 认证拒绝（预存在的本地环境
  限制，与多环境改造无关）；匿名请求经 BaseTest 的
  IsAuthenticated→AllowAny 补丁放行。EnvContextMiddleware 对匿名用户
  （cookie 无法解析）放行环境授权，显式 X-Env-Id 仍走完整环境解析链，
  request.env 为 header 指定环境——环境授权链（UserEnv/superuser/403）
  已由 tests/test_env_manage/test_middleware.py 覆盖，本文件聚焦
  hosts 视图的过滤 / 继承 / 冲突语义。
"""
import json
from unittest import mock

import pytest

from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse

from tests.base import BaseTest
from tests.mixin import GrafanaMainPageResourceMixin
from db_models.models import Env, Host
from hosts import views as hosts_views
from hosts.tasks import insert_host_celery_task
from promemonitor.prometheus import Prometheus
from utils.plugin.crypto import AESCryptor
from utils.plugin.ssh import SSH


def make_host_payload(instance_name, ip):
    """ 构造创建 / 导入用的主机行数据 """
    return {
        "instance_name": instance_name,
        "ip": ip,
        "port": 36000,
        "username": "root",
        "password": "root_password",
        "data_folder": "/data",
        "operate_system": "CentOS",
        "use_ntpd": False,
    }


@pytest.mark.django_db
class HostEnvContextTest(BaseTest, GrafanaMainPageResourceMixin):
    """ hosts 模块环境上下文行为 """

    def setUp(self):
        super(HostEnvContextTest, self).setUp()
        # 显式放开本文件涉及视图的认证与权限，规避模块导入顺序差异：
        # hosts/views.py 的 PYTEST_CURRENT_TEST 放开块只在"测试执行期"首次
        # import 时生效，全量收集阶段（如先收集 test_hosts.py）import 时
        # 环境变量未设置而跳过，视图保留 IsAuthenticated 导致匿名请求 401。
        # 此处与该放开块的意图一致，直接作用到具体视图类，顺序无关。
        for view_cls in (hosts_views.HostListView,
                         hosts_views.HostDetailView,
                         hosts_views.HostBatchImportView):
            view_cls.authentication_classes = []
            view_cls.permission_classes = [AllowAny]
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")
        self.list_url = reverse("hosts-list")
        self.import_url = reverse("batchImport-list")
        self.get_grafana_main_pages()

    def tearDown(self):
        self.destroy_grafana_main_pages()
        super(HostEnvContextTest, self).tearDown()

    def _create_host(self, ip, env, instance_name):
        """ 直接落库一台指定环境的主机（密码加密存储，列表接口需解密） """
        return Host.objects.create(
            instance_name=instance_name,
            ip=ip, port=36000, username="root",
            password=AESCryptor().encode("password"),
            data_folder="/data", operate_system="CentOS", env=env)

    def test_list_filtered_by_env(self):
        """ 两环境各 1 主机：带 B 环境标识只见 B 主机；无标识（pytest 注入
            default）只见 default 主机；列表输出 env_name 而非裸 env id """
        host_a = self._create_host(
            "10.10.0.1", self.env_default, "host_env_a")
        host_b = self._create_host(
            "10.10.0.2", self.env_b, "host_env_b")

        with mock.patch.object(
                Prometheus, "get_host_info", side_effect=lambda x: x):
            # 显式 B 环境上下文：仅见 B 主机
            resp = self.client.get(
                self.list_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
            self.assertEqual(resp.get("code"), 0)
            results = resp.get("data").get("results")
            self.assertEqual(
                [host.get("ip") for host in results], [host_b.ip])
            # 列表 serializer 输出环境名称，不输出裸 env id
            self.assertEqual(results[0].get("env_name"), self.env_b.name)
            self.assertNotIn("env", results[0])

            # 未携带标识（pytest 注入 default 环境）：仅见 default 主机
            resp_default = self.client.get(self.list_url).json()
            self.assertEqual(resp_default.get("code"), 0)
            results_default = resp_default.get("data").get("results")
            self.assertEqual(
                [host.get("ip") for host in results_default], [host_a.ip])
            self.assertEqual(
                results_default[0].get("env_name"), self.env_default.name)

    @mock.patch.object(SSH, "check", return_value=(True, ""))
    @mock.patch.object(SSH, "is_sudo", return_value=(True, "is sudo"))
    @mock.patch.object(SSH, "cmd", return_value=(True, ""))
    @mock.patch.object(insert_host_celery_task, "delay", return_value=None)
    def test_create_inherits_request_env(
            self, celery_mock, cmd_mock, sudo_mock, ssh_mock):
        """ 创建主机自动继承请求环境；客户端显式传 env 值不被接受 """
        payload = make_host_payload("host_env_create", "10.20.0.1")
        # 恶意/冗余的客户端 env 值应被忽略，强制继承请求环境
        payload["env"] = self.env_default.id
        resp = self.client.post(
            self.list_url, data=json.dumps(payload),
            content_type="application/json; charset=utf-8",
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        host = Host.objects.filter(ip="10.20.0.1").first()
        self.assertIsNotNone(host)
        self.assertEqual(host.env, self.env_b)
        # 创建响应同样输出 env_name
        self.assertEqual(resp.get("data").get("env_name"), self.env_b.name)

    @mock.patch.object(insert_host_celery_task, "delay", return_value=None)
    def test_import_into_current_env(self, celery_mock):
        """ 批量导入主机落当前请求环境 """
        data = {"host_list": [
            make_host_payload("host_env_imp1", "10.30.0.1"),
            make_host_payload("host_env_imp2", "10.30.0.2"),
        ]}
        resp = self.client.post(
            self.import_url, data=json.dumps(data),
            content_type="application/json; charset=utf-8",
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("data"), "添加成功")
        for ip in ("10.30.0.1", "10.30.0.2"):
            host = Host.objects.filter(ip=ip).first()
            self.assertIsNotNone(host)
            self.assertEqual(host.env, self.env_b)

    @mock.patch.object(insert_host_celery_task, "delay", return_value=None)
    def test_import_ip_conflict_reports_env(self, celery_mock):
        """ 导入行 IP 已存在（属 default 环境）：该行报错并提示归属环境，
            冲突行未入库，非冲突行照常入库且落当前环境 B """
        conflict_ip = "10.40.0.1"
        self._create_host(
            conflict_ip, self.env_default, "host_env_conflict")
        data = {"host_list": [
            make_host_payload("host_env_conflict_row", conflict_ip),
            make_host_payload("host_env_fresh_row", "10.40.0.2"),
        ]}
        resp = self.client.post(
            self.import_url, data=json.dumps(data),
            content_type="application/json; charset=utf-8",
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp.get("code"), 0)
        # 冲突行明细：提示归属环境名称（决策 #19）
        error_rows = resp.get("data").get("error", [])
        self.assertEqual(len(error_rows), 1)
        self.assertEqual(error_rows[0].get("ip"), conflict_ip)
        self.assertEqual(
            error_rows[0].get("validate_error"),
            f"IP {conflict_ip} 已属于环境 {self.env_default.name}")
        # 冲突行未入库：该 IP 仍仅 1 台且属 default 环境
        self.assertEqual(Host.objects.filter(ip=conflict_ip).count(), 1)
        self.assertEqual(
            Host.objects.filter(ip=conflict_ip).first().env, self.env_default)
        # 非冲突行照常入库且落当前环境 B
        fresh_host = Host.objects.filter(ip="10.40.0.2").first()
        self.assertIsNotNone(fresh_host)
        self.assertEqual(fresh_host.env, self.env_b)
