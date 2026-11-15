# -*- coding: utf-8 -*-
"""
env_manage EnvView 接口测试（多环境架构 Task 5）

断言口径说明（同本目录 test_middleware.py）：平台统一异常处理器
（utils/exception_handler.py）把视图抛出的所有异常包成 HTTP 200 +
{"code": 1, "message": ...}，因此 brief 中的「400 拒绝」在响应包上
表现为 code=1，本文件按该口径断言；中间件层拒绝按真实 HTTP 403 +
统一包格式返回。

认证说明：不走 AutoLoginTest（其 pytest 分支写入的假 token 会被
JSONWebTokenAuthentication 真实解码失败），改用 jwt_encode_handler
签发真实 jwtToken cookie，完整走认证/中间件链路；仅视图层 superuser
兜底校验的分支用 BaseTest 同款 authenticate patch 直接构造
request.user（此时不携带 cookie，中间件解析不到用户而放行）。
"""
import hashlib
import json
from unittest.mock import patch

from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework.reverse import reverse
from rest_framework_jwt.utils import jwt_encode_handler, jwt_payload_handler

from db_models.models import (
    AlertRule, AlertSendWaySetting, BackupSetting, DeploymentPlan, Env, Host,
    HostThreshold, MainInstallHistory, ModuleSendEmailSetting, OperateLog,
    SelfHealingSetting, Service, ServiceCustomThreshold, ServiceThreshold,
    UserEnv, UserProfile)
from tests.base import BaseTest

ENV_LIST_URL = reverse("env-list")
CONFIG_COUNT_TABLES = (
    AlertRule, HostThreshold, ServiceThreshold, ServiceCustomThreshold,
    ModuleSendEmailSetting, AlertSendWaySetting, SelfHealingSetting)


class EnvViewTestBase(BaseTest):
    """ EnvView 测试基类：默认用户提升为 superuser 并签发真实 JWT """

    def setUp(self):
        super(EnvViewTestBase, self).setUp()
        UserProfile.objects.filter(id=self.default_user.id).update(
            role="superuser")
        self.auth_as(self.default_user)

    def auth_as(self, user):
        """ 以指定用户身份签发真实 jwtToken cookie """
        self.client.cookies["jwtToken"] = jwt_encode_handler(
            jwt_payload_handler(user))

    @staticmethod
    def config_counts(env_id):
        """ 七张环境级配置表在指定环境的行数快照（顺序固定便于比对） """
        return tuple(
            model.objects.filter(env_id=env_id).count()
            for model in CONFIG_COUNT_TABLES)

    @staticmethod
    def seed_all_config_tables(env_id):
        """ 给指定环境各配置表播种一行，保证复制比对覆盖全部七表 """
        AlertRule.objects.create(
            env_id=env_id, expr="up==0", severity="critical", name="up",
            threshold_value=0, compare_str="==", for_time="60s",
            alert="标题", service="node", hash_data="seed-hash")
        HostThreshold.objects.create(
            env_id=env_id, index_type="cpu_used", condition=">=",
            condition_value="80%", alert_level="warning")
        ServiceThreshold.objects.create(
            env_id=env_id, index_type="service_active", condition="==",
            condition_value="0", alert_level="critical")
        ServiceCustomThreshold.objects.create(
            env_id=env_id, service_name="kafka", index_type="lag",
            condition=">=", condition_value="1000", alert_level="warning")
        ModuleSendEmailSetting.objects.create(
            env_id=env_id, module="BackupSetting", send_email=True,
            to_users="a@test.com")
        AlertSendWaySetting.objects.create(
            env_id=env_id, way_name="email", used=True,
            server_url="a@test.com")
        SelfHealingSetting.objects.create(
            env_id=env_id, used=True, max_healing_count=5, fresh_rate=10)


