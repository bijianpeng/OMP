# -*- coding: utf-8 -*-\n# !/usr/bin/python3
# -*-coding:utf-8-*-
# Author: omp
# CreateDate: 2021/10/28 4:59 下午
# Description:
from unittest import mock
# ӳٵAutoLoginTest
from tests.base import get_auto_login_test
AutoLoginTest = get_auto_login_test()
from rest_framework.reverse import reverse
from db_models.models import Env
from tests.test_inspection.inspection_mixin import InspectionHistoryMixin


class TestInspectionHistoryList(AutoLoginTest, InspectionHistoryMixin):
    def setUp(self):
        super(TestInspectionHistoryList, self).setUp()
        # BaseTest.setUp 已创建 default 环境（id=1），二次调用
        # create_default_env 会因已存在返回 None；巡检记录视图已按
        # 环境上下文过滤（Task 12），测试数据需落在 default 环境上
        self.env = Env.objects.get(id=1)

    def tearDown(self):
        super(TestInspectionHistoryList, self).tearDown()

    def test_history_list(self):
        # 未找?
        resp = self.get(reverse("history-list")).json()
        self.assertDictEqual(resp, {
            'code': 0,
            'message': 'success',
            'data': {'count': 0, 'next': None, 'previous': None, 'results': []}
        })

        # 查询成功
        self.get_inspection_history(self.env)
        resp = self.get(reverse("history-list")).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        self.assertTrue(resp.get("data") is not None)

    @mock.patch("inspection.tasks.get_prometheus_data.delay", return_value=True)
    def test_history_post(self, tasks):
        # 深度巡检
        data = {'env': 1,
                'execute_type': "man",
                'hosts': {},
                'inspection_name': "深度巡检",
                'inspection_operator': "admin",
                'inspection_status': '1',
                'inspection_type': "deep",
                'services': {}}
        resp = self.post(reverse("history-list"), data=data).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        self.assertTrue(resp.get("data") is not None)

        # 主机巡检
        data = {'env': 1,
                'execute_type': "man",
                'hosts': ["10.0.9.67"],
                'inspection_name': "主机巡检",
                'inspection_operator': "admin",
                'inspection_status': '1',
                'inspection_type': "host",
                'services': {}}
        resp = self.post(reverse("history-list"), data=data).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        self.assertTrue(resp.get("data") is not None)

        # 组件巡检
        data = {'env': 1,
                'execute_type': "man",
                'hosts': {},
                'inspection_name': "组件巡检",
                'inspection_operator': "admin",
                'inspection_status': '1',
                'inspection_type': "service",
                'services': [8]}
        resp = self.post(reverse("history-list"), data=data).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        self.assertTrue(resp.get("data") is not None)
