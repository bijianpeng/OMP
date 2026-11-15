# -*- coding: utf-8 -*-
"""
应用商店卡片"已安装数量"按环境隔离统计（多环境验收反馈修复）

覆盖：
1. 组件卡片：两环境各装同名组件服务，instance_number 只计本环境；
2. 产品卡片：两环境各建产品实例，instance_number 只计本环境；
3. 创建点落 env：
   a. 快速部署导入（app_store/views.py 批量创建产品实例）→ env=请求环境；
   b. 旧链路 CreateInstallPlan.create_product_instance（install_utils）
      → env=主机环境，get_or_create 查重含 env（跨环境同名实例不冲突）；
   c. 新链路 CreateInstallPlan.create_product_instance（new_install_utils）
      → 同 b；
4. 卸载清理产品实例按环境收敛：删 B 环境最后服务只清 B 环境实例，
   其他环境实例保留（否则计数长期虚高）。

测试基建说明：同 tests/test_app_store/test_env.py——继承 BaseTest（非
AutoLoginTest），显式放开本文件涉及视图的认证与权限；本地无 Redis，
涉及 DataJson / BaseRedisData / PrometheusUtils / SaltClient 处均 mock。
"""
import json
from unittest import mock

import pytest

from rest_framework.permissions import AllowAny
from rest_framework.reverse import reverse

from tests.base import BaseTest
from db_models.models import (
    Env, Host, Service, ApplicationHub, ProductHub, Product)
from app_store import views as app_store_views
from app_store.install_utils import CreateInstallPlan as OldCreateInstallPlan
from app_store.new_install_utils import (
    CreateInstallPlan as NewCreateInstallPlan)
from services.tasks import exec_action


def make_host(ip, env, instance_name=None):
    """ 直接落库一台指定环境的主机 """
    return Host.objects.create(
        instance_name=instance_name or ip, ip=ip,
        username="root", password="pwd", operate_system="CentOS",
        env=env)


def make_component(name, version="1.0.0"):
    """ 直接落库一个已发布组件（应用商店卡片数据源） """
    return ApplicationHub.objects.create(
        is_release=True, app_type=ApplicationHub.APP_TYPE_COMPONENT,
        app_name=name, app_version=version, app_port=json.dumps([]),
        app_dependence=None, app_install_args=json.dumps([]),
        app_controllers=json.dumps({"start": "./start.sh"}),
        extend_fields={}, is_base_env=False)


def make_service_app(name, product, version="1.0.0"):
    """ 直接落库一个已发布自研服务应用（挂在产品下） """
    return ApplicationHub.objects.create(
        is_release=True, app_type=ApplicationHub.APP_TYPE_SERVICE,
        app_name=name, app_version=version, app_port=json.dumps([]),
        app_dependence=None, app_install_args=json.dumps([]),
        app_controllers=json.dumps({"start": "./start.sh"}),
        extend_fields={}, is_base_env=False, product=product)


def make_product_hub(name, version="1.0.0"):
    """ 直接落库一个已发布产品（应用商店产品卡片数据源） """
    return ProductHub.objects.create(
        is_release=True, pro_name=name, pro_version=version)


def find_card_item(items, name, name_field):
    """ 在卡片列表中按名称定位条目 """
    matched = [it for it in items if it.get(name_field) == name]
    assert len(matched) == 1, f"卡片 {name} 应唯一存在: {items}"
    return matched[0]