class TestEnvCreate(EnvViewTestBase):
    """ POST /api/env/ 创建环境与配置复制 """

    def test_create_env_with_default_copy(self):
        """ config_source=1：新环境行存在，七表行数一致，hash 不冲突且互不影响 """
        self.seed_all_config_tables(1)
        source_counts = self.config_counts(1)

        resp = self.post(ENV_LIST_URL, {
            "name": "预发环境", "code": "staging",
            "description": "预发", "config_source": 1})
        resp_json = resp.json()
        assert resp_json["code"] == 0, resp_json

        new_env = Env.objects.get(code="staging")
        # 七表行数与来源环境一致
        assert self.config_counts(new_env.id) == source_counts
        # 新行 pk 与来源行不同（快照复制非引用）
        src_rule = AlertRule.objects.get(env_id=1, expr="up==0")
        dst_rule = AlertRule.objects.get(env_id=new_env.id, expr="up==0")
        assert src_rule.id != dst_rule.id
        # hash 按目标环境重算：与来源不同、可按公式复算
        assert dst_rule.hash_data != src_rule.hash_data
        assert dst_rule.hash_data == hashlib.md5(
            f"{new_env.id}:up==0:up:critical".encode()).hexdigest()
        # 复制为快照：修改新环境行不影响来源环境
        dst_rule.threshold_value = 100
        dst_rule.save(update_fields=["threshold_value"])
        src_rule.refresh_from_db()
        assert src_rule.threshold_value == 0

    def test_create_env_blank(self):
        """ config_source=None：新环境配置表 0 行；操作审计登记为新增 """
        self.seed_all_config_tables(1)
        resp = self.post(ENV_LIST_URL, {
            "name": "空环境", "code": "empty"})
        assert resp.json()["code"] == 0
        env = Env.objects.get(code="empty")
        assert self.config_counts(env.id) == (0,) * 7
        # INTERFACE_KINDS 登记 /api/env/ POST -> 新增（审计链路）
        operate_log = OperateLog.objects.filter(
            request_url=ENV_LIST_URL).order_by("-id").first()
        assert operate_log is not None
        assert operate_log.request_method == "新增"
        assert operate_log.description == "创建环境"

    def test_invalid_code_rejected(self):
        """ code 不合法（中文/数字开头/含空格）一律拒绝且不落库 """
        before = Env.objects.count()
        for bad_code in ("测试环境", "1a", "a b"):
            resp = self.post(ENV_LIST_URL, {"name": "x", "code": bad_code})
            resp_json = resp.json()
            assert resp_json["code"] == 1, (bad_code, resp_json)
        assert Env.objects.count() == before

    def test_duplicate_code_rejected(self):
        """ code 与 default 环境重复：拒绝 """
        resp = self.post(ENV_LIST_URL, {"name": "x", "code": "default"})
        assert resp.json()["code"] == 1


class TestEnvUpdate(EnvViewTestBase):
    """ PATCH /api/env/{id}/ 修改环境 """

    def test_code_immutable(self):
        """ PATCH 改 code：值不变，name 可改 """
        env = Env.objects.create(name="原名", code="tcode")
        resp = self.patch(
            reverse("env-detail", args=[env.id]),
            {"code": "hacked", "name": "改名", "description": "描述"})
        assert resp.json()["code"] == 0
        env.refresh_from_db()
        assert env.code == "tcode"
        assert env.name == "改名"
        assert env.description == "描述"


