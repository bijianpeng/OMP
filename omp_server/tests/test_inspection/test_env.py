# -*- coding: utf-8 -*-
"""
inspection 模块环境上下文接入测试（多环境架构 Task 12）

覆盖：
1. 巡检记录 / 巡检定时任务列表按当前环境上下文过滤（两环境数据隔离）
2. 手动巡检创建：服务端以 request.env 为准覆盖请求体 env（防伪造），
   celery 任务下发使用覆盖后的环境
3. 巡检定时任务创建/更新：请求体 env 覆盖 + 定时任务 kwargs 携带
   当前环境 id；跨环境（伪造 job_type 行）更新 404
4. 巡检邮件设置读写按当前环境（list 不再写死 env_id=1，create 忽略
   请求体 env_id）

测试基建说明：同 tests/test_services/test_service_env.py——继承 BaseTest
（非 AutoLoginTest），显式放开本文件涉及视图的认证与权限，规避模块导入
顺序差异；EnvContextMiddleware 对匿名用户（cookie 无法解析）放行环境
授权，显式 X-Env-Id 仍走完整环境解析链，request.env 为 header 指定环境。
"""
import json
from unittest import mock

import pytest

from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse

from tests.base import BaseTest
from db_models.models import (
    Env, InspectionHistory, InspectionCrontab, ModuleSendEmailSetting)
from inspection import views as inspection_views


def make_history(name, env, inspection_type="host"):
    """ 直接落库一条指定环境的巡检记录 """
    return InspectionHistory.objects.create(
        inspection_name=name, inspection_type=inspection_type,
        inspection_status=2, execute_type="man",
        inspection_operator="admin", hosts=[], services=[], env=env)


def make_crontab_payload(job_type, env_id):
    """ 构造巡检定时任务创建/更新请求体（env 为可伪造字段） """
    return {
        "crontab_detail": {"hour": "09", "minute": "41", "month": "*",
                           "day_of_week": "1", "day": "*"},
        "env": env_id,
        "is_start_crontab": 0,
        "job_name": "深度分析",
        "job_type": job_type,
    }


