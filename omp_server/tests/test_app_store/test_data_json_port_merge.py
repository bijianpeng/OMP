# -*- coding: utf-8 -*-
"""
DataJson 生成 JSON 时,ports 必须合并到 install_args 末尾。

背景:hadoop3 重装时,目标机 install.py 用 self.install_args.get("nn_rpc_port")
取端口,但 OMP 生成的 JSON 中 install_args 数组并不含端口(端口在 ports 数组里),
导致 TypeError。

根因:Web 新装链路靠 new_install_serializers.check_error_msg 中
`lst = item.get("install_args", []); lst.extend(item.get("ports"))` 的引用
语义陷阱做合并;重装 / 升级 / 部署计划导入链路绕过该函数,JSON 中
install_args 不含 ports。

修复:在 DataJson 出口统一做合并(幂等),让所有路径生成的 JSON 一致。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from django.test import SimpleTestCase

from app_store.new_install_utils import merge_ports_into_install_args


class TestMergePortsIntoInstallArgs(SimpleTestCase):
    """merge_ports_into_install_args 纯函数单元测试"""

    def test_merge_when_install_args_has_no_port(self):
        """重装场景:install_args 不含端口 → 合并后应含所有 ports"""
        install_args = [
            {"key": "base_dir", "default": "/opt/x"},
            {"key": "log_dir", "default": "/opt/x/logs"},
        ]
        ports = [
            {"key": "service_port", "default": "8020", "protocol": "TCP"},
        ]
        result = merge_ports_into_install_args(install_args, ports)
        keys = [el["key"] for el in result]
        self.assertEqual(keys, ["base_dir", "log_dir", "service_port"])

    def test_idempotent_when_already_merged(self):
        """幂等性:Web 新装链路 check_error_msg 已把 ports 合并进 install_args,
        再次合并不应重复(按 key 去重)"""
        install_args = [
            {"key": "base_dir", "default": "/opt/x"},
            {"key": "service_port", "default": "8020"},
        ]
        ports = [
            {"key": "service_port", "default": "8020", "protocol": "TCP"},
        ]
        result = merge_ports_into_install_args(install_args, ports)
        keys = [el["key"] for el in result]
        self.assertEqual(keys, ["base_dir", "service_port"])

    def test_empty_install_args(self):
        """install_args 为空 → 全部 ports 合并"""
        install_args = []
        ports = [{"key": "service_port", "default": "8020"}]
        result = merge_ports_into_install_args(install_args, ports)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "service_port")

    def test_empty_ports(self):
        """ports 为空 → install_args 不变"""
        install_args = [{"key": "base_dir", "default": "/opt/x"}]
        ports = []
        result = merge_ports_into_install_args(install_args, ports)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["key"], "base_dir")

    def test_both_empty(self):
        """两者都空 → 返回空 list"""
        result = merge_ports_into_install_args([], [])
        self.assertEqual(result, [])

    def test_none_inputs(self):
        """None 入参应被视为空 list,不抛错"""
        result = merge_ports_into_install_args(None, None)
        self.assertEqual(result, [])

    def test_hadoop3_full_case(self):
        """hadoop3 多端口场景:验证所有端口都被合并(报错复现)"""
        install_args = [
            {"key": "base_dir", "default": "/opt/bigmw/hadoop3"},
            {"key": "data_dir", "default": "/opt/data/hadoop3"},
            {"key": "log_dir", "default": "/opt/bigmw/hadoop3/log"},
            {"key": "local_user", "default": ""},
            {"key": "local_password", "default": ""},
            {"key": "run_user", "default": "common"},
            {"key": "memory", "default": "2g"},
        ]
        ports = [
            {"key": "service_port", "default": "50070"},
            {"key": "nn_rpc_port", "default": "8020"},
            {"key": "dn_port", "default": "50010"},
            {"key": "dn_heartbeat_port", "default": "50020"},
            {"key": "sn_ui_port", "default": "50090"},
            {"key": "jobhistory_port", "default": "10020"},
            {"key": "jobhistory_ui_port", "default": "19888"},
        ]
        result = merge_ports_into_install_args(install_args, ports)
        keys = {el["key"] for el in result}
        # install.py 取的所有端口字段都必须在合并后的 install_args 中
        for port_key in ("nn_rpc_port", "sn_ui_port", "service_port",
                         "jobhistory_port", "jobhistory_ui_port"):
            self.assertIn(port_key, keys,
                          f"{port_key} 应在合并后的 install_args 中")
        # 长度 = 原 install_args + 所有 ports(无重复)
        self.assertEqual(
            len(result), len(install_args) + len(ports))

    def test_does_not_mutate_input_install_args(self):
        """入参 install_args 不应被修改(避免 check_error_msg 那种副作用陷阱)"""
        install_args = [{"key": "base_dir"}]
        ports = [{"key": "service_port"}]
        merge_ports_into_install_args(install_args, ports)
        self.assertEqual(
            len(install_args), 1,
            "入参 install_args 不应被修改,但实际被改了")

    def test_does_not_mutate_input_ports(self):
        """入参 ports 不应被修改"""
        install_args = [{"key": "base_dir"}]
        ports = [{"key": "service_port"}]
        merge_ports_into_install_args(install_args, ports)
        self.assertEqual(
            len(ports), 1, "入参 ports 不应被修改,但实际被改了")

    def test_install_args_priority_on_conflict(self):
        """key 冲突时,install_args 中的项优先(保留用户填的值)"""
        install_args = [{"key": "service_port", "default": "9999"}]
        ports = [{"key": "service_port", "default": "8020"}]
        result = merge_ports_into_install_args(install_args, ports)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["default"], "9999",
                         "install_args 中的值应优先")

    def test_skip_non_dict_items(self):
        """跳过非 dict 元素,不抛错"""
        install_args = [{"key": "base_dir"}, None, "garbage"]
        ports = [{"key": "service_port"}, None]
        result = merge_ports_into_install_args(install_args, ports)
        keys = [el["key"] for el in result if isinstance(el, dict)]
        self.assertEqual(keys, ["base_dir", "service_port"])

    def test_skip_items_without_key(self):
        """跳过没有 key 字段的项"""
        install_args = [{"key": "base_dir"}, {"default": "no-key"}]
        ports = [{"key": "service_port"}, {"default": "no-key"}]
        result = merge_ports_into_install_args(install_args, ports)
        keys = [el.get("key") for el in result]
        self.assertEqual(keys, ["base_dir", "service_port"])