class TestEnvDelete(EnvViewTestBase):
    """ DELETE /api/env/{id}/ 删除保护与级联清理 """

    def test_delete_default_rejected(self):
        """ id=1 默认环境不可删除 """
        resp = self.delete(reverse("env-detail", args=[1]))
        resp_json = resp.json()
        assert resp_json["code"] == 1
        assert "默认环境" in resp_json["message"]
        assert Env.objects.filter(id=1).exists()

    def test_delete_env_with_hosts_rejected(self):
        """ 存在主机/服务关联：拒绝并附计数 """
        env = Env.objects.create(name="带资源", code="with-host")
        Host.objects.create(
            instance_name="host-1", ip="10.0.0.1", username="root",
            password="x", operate_system="centos", env=env)
        resp = self.delete(reverse("env-detail", args=[env.id]))
        resp_json = resp.json()
        assert resp_json["code"] == 1
        assert "主机" in resp_json["message"]
        assert "1" in resp_json["message"]
        assert Env.objects.filter(id=env.id).exists()

    def test_delete_env_with_service_rejected(self):
        """ 存在服务关联：拒绝并附计数 """
        env = Env.objects.create(name="带服务", code="with-service")
        Service.objects.create(
            ip="10.0.0.1", service_instance_name="kafka-1", env=env)
        resp = self.delete(reverse("env-detail", args=[env.id]))
        resp_json = resp.json()
        assert resp_json["code"] == 1
        assert "服务" in resp_json["message"]
        assert Env.objects.filter(id=env.id).exists()

    def test_delete_empty_env_cascades_config(self):
        """ 删空环境：配置行级联清理、安装历史保留(env=NULL)、beat 任务注销 """
        env = Env.objects.create(name="待删", code="to-del")
        self.seed_all_config_tables(env.id)
        # 进行中的安装任务阻止删除
        history = MainInstallHistory.objects.create(
            operation_uuid="uuid-del", install_log="log",
            install_status=MainInstallHistory.INSTALL_STATUS_INSTALLING,
            env=env)
        resp = self.delete(reverse("env-detail", args=[env.id]))
        assert resp.json()["code"] == 1
        assert Env.objects.filter(id=env.id).exists()
        # 任务进入终态后可删
        history.install_status = MainInstallHistory.INSTALL_STATUS_SUCCESS
        history.save(update_fields=["install_status"])
        # 该环境的周期任务应被注销
        schedule = CrontabSchedule.objects.create()  # 字段默认全 '*'
        PeriodicTask.objects.create(
            name="inspection_crontab_del", crontab=schedule,
            task="inspection.tasks.inspection_crontab",
            kwargs=json.dumps({"env": env.id}))
        # 其它环境/无 env 的任务不受影响
        keep_task = PeriodicTask.objects.create(
            name="inspection_crontab_keep", crontab=schedule,
            task="inspection.tasks.inspection_crontab",
            kwargs=json.dumps({"env": 1, "job_type": 1}))

        resp = self.delete(reverse("env-detail", args=[env.id]))
        assert resp.json()["code"] == 0

        assert not Env.objects.filter(id=env.id).exists()
        assert self.config_counts(env.id) == (0,) * 7
        # MainInstallHistory 行保留，env 置空（SET_NULL）
        history.refresh_from_db()
        assert history.env_id is None
        assert not PeriodicTask.objects.filter(
            name="inspection_crontab_del").exists()
        assert PeriodicTask.objects.filter(
            name="inspection_crontab_keep").exists()


class TestEnvUsers(EnvViewTestBase):
    """ GET/PATCH /api/env/{id}/users/ 授权管理 """

    def test_env_users_patch(self):
        """ PATCH user_ids 全量覆盖，GET 结果一致 """
        u1 = UserProfile.objects.create_user(
            username="envu1", password="p1", email="envu1@test.com")
        u2 = UserProfile.objects.create_user(
            username="envu2", password="p2", email="envu2@test.com")
        url = reverse("env-users", args=[1])

        resp = self.patch(url, {"user_ids": [u1.id, u2.id]})
        assert resp.json()["code"] == 0
        assert set(UserEnv.objects.filter(env_id=1).values_list(
            "user_id", flat=True)) == {u1.id, u2.id}

        resp = self.get(url)
        assert resp.json()["code"] == 0
        assert sorted(resp.json()["data"]["user_ids"]) == sorted([u1.id, u2.id])

        # 全量覆盖：只保留 u2
        resp = self.patch(url, {"user_ids": [u2.id]})
        assert resp.json()["code"] == 0
        resp = self.get(url)
        assert resp.json()["data"]["user_ids"] == [u2.id]
        assert not UserEnv.objects.filter(env_id=1, user=u1).exists()

    def test_env_users_patch_invalid_user_rejected(self):
        """ user_ids 含不存在用户：拒绝且不落库 """
        url = reverse("env-users", args=[1])
        resp = self.patch(url, {"user_ids": [99999]})
        assert resp.json()["code"] == 1
        assert not UserEnv.objects.filter(env_id=1, user_id=99999).exists()


