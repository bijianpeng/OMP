# -*- coding: utf-8 -*-
"""
check_service_args 的 dir_key 真值判断测试

背景（run_user 被拼成路径 bug）：
- 新前端（omp_web shared.ts installArgKey）曾对所有 install 参数
  统一注入 `dir_key: null`（`?? null` 规范化），随提交落库；
- 后端 make_app_install_args 只给 default 含 {data_path} 的路径参数打
  真值 dir_key 标记，非路径参数本不应携带该键；
- 三处 check_service_args 均只判 `if "dir_key" not in el`（只判键存在
  不判值）→ run_user 等非路径参数被当作路径参数：
  * 老链路 install_utils：default 被 os.path.join(data_path, ...) 改写
    （run_user "common" → "/data/common"，重放再叠 "/data/data/common"，
    useradd 得到无效用户名）；
  * 新链路 new_install_utils 两处：对非路径参数跑 `test -d <default>`，
    default 非路径时可能误报"路径已存在"。

修复：判断改为真值判断 `if not el.get("dir_key"): continue`，
null/空串/缺键均不算路径参数；带真值 dir_key 的路径参数行为不变。
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from django.test import TestCase

from app_store.install_utils import ValidateInstallService
from app_store.new_install_utils import (
    ValidateInstallService as NewValidateInstallService,
    ValidateInstallServicePortArgs,
)

IP = "10.10.20.1"
DATA_PATH = "/data"


class CheckServiceArgsDirKeyBase(TestCase):
    """ 公共：mock SaltClient，路径探测可控 """

    def _check(self, validator_cls, args, salt_returns):
        validator = validator_cls(
            data=[{"ip": IP, "install_args": args, "ports": []}])
        with mock.patch(
                f"{validator_cls.__module__}.SaltClient") as mock_salt:
            mock_salt.return_value.cmd.side_effect = salt_returns
            result = validator.check_service_args(
                app_install_args=args,
                data_path=DATA_PATH,
                ip=IP)
        return result


class OldChainDirKeyTestCase(CheckServiceArgsDirKeyBase):
    """ 老链路 install_utils.ValidateInstallService.check_service_args """

    def test_null_dir_key_arg_default_not_rewritten(self):
        """ dir_key 为 null 的非路径参数（run_user）不被拼成路径（RED 用例）"""
        args = [{"key": "run_user", "name": "运行用户",
                 "dir_key": None, "default": "common"}]
        result = self._check(
            ValidateInstallService, args, salt_returns=[(True, "OK")])
        self.assertEqual(result[0]["default"], "common")
        # 未做路径检查 → 不落 check_flag/check_msg
        self.assertNotIn("check_flag", result[0])
        self.assertNotIn("check_msg", result[0])

    def test_empty_string_dir_key_arg_default_not_rewritten(self):
        """ dir_key 为空串同样不算路径参数 """
        args = [{"key": "run_user", "name": "运行用户",
                 "dir_key": "", "default": "common"}]
        result = self._check(
            ValidateInstallService, args, salt_returns=[(True, "OK")])
        self.assertEqual(result[0]["default"], "common")

    def test_missing_dir_key_arg_untouched(self):
        """ 缺 dir_key 键的参数保持原值（存量行为） """
        args = [{"key": "max_memory", "name": "最大内存",
                 "default": "4G"}]
        result = self._check(
            ValidateInstallService, args, salt_returns=[(True, "OK")])
        self.assertEqual(result[0]["default"], "4G")

    def test_truthy_dir_key_path_arg_still_joined(self):
        """ 带真值 dir_key 的路径参数仍拼 data_path 并做路径检查（回归）"""
        args = [{"key": "base_dir", "name": "安装目录",
                 "dir_key": "{data_path}", "default": "/jdk"}]
        result = self._check(
            ValidateInstallService, args, salt_returns=[(True, "OK")])
        self.assertEqual(result[0]["default"], os.path.join(DATA_PATH, "jdk"))
        self.assertTrue(result[0]["check_flag"])
        self.assertEqual(result[0]["check_msg"], "success")


class NewChainDirKeyTestCase(CheckServiceArgsDirKeyBase):
    """ 新链路 new_install_utils.ValidateInstallService.check_service_args """

    def test_null_dir_key_arg_skips_path_check(self):
        """ dir_key 为 null 的参数跳过路径存在性检查（RED 用例）

        salt 返回 EXISTS（路径已存在）时也不应误报——该参数不是路径。
        """
        args = [{"key": "run_user", "name": "运行用户",
                 "dir_key": None, "default": "common"}]
        result = self._check(
            NewValidateInstallService, args,
            salt_returns=[(True, "EXISTS")])
        self.assertEqual(result[0]["default"], "common")
        self.assertNotIn("error_msg", result[0])
        self.assertNotIn("check_flag", result[0])

    def test_truthy_dir_key_path_arg_checked(self):
        """ 带真值 dir_key 的路径参数仍做路径存在性检查（回归）"""
        args = [{"key": "base_dir", "name": "安装目录",
                 "dir_key": "{data_path}", "default": "/data/jdk"}]
        result = self._check(
            NewValidateInstallService, args,
            salt_returns=[(True, "EXISTS")])
        self.assertFalse(result[0]["check_flag"])
        self.assertIn("已存在", result[0]["error_msg"])


class PortArgsDirKeyTestCase(CheckServiceArgsDirKeyBase):
    """ 新 schema 校验 ValidateInstallServicePortArgs.check_service_args """

    def test_null_dir_key_arg_skips_path_check(self):
        """ dir_key 为 null 的参数跳过路径检查与误报（RED 用例）"""
        args = [{"key": "run_user", "name": "运行用户",
                 "dir_key": None, "default": "common"}]
        result = self._check(
            ValidateInstallServicePortArgs, args,
            salt_returns=[(True, "EXISTS")])
        self.assertEqual(result[0]["default"], "common")
        self.assertNotIn("error_msg", result[0])
        self.assertNotIn("check_flag", result[0])

    def test_truthy_dir_key_path_arg_checked(self):
        """ 带真值 dir_key 的路径参数仍做路径检查（回归）"""
        args = [{"key": "base_dir", "name": "安装目录",
                 "dir_key": "{data_path}", "default": "/data/jdk"}]
        result = self._check(
            ValidateInstallServicePortArgs, args,
            salt_returns=[(True, "EXISTS")])
        self.assertFalse(result[0]["check_flag"])
        self.assertIn("已存在", result[0]["error_msg"])
