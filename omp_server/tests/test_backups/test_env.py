# -*- coding: utf-8 -*-
"""
backups 模块环境上下文接入测试（多环境架构 Task 12）

覆盖：
1. 备份策略列表按当前环境过滤；创建自动写入当前环境（请求体伪造 env
   无效）；定时任务 kwargs 补 env_id；跨环境 PUT / DELETE 404
2. 备份记录列表按当前环境过滤
3. 可备份实例列表按当前环境过滤
4. 备份回调（PATCH backupHistory）无 X-Env-Id / 无登录态照常更新
   （env_exempt 豁免，按记录自身 env 处理，记录 env 不变）

测试基建说明：同 tests/test_services/test_service_env.py——继承 BaseTest
（非 AutoLoginTest），显式放开本文件涉及视图的认证与权限。
"""
import json
from unittest import mock

import pytest

from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse

from tests.base import BaseTest
from db_models.models import (
    Env, ApplicationHub, Service, BackupSetting, BackupHistory)
from backups import views as backups_views
from backups.backups_serializers import BackupSettingSerializer

CRONTAB_DETAIL = {
    "minute": "0", "hour": "1", "day_of_month": "*",
    "month_of_year": "*", "day_of_week": "*",
}


def make_setting(env, instances=("mysql-1",)):
    """ 直接落库一条指定环境的备份策略 """
    return BackupSetting.objects.create(
        backup_instances=list(instances), is_on=True,
        crontab_detail=dict(CRONTAB_DETAIL), retain_day=1,
        retain_path="/data/omp/data/backup/", env=env)


def make_service(app, instance_name, ip, env):
    """ 直接落库一个指定环境的可备份服务实例 """
    return Service.objects.create(
        service_instance_name=instance_name,
        ip=ip,
        service_status=Service.SERVICE_STATUS_NORMAL,
        service=app,
        env=env,
    )