@pytest.mark.django_db
class StoreCountsEnvTest(BaseTest):
    """ 应用商店"已安装数量"环境隔离行为 """

    def setUp(self):
        super(StoreCountsEnvTest, self).setUp()
        # 显式放开本文件涉及视图的认证与权限（说明同 test_env.py）
        for view_cls in (
                app_store_views.ComponentListView,
                app_store_views.ServiceListView,
                app_store_views.DeploymentPlanImportView):
            view_cls.authentication_classes = []
            view_cls.permission_classes = [AllowAny]
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")
        self.component_list_url = reverse("components-list")
        self.service_list_url = reverse("appServices-list")
        self.plan_import_url = reverse("deploymentPlanImport-list")

    def _get_card_items(self, url, env_id):
        headers = {} if env_id is None else {"HTTP_X_ENV_ID": str(env_id)}
        resp = self.client.get(url, **headers).json()
        self.assertEqual(resp.get("code"), 0)
        data = resp.get("data")
        return data.get("results") if isinstance(data, dict) else data

    # ------------------------------------------------------------------
    # 1. 组件卡片计数按环境隔离
    # ------------------------------------------------------------------
    def test_component_card_count_isolated_by_env(self):
        """ 两环境各装同名组件服务，组件卡片只计本环境实例 """
        app_obj = make_component("cnt-comp")
        for env in (self.env_default, self.env_default, self.env_b):
            Service.objects.create(
                ip="10.10.0.%s" % env.id,
                service_instance_name=f"cnt-comp-{env.id}-{Service.objects.count()}",
                service=app_obj, env=env)

        item_default = find_card_item(
            self._get_card_items(self.component_list_url, self.env_default.id),
            "cnt-comp", "app_name")
        self.assertEqual(item_default.get("instance_number"), 2)

        item_b = find_card_item(
            self._get_card_items(self.component_list_url, self.env_b.id),
            "cnt-comp", "app_name")
        self.assertEqual(item_b.get("instance_number"), 1)

        # 未携带环境标识：pytest 注入 default 环境，口径同 default
        item_none = find_card_item(
            self._get_card_items(self.component_list_url, None),
            "cnt-comp", "app_name")
        self.assertEqual(item_none.get("instance_number"), 2)

    # ------------------------------------------------------------------
    # 2. 产品卡片计数按环境隔离
    # ------------------------------------------------------------------
    def test_product_card_count_isolated_by_env(self):
        """ 两环境各建产品实例，产品卡片只计本环境实例 """
        pro_obj = make_product_hub("cnt-pro")
        Product.objects.create(
            product_instance_name="cnt-pro-default",
            product=pro_obj, env=self.env_default)
        Product.objects.create(
            product_instance_name="cnt-pro-b-1", product=pro_obj, env=self.env_b)
        Product.objects.create(
            product_instance_name="cnt-pro-b-2", product=pro_obj, env=self.env_b)

        item_default = find_card_item(
            self._get_card_items(self.service_list_url, self.env_default.id),
            "cnt-pro", "pro_name")
        self.assertEqual(item_default.get("instance_number"), 1)

        item_b = find_card_item(
            self._get_card_items(self.service_list_url, self.env_b.id),
            "cnt-pro", "pro_name")
        self.assertEqual(item_b.get("instance_number"), 2)

    # ------------------------------------------------------------------
    # 3a. 创建点：快速部署导入批量创建产品实例落请求环境
    # ------------------------------------------------------------------
    def test_product_created_with_request_env_on_import(self):
        """ 导入链路批量创建产品实例：env=请求环境，卡片计数随之隔离 """
        make_host("192.0.2.120", self.env_b, "host-b")
        pro_obj = make_product_hub("import-pro")
        make_service_app("import-app", pro_obj)
        payload = {
            "instance_info_ls": [{"instance_name": "host-b",
                                  "run_user": ""}],
            "service_data_ls": [{"instance_name": "host-b",
                                 "service_name": "import-app",
                                 "vip": None, "role": None,
                                 "memory": ""}],
        }
        with mock.patch("app_store.views.DataJson"):
            resp = self.client.post(
                self.plan_import_url, data=json.dumps(payload),
                content_type="application/json; charset=utf-8",
                HTTP_X_ENV_ID=str(self.env_b.id)).json()
        self.assertEqual(resp.get("code"), 0)

        pi = Product.objects.get(product=pro_obj)
        self.assertEqual(pi.env, self.env_b)
        # 产品卡片在 B 环境计数为 1，default 环境不可见
        item_b = find_card_item(
            self._get_card_items(self.service_list_url, self.env_b.id),
            "import-pro", "pro_name")
        self.assertEqual(item_b.get("instance_number"), 1)
        item_default = find_card_item(
            self._get_card_items(self.service_list_url, self.env_default.id),
            "import-pro", "pro_name")
        self.assertEqual(item_default.get("instance_number"), 0)

    # ------------------------------------------------------------------
    # 3b. 创建点：旧链路 create_product_instance 继承主机环境
    # ------------------------------------------------------------------
    def test_old_chain_create_product_instance_inherits_host_env(self):
        """ 旧链路：产品实例 env=主机环境；同名实例跨环境各建一行 """
        host_b = make_host("192.0.2.121", self.env_b)
        host_a = make_host("192.0.2.122", self.env_default)
        pro_obj = make_product_hub("old-pro")
        app_obj = make_service_app("old-app", pro_obj)

        dic_b = {"name": "old-app", "version": "1.0.0",
                 "ip": host_b.ip, "product_instance_name": "old-pi"}
        dic_a = {"name": "old-app", "version": "1.0.0",
                 "ip": host_a.ip, "product_instance_name": "old-pi"}
        OldCreateInstallPlan(
            install_data={"install_type": 0, "install_services": []},
            env=self.env_b).create_product_instance(dic_b)
        OldCreateInstallPlan(
            install_data={"install_type": 0, "install_services": []},
            env=self.env_default).create_product_instance(dic_a)

        pi_ls = Product.objects.filter(
            product_instance_name="old-pi").order_by("id")
        self.assertEqual(pi_ls.count(), 2)
        self.assertEqual(
            set(pi_ls.values_list("env", flat=True)),
            {self.env_default.id, self.env_b.id})
        self.assertEqual(app_obj.product, pro_obj)

    # ------------------------------------------------------------------
    # 3c. 创建点：新链路 create_product_instance 继承主机环境
    # ------------------------------------------------------------------
    def test_new_chain_create_product_instance_inherits_host_env(self):
        """ 新链路：产品实例 env=主机环境；同名实例跨环境各建一行 """
        host_b = make_host("192.0.2.123", self.env_b)
        host_a = make_host("192.0.2.124", self.env_default)
        pro_obj = make_product_hub("new-pro")
        make_service_app("new-app", pro_obj)

        redis_data = {"data": {"basic": [
            {"name": "new-pro", "version": "1.0.0",
             "cluster_name": "new-pi"}]}}

        def _create(ip, env):
            with mock.patch(
                    "app_store.new_install_utils.BaseRedisData") as brd:
                brd.return_value.get_step_3_checked_data.return_value = \
                    redis_data
                NewCreateInstallPlan(
                    all_install_service_lst=[], unique_key="uk-cnt-%s" % env.id,
                    env=env).create_product_instance(
                    {"name": "new-app", "version": "1.0.0", "ip": ip})

        _create(host_b.ip, self.env_b)
        _create(host_a.ip, self.env_default)

        pi_ls = Product.objects.filter(
            product_instance_name="new-pi").order_by("id")
        self.assertEqual(pi_ls.count(), 2)
        self.assertEqual(
            set(pi_ls.values_list("env", flat=True)),
            {self.env_default.id, self.env_b.id})

    # ------------------------------------------------------------------
    # 4. 卸载清理产品实例按环境收敛
    # ------------------------------------------------------------------
    @mock.patch(
        "promemonitor.prometheus_utils.PrometheusUtils.delete_service",
        return_value="")
    @mock.patch(
        "utils.plugin.salt_client.SaltClient",
        return_value="")
    def test_uninstall_cleans_product_instance_per_env(
            self, mock_salt, mock_prom_delete):
        """ 删 B 环境最后服务：仅清 B 环境产品实例，default 环境保留 """
        pro_obj = make_product_hub("clean-pro")
        app_obj = make_service_app("clean-app", pro_obj)
        Product.objects.create(
            product_instance_name="clean-pro-b", product=pro_obj,
            env=self.env_b)
        pi_default = Product.objects.create(
            product_instance_name="clean-pro-a", product=pro_obj,
            env=self.env_default)
        service_b = Service.objects.create(
            ip="10.11.0.2", service_instance_name="clean-app-b",
            service=app_obj, env=self.env_b,
            service_port=json.dumps([{"key": "service_port",
                                      "default": "18080"}]))
        service_a = Service.objects.create(
            ip="10.11.0.1", service_instance_name="clean-app-a",
            service=app_obj, env=self.env_default)

        exec_action("4", service_b.id, "admin")

        self.assertFalse(Service.objects.filter(id=service_b.id).exists())
        # B 环境实例连带清理；default 环境实例与其服务均保留
        self.assertFalse(Product.objects.filter(
            product_instance_name="clean-pro-b").exists())
        self.assertTrue(Product.objects.filter(
            id=pi_default.id).exists())
        self.assertTrue(Service.objects.filter(id=service_a.id).exists())
