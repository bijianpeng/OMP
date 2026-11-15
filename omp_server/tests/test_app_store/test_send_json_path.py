# -*- coding: utf-8 -*-
"""
pre 阶段 json 下发链路测试(老链路 PreInstallHistory 缺失修复)

背景(实证: 2026-11-15 main 20/21/22 jdk-56-109 安装失败):
- /api/appStore/executeInstall/ 走老链路 install_utils.CreateInstallPlan,
  其 run() 只创建 Main/Detail 安装记录并生成 data json,
  不创建 PreInstallHistory(新链路 new_install_utils 会创建)。
- celery 执行器 install_exec.create_user_and_send_json 按 (main, ip)
  查询 PreInstallHistory, 查不到时 `continue` 静默跳过整个前置阶段:
  无异常、无 "Pre-install failed" 日志、json 文件从未 salt 下发,
  Install 步骤目标机读 /opt/omp_packages/{uuid}.json 报 No such file。
- 修复:
  1) 老链路 run() 补建 PreInstallHistory(与新链路对齐);
  2) 执行器查不到记录时补建并执行, 不再静默跳过;
  3) execute_pre_install 捕获异常时输出完整 traceback(可见性)。
"""
import os
import sys
import uuid as uuid_module
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from django.test import TestCase

from omp_server.settings import PROJECT_DIR
from app_store.install_exec import InstallServiceExecutor
from app_store import install_utils
from db_models.models import (
    ApplicationHub, DetailInstallHistory, Env, Host,
    MainInstallHistory, PreInstallHistory, Service,
    UploadPackageHistory,
)

IP = "10.10.10.11"
JSON_DIR = os.path.join(PROJECT_DIR, "package_hub", "data_files")


def _make_env_host_main(operation_uuid):
    """构造 pre 阶段依赖的最小对象图(Env/Host/主安装记录)"""
    if not Env.objects.filter(id=1).exists():
        Env.objects.create(id=1, name="default")
    if not Host.objects.filter(ip=IP).exists():
        Host.objects.create(
            instance_name=f"host-{IP}", ip=IP, port=22, username="root",
            password="fake_password", data_folder="/data/test",
            operate_system="CentOS", host_name=f"hostname-{IP}",
            agent_dir="/data/test",
        )
    return MainInstallHistory.objects.create(
        operator="test", operation_uuid=operation_uuid,
        install_status=MainInstallHistory.INSTALL_STATUS_INSTALLING,
        install_log="",
    )


class SendJsonFileTestCase(TestCase):
    """json 文件读/写路径一致性(写入方 install_utils/new_install_utils
    make_data_json 均写 PROJECT_DIR/package_hub/data_files)"""

    def setUp(self):
        self.uuid = str(uuid_module.uuid4())
        self.json_path = os.path.join(JSON_DIR, f"{self.uuid}.json")
        with open(self.json_path, "w", encoding="utf8") as fp:
            fp.write('[{"ip": "%s", "install_args": '
                     '[{"key": "run_user", "default": "omp"}]}]' % IP)

    def tearDown(self):
        if os.path.exists(self.json_path):
            os.remove(self.json_path)

    def test_parse_origin_data_reads_package_hub_data_files(self):
        """parse_origin_data 必须从 PROJECT_DIR/package_hub/data_files
        读取(与 make_data_json 写入位置一致, 不依赖进程 cwd)"""
        main = _make_env_host_main(self.uuid)
        executor = InstallServiceExecutor(main_id=main.id, username="test")
        ip_user_map = executor.parse_origin_data(f"data_files/{self.uuid}.json")
        self.assertEqual(ip_user_map, {IP: ["omp"]})

    def test_send_json_without_pre_install_history(self):
        """老链路 main 无 PreInstallHistory 时(生产事故形态):
        执行器应补建记录并完成 json 下发, 而非静默跳过"""
        main = _make_env_host_main(self.uuid)
        executor = InstallServiceExecutor(main_id=main.id, username="test")
        with patch("app_store.install_exec.SaltClient") as mock_salt:
            salt_instance = mock_salt.return_value
            # set_hostname_analysis 探测: 返回包含 write_hostname
            salt_instance.cmd.return_value = (True, "ok write_hostname")
            salt_instance.cp_file.return_value = (True, "/opt/omp_packages")
            executor.create_user_and_send_json(main)
        # 前置记录被补建且执行成功
        pre_obj = PreInstallHistory.objects.filter(
            main_install_history=main, ip=IP).last()
        self.assertIsNotNone(pre_obj)
        self.assertEqual(pre_obj.install_flag, 2)
        # json 已按 salt file_roots 相对路径下发到目标机 omp_packages
        salt_instance.cp_file.assert_called_once()
        _, kwargs = salt_instance.cp_file.call_args
        # salt:// 相对路径, 由 salt master file_roots(package_hub) 解析
        self.assertEqual(
            kwargs["source_path"],
            os.path.join("data_files", f"{self.uuid}.json"))
        self.assertIn(f"omp_packages/{self.uuid}.json", kwargs["target_path"])