class TestEnvListVisibility(EnvViewTestBase):
    """ GET /api/env/ 列表可见性与元素结构 """

    def test_superuser_list_all_with_counts(self):
        """ superuser 全量，元素含资源统计字段 """
        env = Env.objects.create(name="新环境", code="newenv")
        Host.objects.create(
            instance_name="host-l", ip="10.0.0.2", username="root",
            password="x", operate_system="centos", env=env)
        Service.objects.create(
            ip="10.0.0.2", service_instance_name="redis-1", env=env)

        resp = self.get(ENV_LIST_URL)
        resp_json = resp.json()
        assert resp_json["code"] == 0
        data = resp_json["data"]
        assert isinstance(data, list)
        by_id = {item["id"]: item for item in data}
        assert set(by_id) >= {1, env.id}
        item = by_id[env.id]
        assert set(item.keys()) == {
            "id", "name", "code", "description", "created",
            "host_count", "service_count"}
        assert item["host_count"] == 1
        assert item["service_count"] == 1
        assert by_id[1]["host_count"] == 0

    def test_readonly_user_sees_only_authorized(self):
        """ readonlyuser 列表仅授权环境；带已授权 X-Env-Id 也不按其过滤 """
        env_a = Env.objects.create(name="A环境", code="enva")
        env_b = Env.objects.create(name="B环境", code="envb")
        ro_user = UserProfile.objects.create_user(
            username="ro_list", password="p1", email="rol@test.com",
            role="readonlyuser")
        UserEnv.objects.create(user=ro_user, env_id=1)
        UserEnv.objects.create(user=ro_user, env=env_a)
        self.auth_as(ro_user)

        # 前端刷新会带 X-Env-Id（Task 16 约定）：带已授权环境标识时，
        # 列表仍返回全部授权环境，不得按其过滤
        resp = self.client.get(
            ENV_LIST_URL, HTTP_X_ENV_ID=str(env_a.id))
        data = resp.json()["data"]
        assert {item["id"] for item in data} == {1, env_a.id}

        # 未授权环境标识由 EnvContextMiddleware 拦截（403，平台边界）
        resp = self.client.get(
            ENV_LIST_URL, HTTP_X_ENV_ID=str(env_b.id))
        assert resp.status_code == 403
        assert resp.json()["code"] == 1

    def test_readonly_user_cannot_manage_envs(self):
        """ readonlyuser 创建环境：拒绝（环境管理仅 superuser） """
        ro_user = UserProfile.objects.create_user(
            username="ro_create", password="p1", email="roc@test.com",
            role="readonlyuser")
        # 路径一：携带真实 token，RoleAuthenticationMiddleware 拦截
        self.auth_as(ro_user)
        resp = self.post(ENV_LIST_URL, {"name": "x", "code": "rox"})
        assert resp.json()["code"] == 1
        # 路径二：中间件放行（解析不到用户）时的视图层 superuser 兜底
        self.client.cookies.pop("jwtToken", None)
        with patch(
                "rest_framework.authentication.BaseAuthentication.authenticate",
                return_value=(ro_user, None)):
            resp = self.post(ENV_LIST_URL, {"name": "x", "code": "rox"})
        assert resp.json()["code"] == 1
        assert not Env.objects.filter(code="rox").exists()