@pytest.mark.django_db
class BackupEnvContextTest(BaseTest):
    """ backups 模块环境上下文行为 """

    def setUp(self):
        super(BackupEnvContextTest, self).setUp()
        # 显式放开本文件涉及视图的认证与权限（说明同 services 环境测试）
        for view_cls in (backups_views.BackupSettingView,
                         backups_views.BackupHistoryView,
                         backups_views.CanBackupInstancesView):
            view_cls.authentication_classes = []
            view_cls.permission_classes = [AllowAny]
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")
        self.setting_url = reverse("backupSettings-list")
        self.history_url = reverse("backupHistory-list")
        self.instances_url = reverse("canBackupInstances-list")

    def _json_headers(self, env_id=None):
        headers = {"content_type": "application/json; charset=utf-8"}
        if env_id is not None:
            headers["HTTP_X_ENV_ID"] = str(env_id)
        return headers

    def test_backup_setting_filtered_and_created_with_env(self):
        """ 备份策略：两环境各 1 条，列表按当前环境过滤；创建写入当前环境
            （伪造 env 无效），定时任务 kwargs 补 env_id；跨环境
            PUT / DELETE -> 统一包 code=1 且记录不受影响 """
        from django_celery_beat.models import PeriodicTask

        setting_a = make_setting(self.env_default)
        setting_b = make_setting(self.env_b)

        # 列表过滤：B 上下文仅见 B 策略；无标识（pytest 注入 default）
        # 仅见 default 策略
        resp_b = self.client.get(
            self.setting_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_b.get("data")], [setting_b.id])
        resp_default = self.client.get(self.setting_url).json()
        self.assertEqual(resp_default.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_default.get("data")], [setting_a.id])

        # 创建：body 伪造 env=default，实际落 B 环境
        with mock.patch.object(
                BackupSettingSerializer, "validate_retain_path",
                lambda self, value: value):
            resp_create = self.client.post(
                self.setting_url,
                data=json.dumps({
                    "backup_instances": ["mysql-b"],
                    "crontab_detail": dict(CRONTAB_DETAIL),
                    "retain_day": 1,
                    "retain_path": "/data/omp/data/backup/",
                    "is_on": True,
                    "env": self.env_default.id,  # 伪造，应被忽略
                }),
                **self._json_headers(env_id=self.env_b.id)).json()
            self.assertEqual(resp_create.get("code"), 0)
        created = BackupSetting.objects.exclude(
            id__in=[setting_a.id, setting_b.id]).first()
        self.assertIsNotNone(created)
        self.assertEqual(created.env, self.env_b)

        # 定时任务 kwargs 补 env_id（任务侧按 task_id 读取策略自身 env）
        task = PeriodicTask.objects.filter(
            name=f"backups_cron_task_{created.id}").first()
        self.assertIsNotNone(task)
        task_kwargs = json.loads(task.kwargs)
        self.assertEqual(task_kwargs.get("task_id"), created.id)
        self.assertEqual(task_kwargs.get("env_id"), self.env_b.id)

        # 跨环境 PUT / DELETE：统一包 code=1，记录不受影响
        detail_url_a = reverse(
            "backupSettings-detail", args=[setting_a.id])
        resp_put = self.client.put(
            detail_url_a,
            data=json.dumps({
                "backup_instances": ["mysql-a"],
                "crontab_detail": dict(CRONTAB_DETAIL),
                "retain_day": 1, "retain_path": "/data/omp/data/backup/",
                "is_on": True}),
            **self._json_headers(env_id=self.env_b.id)).json()
        self.assertEqual(resp_put.get("code"), 1)
        self.assertIsNone(resp_put.get("data"))
        resp_delete = self.client.delete(
            detail_url_a, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_delete.get("code"), 1)
        self.assertIsNone(resp_delete.get("data"))
        self.assertTrue(
            BackupSetting.objects.filter(id=setting_a.id).exists())

    def test_backup_history_list_filtered(self):
        """ 备份记录：两环境各 1 条，列表按当前环境过滤 """
        history_a = BackupHistory.objects.create(
            backup_name="backup-default", env=self.env_default)
        history_b = BackupHistory.objects.create(
            backup_name="backup-B", env=self.env_b)

        resp_b = self.client.get(
            self.history_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_b.get("data").get("results")],
            [history_b.id])
        resp_default = self.client.get(self.history_url).json()
        self.assertEqual(resp_default.get("code"), 0)
        self.assertEqual(
            [r.get("id") for r in resp_default.get("data").get("results")],
            [history_a.id])

    def test_can_backup_instances_filtered_by_env(self):
        """ 可备份实例：两环境各 1 个，仅返回当前环境的实例 """
        app = ApplicationHub.objects.create(
            app_name="mysql", app_version="1.0",
            app_type=ApplicationHub.APP_TYPE_COMPONENT,
            is_release=True, is_base_env=False,
            extend_fields={"base_env": False, "affinity": ""})
        make_service(app, "mysql-default", "10.10.0.1", self.env_default)
        make_service(app, "mysql-b", "10.10.0.2", self.env_b)

        with mock.patch("backups.views.BACKUP_SERVICE", ["mysql"]):
            resp_b = self.client.get(
                self.instances_url,
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
            self.assertEqual(resp_b.get("code"), 0)
            self.assertEqual(sorted(resp_b.get("data")), ["mysql-b"])
            resp_default = self.client.get(self.instances_url).json()
            self.assertEqual(resp_default.get("code"), 0)
            self.assertEqual(
                sorted(resp_default.get("data")), ["mysql-default"])

    def test_backup_callback_without_header_ok(self):
        """ 备份回调：PATCH 不带 X-Env-Id、不带登录态 -> 200 照常更新
            （env_exempt 豁免环境上下文，按记录自身 env 处理，env 不变）"""
        history_b = BackupHistory.objects.create(
            backup_name="backup-callback", content="mysql-b",
            result=BackupHistory.ING, file_name="backup-callback.tar.gz",
            env=self.env_b)
        callback_url = reverse("backupHistory-detail", args=[history_b.id])

        # 模拟被管节点回调：无环境标识、无 cookie
        resp = self.client.patch(
            callback_url,
            data=json.dumps({"result": "0", "ip": "10.10.0.2"}),
            content_type="application/json; charset=utf-8")
        self.assertEqual(resp.status_code, 200)
        resp_json = resp.json()
        self.assertEqual(resp_json.get("code"), 0)
        history_b.refresh_from_db()
        # result="0" -> 备份成功；无 remote_path -> file_deleted 置 True
        self.assertEqual(history_b.result, BackupHistory.SUCCESS)
        self.assertTrue(history_b.file_deleted)
        # 记录自身 env 不变（回调不做环境处理）
        self.assertEqual(history_b.env, self.env_b)

    def test_backup_history_created_with_setting_env(self):
        """ 定时备份任务落库：BackupHistory.env 跟随策略所属环境
            （多环境终审必修项 1——env2 策略产出的历史不落 default）"""
        from backups import tasks as backups_tasks

        setting_b = make_setting(self.env_b, instances=("mysql-b",))
        setting_a = make_setting(self.env_default, instances=("mysql-a",))

        # 模拟任务路径：执行细节（真实备份调用 / 过期清理）全部 mock，
        # 只保留 BackupHistory 落库行为
        with mock.patch.object(backups_tasks, "check_ing",
                               return_value=False), \
                mock.patch.object(backups_tasks, "backup_service_data"), \
                mock.patch.object(backups_tasks, "rm_backend_file"):
            backups_tasks.backup_service.run(task_id=setting_b.id)
            backups_tasks.backup_service.run(task_id=setting_a.id)

        history_b = BackupHistory.objects.filter(
            content="mysql-b").first()
        self.assertIsNotNone(history_b)
        self.assertEqual(history_b.env, self.env_b)
        history_a = BackupHistory.objects.filter(
            content="mysql-a").first()
        self.assertIsNotNone(history_a)
        self.assertEqual(history_a.env, self.env_default)
