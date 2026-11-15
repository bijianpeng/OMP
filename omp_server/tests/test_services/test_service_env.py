# -*- coding: utf-8 -*-
"""
services / 自愈模块环境上下文接入测试（多环境架构 Task 8）

覆盖：
1. 服务列表按当前环境上下文过滤（Service 自有 env FK 直接过滤，两环境数据隔离）；
   服务详情对本环境外服务（伪造 id）404（列表 queryset 统一闸门）
2. 自愈策略设置 per-env：GET 无行时按当前环境 get_or_create；PUT 只影响本
   环境行、跨环境 pk 404；POST 强制继承请求环境（不接受客户端 env 值）
3. 自愈历史记录列表按当前环境过滤

测试基建说明：同 tests/test_hosts/test_host_env.py——继承 BaseTest（非
AutoLoginTest），显式放开本文件涉及视图的认证与权限，规避模块导入顺序
差异；EnvContextMiddleware 对匿名用户（cookie 无法解析）放行环境授权，
显式 X-Env-Id 仍走完整环境解析链，request.env 为 header 指定环境。
"""
from unittest import mock

import pytest

from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse

from tests.base import BaseTest
from db_models.models import (
    Env, Service, SelfHealingSetting, SelfHealingHistory, ApplicationHub
)
from services import views as services_views
from services import self_heal_view as self_heal_views
from promemonitor.prometheus import Prometheus


def make_service(app, instance_name, ip, env):
    """ 直接落库一个指定环境的服务实例（关联同一 app，无 cluster） """
    return Service.objects.create(
        service_instance_name=instance_name,
        ip=ip,
        service_status=Service.SERVICE_STATUS_NORMAL,
        service=app,
        env=env,
    )


