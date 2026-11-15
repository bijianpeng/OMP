# -*- coding: utf-8 -*-\n# !/usr/bin/python3
# -*-coding:utf-8-*-
# Author: omp
# CreateDate: 2021/10/28 4:59 下午
# Description:
# ӳٵAutoLoginTest
from tests.base import get_auto_login_test
AutoLoginTest = get_auto_login_test()
from rest_framework.reverse import reverse
from db_models.models import Env
from tests.test_inspection.inspection_mixin import InspectionReportMixin


class TestInspectionReportList(AutoLoginTest, InspectionReportMixin):
    def setUp(self):
        super(TestInspectionReportList, self).setUp()
        # BaseTest.setUp 已创建 default 环境（id=1），二次调用
        # create_default_env 会因已存在返回 None；巡检报告视图已按
        # 环境上下文校验巡检记录归属（Task 12），测试数据需落在
        # default 环境上
        self.env = Env.objects.get(id=1)

    def tearDown(self):
        super(TestInspectionReportList, self).tearDown()

    def test_crontab_read(self):
        inst_id = self.create_inspection_report(self.env)
        self.update_inspection_report(inst_id=inst_id)
        resp = self.get(
            f"/api/inspection/report/{inst_id}/", data={'inst_id': inst_id}
        ).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        self.assertTrue(resp.get("data") is not None)