class OldCreateInstallPlanPreHistoryTestCase(TestCase):
    """老链路 install_utils.CreateInstallPlan.run 应补建 PreInstallHistory
    (与新链路 new_install_utils.create_pre_install_history 对齐)"""

    def setUp(self):
        self.uuid = str(uuid_module.uuid4())
        self.json_path = os.path.join(JSON_DIR, f"{self.uuid}.json")

    def tearDown(self):
        if os.path.exists(self.json_path):
            os.remove(self.json_path)

    def test_run_creates_pre_install_history(self):
        main = _make_env_host_main(self.uuid)
        package = UploadPackageHistory.objects.create(
            operation_uuid=self.uuid,
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
            ip=IP, service_instance_name="jdk-pre-history",
            service=app, service_status=Service.SERVICE_STATUS_INSTALLING,
            service_port="[]",
        )
        plan = install_utils.CreateInstallPlan(install_data={
            "install_type": 0,
            "install_services": [{"ip": IP, "name": "jdk",
                                  "version": "1.8.0"}],
        })
        with patch.object(install_utils.CreateInstallPlan, "create_service",
                          return_value=service), \
                patch.object(install_utils.CreateInstallPlan,
                             "create_product_instance"), \
                patch.object(install_utils.CreateInstallPlan,
                             "check_if_has_post_action",
                             return_value=False), \
                patch.object(install_utils, "install_service") as mock_task, \
                patch.object(install_utils.DataJson, "run"):
            mock_task.delay.return_value = "fake-task-id"
            flag, msg = plan.run()
        self.assertTrue(flag, msg)
        # run() 内部新建了主安装记录, msg 即其 operation_uuid
        new_main = MainInstallHistory.objects.filter(
            operation_uuid=msg).first()
        self.assertIsNotNone(new_main)
        pre_qs = PreInstallHistory.objects.filter(
            main_install_history=new_main, ip=IP)
        self.assertTrue(
            pre_qs.exists(),
            "老链路 CreateInstallPlan.run 未创建 PreInstallHistory")


class PreInstallTracebackTestCase(TestCase):
    """execute_pre_install 吞异常时应输出完整 traceback(可见性)"""

    def test_pre_install_failure_logs_traceback(self):
        main = _make_env_host_main(str(uuid_module.uuid4()))
        executor = InstallServiceExecutor(main_id=main.id, username="test")
        with patch.object(
                InstallServiceExecutor, "create_user_and_send_json",
                side_effect=RuntimeError("boom")):
            with self.assertLogs("server", level="ERROR") as cm:
                executor.execute_pre_install(main)
        logged = "\n".join(cm.output)
        self.assertIn("Pre-install failed: boom", logged)
        self.assertIn("Traceback (most recent call last)", logged)
        self.assertIn("RuntimeError: boom", logged)