@pytest.mark.django_db
class ServiceEnvContextTest(BaseTest):
    """ services / 自愈模块环境上下文行为 """

    def setUp(self):
        super(ServiceEnvContextTest, self).setUp()
        # 显式放开本文件涉及视图的认证与权限（说明同 hosts 环境测试）：
        # PYTEST_CURRENT_TEST 的放开依赖 import 时机，直接作用到具体视图类，
        # 顺序无关。
        for view_cls in (services_views.ServiceListView,
                         services_views.ServiceDetailView,
                         self_heal_views.SelfHealingSettingView,
                         self_heal_views.ListSelfHealingHistoryView):
            view_cls.authentication_classes = []
            view_cls.permission_classes = [AllowAny]
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")
        # 列表 serializer 的 label_name 依赖 Service.service（ApplicationHub），
        # 两环境服务共用同一 app
        self.app = ApplicationHub.objects.create(
            app_name="t_env_app", app_version="1.0",
            app_type=ApplicationHub.APP_TYPE_COMPONENT,
            is_release=True, is_base_env=False,
            extend_fields={"base_env": False, "affinity": ""})
        self.service_list_url = reverse("services-list")
        self.setting_list_url = reverse("SelfHealingSetting-list")
        self.history_list_url = reverse("ListSelfHealingHistory-list")

    def test_service_list_filtered_by_env(self):
        """ 两环境各 1 服务：带 B 环境标识只见 B 服务；无标识（pytest 注入
            default）只见 default 服务；跨环境服务详情 404 """
        service_a = make_service(
            self.app, "svc_env_default", "10.10.0.1", self.env_default)
        service_b = make_service(
            self.app, "svc_env_b", "10.10.0.2", self.env_b)

        with mock.patch.object(
                Prometheus, "get_all_service_status",
                return_value=(False, {})), \
            mock.patch.object(
                Prometheus, "get_service_info", side_effect=lambda x: x):
            # 显式 B 环境上下文：仅见 B 服务
            resp = self.client.get(
                self.service_list_url,
                HTTP_X_ENV_ID=str(self.env_b.id))
            self.assertEqual(resp.status_code, 200)
            resp_json = resp.json()
            self.assertEqual(resp_json.get("code"), 0)
            results = resp_json.get("data").get("results")
            self.assertEqual(
                [s.get("service_instance_name") for s in results],
                [service_b.service_instance_name])

            # 未携带标识（pytest 注入 default 环境）：仅见 default 服务
            resp_default = self.client.get(self.service_list_url)
            self.assertEqual(resp_default.status_code, 200)
            results_default = resp_default.json().get("data").get("results")
            self.assertEqual(
                [s.get("service_instance_name") for s in results_default],
                [service_a.service_instance_name])

        # 跨环境服务详情：B 环境上下文访问 default 环境服务 -> 统一包
        # 错误响应（全局异常处理器把 Http404 转 200 body + code=1）
        detail_url = reverse("services-detail", args=[service_a.id])
        resp_detail = self.client.get(
            detail_url, HTTP_X_ENV_ID=str(self.env_b.id))
        self.assertEqual(resp_detail.status_code, 200)
        resp_detail_json = resp_detail.json()
        self.assertEqual(resp_detail_json.get("code"), 1)
        self.assertIsNone(resp_detail_json.get("data"))
        # 本环境服务详情正常
        resp_detail_ok = self.client.get(
            reverse("services-detail", args=[service_b.id]),
            HTTP_X_ENV_ID=str(self.env_b.id))
        self.assertEqual(resp_detail_ok.status_code, 200)
        self.assertEqual(resp_detail_ok.json().get("code"), 0)

    def test_self_heal_setting_per_env(self):
        """ 自愈策略设置 per-env：GET 无行时按当前环境 get_or_create 默认行；
            两环境 GET / PUT 互不影响；跨环境 pk PUT 404；POST 强制继承
            请求环境（忽略客户端 env 值） """
        # 初始无任何设置行
        self.assertEqual(SelfHealingSetting.objects.count(), 0)

        # B 环境首次 GET：无行则 get_or_create 出 B 环境默认行
        resp_b = self.client.get(
            self.setting_list_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        self.assertEqual(len(resp_b.get("data")), 1)
        setting_b = SelfHealingSetting.objects.filter(
            env=self.env_b).first()
        self.assertIsNotNone(setting_b)
        self.assertFalse(setting_b.used)
        self.assertEqual(setting_b.repair_instance, [])

        # default 环境首次 GET（无标识，pytest 注入）：get_or_create 出
        # default 环境默认行，两环境行相互独立
        resp_default = self.client.get(self.setting_list_url).json()
        self.assertEqual(resp_default.get("code"), 0)
        self.assertEqual(len(resp_default.get("data")), 1)
        setting_default = SelfHealingSetting.objects.filter(
            env=self.env_default).first()
        self.assertIsNotNone(setting_default)
        self.assertNotEqual(setting_b.id, setting_default.id)

        # B 环境上下文 PUT 本环境行：仅 B 行变化，default 行不受影响
        update_url_b = reverse(
            "SelfHealingSetting-detail", args=[setting_b.id])
        resp_put = self.client.put(
            update_url_b,
            data='{"used": true, "max_healing_count": 8, '
                 '"fresh_rate": 20, "instance_tp": 1, '
                 '"repair_instance": ["redis"]}',
            content_type="application/json; charset=utf-8",
            HTTP_X_ENV_ID=str(self.env_b.id))
        self.assertEqual(resp_put.status_code, 200)
        setting_b.refresh_from_db()
        setting_default.refresh_from_db()
        self.assertTrue(setting_b.used)
        self.assertEqual(setting_b.max_healing_count, 8)
        self.assertEqual(setting_b.repair_instance, ["redis"])
        self.assertFalse(setting_default.used)
        self.assertEqual(setting_default.max_healing_count, 5)

        # 再次 GET：各环境只见本环境行
        resp_b2 = self.client.get(
            self.setting_list_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(
            [row.get("id") for row in resp_b2.get("data")], [setting_b.id])
        resp_default2 = self.client.get(self.setting_list_url).json()
        self.assertEqual(
            [row.get("id") for row in resp_default2.get("data")],
            [setting_default.id])

        # 跨环境 pk：B 环境上下文 PUT default 环境行 -> 统一包错误响应
        # （全局异常处理器把 Http404 转 200 body + code=1）
        update_url_default = reverse(
            "SelfHealingSetting-detail", args=[setting_default.id])
        resp_cross = self.client.put(
            update_url_default,
            data='{"used": true}',
            content_type="application/json; charset=utf-8",
            HTTP_X_ENV_ID=str(self.env_b.id))
        self.assertEqual(resp_cross.status_code, 200)
        resp_cross_json = resp_cross.json()
        self.assertEqual(resp_cross_json.get("code"), 1)
        self.assertIsNone(resp_cross_json.get("data"))
        setting_default.refresh_from_db()
        self.assertFalse(setting_default.used)

        # POST 强制继承请求环境：客户端显式传其他环境的 env 值不被接受；
        # 每环境至多一行（Task 7b unique 约束）：B 已有行时重复创建被拒，
        # 换一个尚无配置行的环境 C 才能新建，且行归属 C
        resp_repeat = self.client.post(
            self.setting_list_url,
            data='{"used": false, "repair_instance": ["mysql"], '
                 '"env": %d}' % self.env_default.id,
            content_type="application/json; charset=utf-8",
            HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_repeat.get("code"), 1)

        env_c = Env.objects.create(name="测试环境C", code="envc")
        resp_create = self.client.post(
            self.setting_list_url,
            data='{"used": false, "repair_instance": ["mysql"], '
                 '"env": %d}' % self.env_default.id,
            content_type="application/json; charset=utf-8",
            HTTP_X_ENV_ID=str(env_c.id))
        self.assertEqual(resp_create.status_code, 201)
        created = SelfHealingSetting.objects.filter(
            repair_instance=["mysql"]).first()
        self.assertIsNotNone(created)
        self.assertEqual(created.env, env_c)

    def test_self_heal_history_filtered(self):
        """ 自愈历史记录：两环境各 1 条，列表按当前环境上下文过滤 """
        history_a = SelfHealingHistory.objects.create(
            host_ip="10.10.0.1", service_name="svc_default",
            instance_name="svc_env_default", env=self.env_default)
        history_b = SelfHealingHistory.objects.create(
            host_ip="10.10.0.2", service_name="svc_b",
            instance_name="svc_env_b", env=self.env_b)

        # 显式 B 环境上下文：仅见 B 记录
        resp_b = self.client.get(
            self.history_list_url, HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp_b.get("code"), 0)
        results_b = resp_b.get("data").get("results")
        self.assertEqual([r.get("id") for r in results_b], [history_b.id])

        # 未携带标识（pytest 注入 default 环境）：仅见 default 记录
        resp_default = self.client.get(self.history_list_url).json()
        self.assertEqual(resp_default.get("code"), 0)
        results_default = resp_default.get("data").get("results")
        self.assertEqual(
            [r.get("id") for r in results_default], [history_a.id])