@pytest.mark.django_db
class InspectionEnvContextTest(BaseTest):
    """ inspection 模块环境上下文行为 """

    def setUp(self):
        super(InspectionEnvContextTest, self).setUp()
        # 显式放开本文件涉及视图的认证与权限（说明同 services 环境测试）
        for view_cls in (inspection_views.InspectionHistoryView,
                         inspection_views.InspectionCrontabView,
                         inspection_views.InspectionSendEmailSettingView):
            view_cls.authentication_classes = []
            view_cls.permission_classes = [AllowAny]
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")
        self.history_url = reverse("history-list")
        self.crontab_url = reverse("crontab-list")
        self.email_url = reverse("inspectionSendEmailSetting-list")

    def _post(self, url, data, env_id=None):
        """ JSON POST，可携带环境标识 """
        kwargs = {}
        if env_id is not None:
            kwargs["HTTP_X_ENV_ID"] = str(env_id)
        return self.client.post(
            url, data=json.dumps(data),
            content_type="application/json; charset=utf-8", **kwargs).json()

    def _put(self, url, data, env_id=None):
        """ JSON PUT，可携带环境标识 """
        kwargs = {}
        if env_id is not None:
            kwargs["HTTP_X_ENV_ID"] = str(env_id)
        return self.client.put(
            url, data=json.dumps(data),
            content_type="application/json; charset=utf-8", **kwargs).json()

    def test_inspection_list_filtered(self):
        """ 巡检记录/定时任务：两环境各 1 条，列表按当前环境上下文过滤 """
        history_a = make_history("巡检-default", self.env_default)
        history_b = make_history("巡检-B", self.env_b)
        crontab_a = InspectionCrontab.objects.create(
            job_type=0, job_name="深度分析-default",
            crontab_detail={}, is_start_crontab=1, env=self.env_default)
        crontab_b = InspectionCrontab.objects.create(
            job_type=0, job_name="深度分析-B",
            crontab_detail={}, is_start_crontab=1, env=self.env_b)

        # 显式 B 环境上下文：仅见 B 记录
        resp_history_b = self.client.get(
            self.history_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_history_b.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_history_b.get("data").get("results")],
            [history_b.id])
        resp_cron_b = self.client.get(
            self.crontab_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_cron_b.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_cron_b.get("data").get("results")],
            [crontab_b.id])

        # 未携带标识（pytest 注入 default 环境）：仅见 default 记录
        resp_history_default = self.client.get(self.history_url).json()
        self.assertEqual(resp_history_default.get("code"), 0)
        self.assertEqual(
            [r.get("id")
             for r in resp_history_default.get("data").get("results")],
            [history_a.id])
        resp_cron_default = self.client.get(self.crontab_url).json()
        self.assertEqual(resp_cron_default.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_cron_default.get("data").get("results")],
            [crontab_a.id])

    def test_manual_inspection_overrides_body_env(self):
        """ 手动巡检创建：请求体 env 伪造为 default，服务端以 request.env
            （B）为准覆盖；celery 任务 env_id 同步使用 B """
        with mock.patch(
                "inspection.views.get_prometheus_data.delay") as delay_mock:
            payload = {
                "env": self.env_default.id,  # 伪造为 default 环境
                "execute_type": "man", "hosts": ["10.0.0.1"],
                "inspection_operator": "admin", "inspection_status": 1,
                "inspection_type": "host", "services": []}
            resp = self._post(
                self.history_url, payload, env_id=self.env_b.id)
            self.assertEqual(resp.get("code"), 0)
            # 落库记录与响应 env 均为请求环境 B
            history = InspectionHistory.objects.filter(
                inspection_type="host").first()
            self.assertIsNotNone(history)
            self.assertEqual(history.env, self.env_b)
            self.assertEqual(resp.get("data").get("env"), self.env_b.id)
            # celery 任务下发使用覆盖后的环境
            delay_mock.assert_called_once()
            self.assertEqual(
                delay_mock.call_args.kwargs.get("env_id"), self.env_b.id)

    def test_crontab_overrides_body_env(self):
        """ 巡检定时任务创建/更新：请求体 env 覆盖为 request.env，定时任务
            kwargs 携带该环境；跨环境（default 上下文）更新 B 行 404 """
        from django_celery_beat.models import PeriodicTask

        # 创建：body env 伪造为 default，实际落 B + kwargs 带 B；
        # 定时任务名带环境 code 前缀（Task 7b per-env 命名）
        resp = self._post(
            self.crontab_url, make_crontab_payload(0, self.env_default.id),
            env_id=self.env_b.id)
        self.assertEqual(resp.get("code"), 0)
        crontab_b = InspectionCrontab.objects.filter(
            env=self.env_b, job_type=0).first()
        self.assertIsNotNone(crontab_b)
        task = PeriodicTask.objects.filter(
            name="inspection_cron_task_staging_deep").first()
        self.assertIsNotNone(task)
        self.assertEqual(json.loads(task.kwargs).get("env"), self.env_b.id)

        # 更新：B 上下文更新 B 行，kwargs 环境仍为 B
        # （update 会删除并重建同名定时任务，需按 name 重新获取）
        resp_upd = self._put(
            f"{self.crontab_url}0/", make_crontab_payload(0, self.env_default.id),
            env_id=self.env_b.id)
        self.assertEqual(resp_upd.get("code"), 0)
        crontab_b.refresh_from_db()
        self.assertEqual(crontab_b.env, self.env_b)
        task = PeriodicTask.objects.filter(
            name="inspection_cron_task_staging_deep").first()
        self.assertIsNotNone(task)
        self.assertEqual(json.loads(task.kwargs).get("env"), self.env_b.id)

        # default 上下文（pytest 注入）按 job_type=0 更新：B 行不可见 -> 404
        resp_cross = self._put(
            f"{self.crontab_url}0/", make_crontab_payload(0, 1))
        self.assertEqual(resp_cross.get("code"), 1)
        self.assertIsNone(resp_cross.get("data"))
        crontab_b.refresh_from_db()
        self.assertEqual(crontab_b.env, self.env_b)

    def test_inspection_email_setting_uses_request_env(self):
        """ 巡检邮件设置：list 按当前环境读取（不再写死 env_id=1）；create
            忽略请求体 env_id，写入当前环境；两环境互不影响 """
        # default 环境已有配置
        ModuleSendEmailSetting.update_email_settings(
            self.env_default.id, "inspection", True, "default@omp.com")

        # B 环境 GET：空配置（不串读 default 的）
        resp_b = self.client.get(
            self.email_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        self.assertEqual(resp_b.get("data"), {})

        # B 环境写入：body 伪造 env_id=1 应被忽略
        resp_post = self._post(
            self.email_url,
            {"env_id": self.env_default.id, "send_email": True,
             "to_users": "b@omp.com"},
            env_id=self.env_b.id)
        self.assertEqual(resp_post.get("code"), 0)
        setting_b = ModuleSendEmailSetting.objects.filter(
            env=self.env_b, module="inspection").first()
        self.assertIsNotNone(setting_b)
        self.assertEqual(setting_b.to_users, "b@omp.com")

        # B 环境再读：读到 B 的配置
        resp_b2 = self.client.get(
            self.email_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(
            resp_b2.get("data").get("to_users"), "b@omp.com")
        # default 环境（pytest 注入）读：仍是 default 的配置
        resp_default = self.client.get(self.email_url).json()
        self.assertEqual(
            resp_default.get("data").get("to_users"), "default@omp.com")
