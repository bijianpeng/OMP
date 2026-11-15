# -*- coding: utf-8 -*-
"""
unzip 步骤 install_detail_args 参数键名兼容性测试(schema 错配修复)

背景:
- /api/appStore/executeInstall/ 把前端原始 install_services[i] 原样写入
  DetailInstallHistory.install_detail_args, 其参数键名为 app_install_args
  (new_install_utils.py)。
- celery 安装任务执行器 install_exec.py / install_executor.py 的 unzip 步骤
  读取的是 install_args 键, 键名错配导致找不到 base_dir,
  报 "未获取到解压目标路径" (实证: 2026-11-15 jdk-56-109 安装失败)。
- 修复: 读取侧兼容两种键, 老 schema install_args 优先, 缺省回退 app_install_args。
"""
import os
import queue
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from django.test import TestCase

from app_store.install_exec import InstallServiceExecutor as OldExecutor
from app_store.install_executor import InstallServiceExecutor as NewExecutor
from db_models.models import (
    ApplicationHub, DetailInstallHistory, Env, Host,
    MainInstallHistory, Service, UploadPackageHistory,
)

IP = "10.10.10.10"
BASE_DIR = "/data/test/jdk"


def _make_env_host_service_detail(install_detail_args):
    """构造 unzip 步骤依赖的最小对象图(Env/Host/包/应用/服务/主记录/明细)"""
    if not Env.objects.filter(id=1).exists():
        Env.objects.create(id=1, name="default")
    Host.objects.create(
        instance_name=f"host-{IP}", ip=IP, port=22, username="root",
        password="fake_password", data_folder="/data/test",
        operate_system="CentOS", host_name=f"hostname-{IP}",
        agent_dir="/data/test",
    )
    package = UploadPackageHistory.objects.create(
        operation_uuid="test-uuid-unzip-schema",
        package_name="jdk-1.8.0.tar.gz",
        package_md5="0" * 32,
        package_path="test/jdk-1.8.0.tar.gz",
    )
    app = ApplicationHub.objects.create(
        app_name="jdk", app_version="1.8.0",
        app_type=ApplicationHub.APP_TYPE_SERVICE,
        app_package=package,
    )
    service = Service.objects.create(
        ip=IP, service_instance_name="jdk-instance", service=app,
        service_status=Service.SERVICE_STATUS_INSTALLING,
        service_port="[]",
    )
    main = MainInstallHistory.objects.create(
        operator="test", operation_uuid="test-uuid-unzip-schema-main",
        install_status=MainInstallHistory.INSTALL_STATUS_INSTALLING,
        install_log="",
    )
    detail = DetailInstallHistory.objects.create(
        service=service, main_install_history=main,
        install_step_status=DetailInstallHistory.INSTALL_STATUS_READY,
        send_msg="", unzip_msg="", install_msg="",
        init_msg="", start_msg="",
        install_detail_args=install_detail_args,
    )
    return service, detail


NEW_SCHEMA_ARGS = {
    # 新前端 payload 原样落库: 参数键名为 app_install_args
    "name": "jdk",
    "app_install_args": [
        {"key": "base_dir", "default": BASE_DIR},
        {"key": "run_user", "default": "omp"},
    ],
}
OLD_SCHEMA_ARGS = {
    # 老 schema: 参数键名为 install_args
    "name": "jdk",
    "install_args": [
        {"key": "base_dir", "default": BASE_DIR},
    ],
}


class UnzipSchemaTestMixin:
    """两个执行器(install_exec/install_executor)共用的 unzip 兼容性用例"""

    executor_cls = None
    # install_exec 的 unzip 使用单主机解压并发队列, 需提前构建(真实流程见其 run 入口)
    need_concurrent_controller = False

    def _run_unzip(self, install_detail_args):
        service, detail = _make_env_host_service_detail(install_detail_args)
        executor = self.executor_cls(
            main_id=detail.main_install_history_id, username="test")
        if self.need_concurrent_controller:
            executor.unzip_concurrent_controller[IP] = \
                queue.Queue(maxsize=3)
        with patch(
                f"{self.executor_cls.__module__}.SaltClient") as mock_salt:
            mock_salt.return_value.cmd.return_value = (True, "")
            result = executor.unzip(detail)
        detail.refresh_from_db()
        return result, detail

    def test_unzip_new_schema_app_install_args(self):
        """新 schema: 仅含 app_install_args(带 base_dir)也应解压成功"""
        result, detail = self._run_unzip(NEW_SCHEMA_ARGS)
        self.assertEqual(result[0], True)
        self.assertEqual(detail.unzip_flag, 2)
        self.assertNotIn("未获取到解压目标路径", detail.unzip_msg)

    def test_unzip_old_schema_install_args(self):
        """老 schema 回归: 含 install_args 的存量数据仍正常"""
        result, detail = self._run_unzip(OLD_SCHEMA_ARGS)
        self.assertEqual(result[0], True)
        self.assertEqual(detail.unzip_flag, 2)
        self.assertNotIn("未获取到解压目标路径", detail.unzip_msg)

    def test_unzip_new_schema_failure_path_no_key_mismatch_error(self):
        """新 schema 解压失败时, 失败原因不应是键名错配的
        '未获取到解压目标路径'(salt 执行失败属正常失败)"""
        service, detail = _make_env_host_service_detail(NEW_SCHEMA_ARGS)
        executor = self.executor_cls(
            main_id=detail.main_install_history_id, username="test")
        if self.need_concurrent_controller:
            executor.unzip_concurrent_controller[IP] = \
                queue.Queue(maxsize=3)
        with patch(
                f"{self.executor_cls.__module__}.SaltClient") as mock_salt:
            mock_salt.return_value.cmd.return_value = (False, "salt error")
            result = executor.unzip(detail)
        detail.refresh_from_db()
        self.assertEqual(result[0], False)
        self.assertEqual(detail.unzip_flag, 3)
        self.assertIn("salt error", detail.unzip_msg)
        self.assertNotIn("未获取到解压目标路径", detail.unzip_msg)


class TestInstallExecUnzipSchema(UnzipSchemaTestMixin, TestCase):
    """celery 在用执行器 app_store.install_exec"""
    executor_cls = OldExecutor
    need_concurrent_controller = True


class TestInstallExecutorUnzipSchema(UnzipSchemaTestMixin, TestCase):
    """新执行器 app_store.install_executor(保持双执行器一致)"""
    executor_cls = NewExecutor
