# -*- coding: utf-8 -*-
"""
tool 模块环境上下文接入测试（多环境架构 Task 13）

覆盖：
1. 工具执行历史列表按当前环境过滤；跨环境执行结果详情（按 id 查看）
   走过滤 queryset -> 统一包 code=1（工具列表本身保持全局，不在本文件
   断言范围内）
2. 发起工具执行：ToolExecuteMainHistory 写入当前环境（请求体伪造 env
   不在序列化字段内，天然无效）

测试基建说明：同 tests/test_backups/test_env.py——继承 BaseTest（非
AutoLoginTest），显式放开本文件涉及视图的认证与权限。
"""
import json
from unittest import mock

import pytest

from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse

from tests.base import BaseTest
from db_models.models import (
    Env, Host, ToolInfo, ToolExecuteMainHistory, ToolExecuteDetailHistory)
from tool import views as tool_views


def make_tool():
    """ 直接落库一个主机目标工具（无自定义参数） """
    return ToolInfo.objects.create(
        name="env_check", kind=ToolInfo.KIND_CHECK,
        script_type=ToolInfo.SCRIPT_TYPE_SHELL, target_name="host",
        source_package_path="tool/tar/env_check.tar.gz",
        tool_folder_path="tool/folder/env_check",
        script_path="env_check.sh",
        send_package=[], template_filepath=[], obj_connection_args=[],
        script_args=[], output=ToolInfo.OUTPUT_TERMINAL,
        description="环境上下文测试工具")


def make_history(tool, task_name, env, target_ip):
    """ 直接落库一条指定环境的工具执行记录（含执行明细） """
    history = ToolExecuteMainHistory.objects.create(
        tool=tool, task_name=task_name, operator="admin", env=env)
    ToolExecuteDetailHistory.objects.create(
        main_history=history, target_ip=target_ip,
        run_user="root", time_out=60, execute_args={}, execute_log="")
    return history


@pytest.mark.django_db
class ToolEnvContextTest(BaseTest):
    """ tool 模块环境上下文行为 """

    def setUp(self):
        super(ToolEnvContextTest, self).setUp()
        # 显式放开本文件涉及视图的认证与权限（说明同 backups 环境测试）
        for view_cls in (tool_views.ToolExecuteHistoryListApiView,
                         tool_views.GetToolDetailView,
                         tool_views.ToolFormAnswerAPIView):
            view_cls.authentication_classes = []
            view_cls.permission_classes = [AllowAny]
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")
        self.tool = make_tool()
        self.history_url = reverse("execute-history")

    def test_tool_history_filtered_and_written(self):
        """ 执行历史两环境各 1 条：列表按当前环境过滤，跨环境结果详情
            code=1；发起执行写入当前环境（body 伪造 env 无效） """
        history_a = make_history(
            self.tool, "task-default", self.env_default, "10.10.0.1")
        history_b = make_history(
            self.tool, "task-b", self.env_b, "10.10.0.2")

        # 列表过滤：B 上下文仅见 B 记录；无标识（pytest 注入 default）
        # 仅见 default 记录
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

        # 执行结果按 id 查看：B 上下文访问 default 记录 -> 统一包 code=1；
        # 本环境记录正常
        resp_cross = self.client.get(
            reverse("result-detail", args=[history_a.id]),
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_cross.get("code"), 1)
        self.assertIsNone(resp_cross.get("data"))
        resp_own = self.client.get(
            reverse("result-detail", args=[history_b.id]),
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_own.get("code"), 0)

        # 发起执行：ToolExecuteMainHistory 写入当前环境
        host = Host.objects.create(
            instance_name="host-b", ip="10.10.0.9", port=22,
            username="root", password="pwd", data_folder="/data",
            operate_system="CentOS", host_agent=str(Host.AGENT_RUNNING),
            env=self.env_b)
        with mock.patch("tool.serializers.exec_tools_main.delay"):
            resp_create = self.client.post(
                reverse("answer", args=[self.tool.id]),
                data=json.dumps({
                    "default_form": {
                        "task_name": "task-exec-b",
                        "target_objs": [{"id": host.id, "ip": host.ip}],
                        "runuser": "root",
                        "timeout": 60
                    },
                    # 请求体伪造 env 不在序列化字段内，天然无效
                    "env": self.env_default.id,
                }),
                content_type="application/json",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_create.get("code"), 0)
        created = ToolExecuteMainHistory.objects.exclude(
            id__in=[history_a.id, history_b.id]).first()
        self.assertIsNotNone(created)
        self.assertEqual(created.env, self.env_b)
