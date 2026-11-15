import random
from types import SimpleNamespace
from django.db.models import Max
from rest_framework.reverse import reverse

from tests.base import AutoLoginTest
from tests.mixin import (
    ApplicationResourceMixin, ProductResourceMixin
)
from db_models.models import (
    Labels, ApplicationHub
)


class FakeCountQueryset(list):
    """ 模拟 queryset：instance_number 走 .count() 而非 len() """
    def count(self):
        return len(self)


class LabelListTest(AutoLoginTest, ApplicationResourceMixin):
    """ 标签列表测试类 """

    def setUp(self):
        super(LabelListTest, self).setUp()
        self.label_list_url = reverse("labels-list")
        self.get_application()

    def tearDown(self):
        super(LabelListTest, self).tearDown()
        self.destroy_application()

    def test_label_list(self):
        """ 测试标签列表 """

        # 查询标签列表 -> 返回所有标签列表数据
        resp = self.get(self.label_list_url).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")

        # 查询指定类型标签 -> 返回指定类型标签列表数据
        choice = random.choice(Labels.LABELS_CHOICES)
        resp = self.get(self.label_list_url, {
            "label_type": choice[0]
        }).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        self.assertEqual(
            set(resp.get("data")),
            set(Labels.objects.filter(
                label_type=choice[0],
                applicationhub__app_type=ApplicationHub.APP_TYPE_COMPONENT
            ).order_by("id").values_list("label_name", flat=True).distinct())
        )


class ComponentListTest(AutoLoginTest, ApplicationResourceMixin):
    """ 基础组件列表测试类 """

    def setUp(self):
        super(ComponentListTest, self).setUp()
        self.component_list_url = reverse("components-list")
        self.app_obj_ls = self.get_application()

    def tearDown(self):
        super(ComponentListTest, self).tearDown()
        self.destroy_application()

    def test_component_list_filter(self):
        """ 测试基础组件列表过滤 """

        # 查询组件列表 -> 按名称合并展示所有已发布组件
        resp = self.get(self.component_list_url).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        comp_set = set(self.app_obj_ls.filter(
            is_release=True,
            app_type=ApplicationHub.APP_TYPE_COMPONENT
        ).values_list("app_name"))
        self.assertEqual(resp.get("data").get("count"), len(comp_set))

        # 组件名过滤 -> 展示组件名模糊匹配项
        resp = self.get(self.component_list_url, {
            "app_name": "app_1"
        }).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        comp_set = set(self.app_obj_ls.filter(
            is_release=True,
            app_type=ApplicationHub.APP_TYPE_COMPONENT,
            app_name__contains="app_1",
        ).values_list("app_name"))
        self.assertEqual(resp.get("data").get("count"), len(comp_set))

        # 标签类型过滤 -> 展示标签名匹配项
        label_name = random.choice(Labels.LABELS_CHOICES)[1]
        resp = self.get(self.component_list_url, {
            "type": label_name
        }).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        comp_set = set(self.app_obj_ls.filter(
            is_release=True,
            app_type=ApplicationHub.APP_TYPE_COMPONENT,
            app_labels__label_name=label_name,
        ).values_list("app_name"))
        self.assertEqual(resp.get("data").get("count"), len(comp_set))

    def test_component_list_order(self):
        """ 测试基础组建列表排序 """

        # 查询组件列表 -> 各组件返回最新数据，按照创建时间排序
        resp = self.get(self.component_list_url).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        obj_ls = list(self.app_obj_ls.filter(
            is_release=True,
            app_type=ApplicationHub.APP_TYPE_COMPONENT
        ).values("app_name").annotate(c=Max("created")).order_by(
            "-created").values_list("app_name", flat=True))
        target_ls = []
        for obj in obj_ls:
            if obj not in target_ls:
                target_ls.append(obj)
            if len(target_ls) == 10:
                break
        result_ls = list(map(
            lambda x: x.get("app_name"),
            resp.get("data").get("results")))
        self.assertEqual(result_ls, target_ls)


class ServiceListTest(AutoLoginTest, ProductResourceMixin):
    """ 产品列表测试类 """

    def setUp(self):
        super(ServiceListTest, self).setUp()
        self.service_list_url = reverse("appServices-list")
        self.service_obj_ls = self.get_product()

    def tearDown(self):
        super(ServiceListTest, self).tearDown()
        self.destroy_product()

    def test_service_list_filter(self):
        """ 测试应用服务列表过滤 """

        # 查询服务列表 -> 按名称合并展示所有已发布服务
        resp = self.get(self.service_list_url).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        service_set = set(self.service_obj_ls.filter(
            is_release=True
        ).values_list("pro_name"))
        self.assertEqual(resp.get("data").get("count"), len(service_set))

        # 服务名过滤 -> 展示服务名模糊匹配项
        resp = self.get(self.service_list_url, {
            "pro_name": "pro_1"
        }).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        service_set = set(self.service_obj_ls.filter(
            is_release=True,
            pro_name__contains="pro_1",
        ).values_list("pro_name"))
        self.assertEqual(resp.get("data").get("count"), len(service_set))

        self.destroy_product()

    def test_service_list_order(self):
        """ 测试应用服务列表排序 """

        # 查询应用服务列表 -> 各组件返回最新数据，按照创建时间排序
        resp = self.get(self.service_list_url).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        obj_ls = list(self.service_obj_ls.filter(
            is_release=True,
        ).values("pro_name").annotate(c=Max("created")).order_by(
            "-created").values_list("pro_name", flat=True))
        target_ls = []
        for obj in obj_ls:
            if obj not in target_ls:
                target_ls.append(obj)
        result_ls = list(map(
            lambda x: x.get("pro_name"),
            resp.get("data").get("results")))
        self.assertEqual(result_ls, target_ls[:10])


class AppStoreDetailTest(AutoLoginTest, ApplicationResourceMixin, ProductResourceMixin):
    """ 应用商店组件和产品测试类 """

    def setUp(self):
        super(AppStoreDetailTest, self).setUp()
        self.application_detail_url = reverse("componentDetail-list")
        self.product_detail_url = reverse("appServiceDetail-list")

    def test_application_detail(self):
        """ 测试应用详情 """
        app_ls = self.get_application()

        # 查询应用表 -> 返回所指定应用名符合的数据
        resp = self.get(self.application_detail_url, {
            "app_name": random.choice(app_ls).app_name
        }).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        self.assertIsNotNone(resp.get('data'))

        self.destroy_application()

    def test_product_detail(self):
        """
        测试产品详情
        """
        pro_ls = self.get_product()

        resp = self.get(self.product_detail_url, {
            "pro_name": random.choice(pro_ls).pro_name
        }).json()
        self.assertEqual(resp.get("code"), 0)
        self.assertEqual(resp.get("message"), "success")
        self.assertIsNotNone(resp.get('data'))

        self.destroy_product()

# ================== app_store_filters.py 补全测试 ==================
import pytest
from app_store import app_store_filters
from db_models.models import Labels, ApplicationHub, ProductHub, UploadPackageHistory, MainInstallHistory, Service

def test_label_filter_fields():
    f = app_store_filters.LabelFilter()
    assert 'label_type' in f.get_fields()

def test_component_filter_fields():
    f = app_store_filters.ComponentFilter()
    assert 'app_name' in f.get_fields()
    assert 'type' in f.get_fields()

def test_service_filter_fields():
    f = app_store_filters.ServiceFilter()
    assert 'pro_name' in f.get_fields()
    assert 'type' in f.get_fields()

def test_upload_package_history_filter_fields():
    f = app_store_filters.UploadPackageHistoryFilter()
    assert 'operation_uuid' in f.get_fields()

def test_publish_package_history_filter_fields():
    f = app_store_filters.PublishPackageHistoryFilter()
    assert 'operation_uuid' in f.get_fields()

def test_component_entrance_filter_fields():
    f = app_store_filters.ComponentEntranceFilter()
    assert 'app_name' in f.get_fields()

def test_product_entrance_filter_fields():
    f = app_store_filters.ProductEntranceFilter()
    assert 'pro_name' in f.get_fields()

def test_install_history_filter_fields():
    f = app_store_filters.InstallHistoryFilter()
    assert 'operation_uuid' in f.get_fields()

def test_service_install_history_filter_fields():
    f = app_store_filters.ServiceInstallHistoryFilter()
    assert 'id' in f.get_fields()

# ================== app_store_serializers.py 补全测试 ==================
from app_store import app_store_serializers
from rest_framework.exceptions import ValidationError
from unittest import mock

def test_upload_package_serializer_validate(monkeypatch):
    s = app_store_serializers.UploadPackageSerializer()
    class DummyFile:
        name = 'test.tar'
        size = 100
        def chunks(self):
            yield b'data'
    attrs = {'file': DummyFile(), 'uuid': 'u', 'operation_user': 'o', 'md5': 'm'}
    assert s.validate(attrs) == attrs
    DummyFile.name = 'test.txt'
    with pytest.raises(ValidationError):
        s.validate(dict(attrs, file=DummyFile()))
    DummyFile.name = 'test.tar'
    DummyFile.size = 5 * 1024 * 1024 * 1024
    with pytest.raises(ValidationError):
        s.validate(dict(attrs, file=DummyFile()))

def test_remove_package_serializer_validate(monkeypatch):
    s = app_store_serializers.RemovePackageSerializer()
    class DummyQueryset:
        def exists(self): return True
        def __len__(self): return 1
        def update(self, **kwargs): pass
    monkeypatch.setattr('db_models.models.UploadPackageHistory.objects.filter', lambda **kwargs: DummyQueryset())
    attrs = {'uuid': 'u', 'package_names': ['a']}
    res = s.validate(attrs)
    assert 'queryset' in res
    class DummyQueryset2:
        def exists(self): return False
        def __len__(self): return 0
    monkeypatch.setattr('db_models.models.UploadPackageHistory.objects.filter', lambda **kwargs: DummyQueryset2())
    with pytest.raises(ValidationError):
        s.validate(attrs)

def test_component_list_serializer_get_instance_number(monkeypatch):
    # 多环境：计数按请求环境过滤，注入带 env 的请求上下文
    s = app_store_serializers.ComponentListSerializer(
        context={"request": SimpleNamespace(env=object())})
    monkeypatch.setattr('db_models.models.Service.objects.filter', lambda **kwargs: FakeCountQueryset([1,2,3]))
    class DummyObj: app_name = 'a'
    assert s.get_instance_number(DummyObj()) == 3

def test_service_list_serializer_get_instance_number(monkeypatch):
    # 多环境：计数按请求环境过滤，注入带 env 的请求上下文
    s = app_store_serializers.ServiceListSerializer(
        context={"request": SimpleNamespace(env=object())})
    monkeypatch.setattr('db_models.models.Product.objects.filter', lambda **kwargs: FakeCountQueryset([1,2]))
    class DummyObj: pass
    assert s.get_instance_number(DummyObj()) == 2

# ================== unittest风格补全 ==================
import unittest
from unittest import mock
from app_store import app_store_filters, app_store_serializers
from rest_framework.exceptions import ValidationError

class TestAppStoreFiltersUnittest(unittest.TestCase):
    def test_label_filter_fields(self):
        f = app_store_filters.LabelFilter()
        self.assertIn('label_type', f.get_fields())

    def test_component_filter_fields(self):
        f = app_store_filters.ComponentFilter()
        self.assertIn('app_name', f.get_fields())
        self.assertIn('type', f.get_fields())

    def test_service_filter_fields(self):
        f = app_store_filters.ServiceFilter()
        self.assertIn('pro_name', f.get_fields())
        self.assertIn('type', f.get_fields())

    def test_upload_package_history_filter_fields(self):
        f = app_store_filters.UploadPackageHistoryFilter()
        self.assertIn('operation_uuid', f.get_fields())

    def test_publish_package_history_filter_fields(self):
        f = app_store_filters.PublishPackageHistoryFilter()
        self.assertIn('operation_uuid', f.get_fields())

    def test_component_entrance_filter_fields(self):
        f = app_store_filters.ComponentEntranceFilter()
        self.assertIn('app_name', f.get_fields())

    def test_product_entrance_filter_fields(self):
        f = app_store_filters.ProductEntranceFilter()
        self.assertIn('pro_name', f.get_fields())

    def test_install_history_filter_fields(self):
        f = app_store_filters.InstallHistoryFilter()
        self.assertIn('operation_uuid', f.get_fields())

    def test_service_install_history_filter_fields(self):
        f = app_store_filters.ServiceInstallHistoryFilter()
        self.assertIn('id', f.get_fields())

class TestAppStoreSerializersUnittest(unittest.TestCase):
    def test_upload_package_serializer_validate(self):
        s = app_store_serializers.UploadPackageSerializer()
        class DummyFile:
            name = 'test.tar'
            size = 100
            def chunks(self):
                yield b'data'
        attrs = {'file': DummyFile(), 'uuid': 'u', 'operation_user': 'o', 'md5': 'm'}
        self.assertEqual(s.validate(attrs), attrs)
        DummyFile.name = 'test.txt'
        with self.assertRaises(ValidationError):
            s.validate(dict(attrs, file=DummyFile()))
        DummyFile.name = 'test.tar'
        DummyFile.size = 5 * 1024 * 1024 * 1024
        with self.assertRaises(ValidationError):
            s.validate(dict(attrs, file=DummyFile()))

    @mock.patch('db_models.models.UploadPackageHistory.objects.filter')
    def test_remove_package_serializer_validate(self, mock_filter):
        s = app_store_serializers.RemovePackageSerializer()
        class DummyQueryset:
            def exists(self): return True
            def __len__(self): return 1
            def update(self, **kwargs): pass
        mock_filter.return_value = DummyQueryset()
        attrs = {'uuid': 'u', 'package_names': ['a']}
        res = s.validate(attrs)
        self.assertIn('queryset', res)
        class DummyQueryset2:
            def exists(self): return False
            def __len__(self): return 0
        mock_filter.return_value = DummyQueryset2()
        with self.assertRaises(ValidationError):
            s.validate(attrs)

    @mock.patch('db_models.models.Service.objects.filter')
    def test_component_list_serializer_get_instance_number(self, mock_filter):
        # 多环境：计数按请求环境过滤，注入带 env 的请求上下文
        s = app_store_serializers.ComponentListSerializer(
            context={"request": SimpleNamespace(env=object())})
        mock_filter.return_value = FakeCountQueryset([1,2,3])
        class DummyObj: app_name = 'a'
        self.assertEqual(s.get_instance_number(DummyObj()), 3)

    @mock.patch('db_models.models.Product.objects.filter')
    def test_service_list_serializer_get_instance_number(self, mock_filter):
        # 多环境：计数按请求环境过滤，注入带 env 的请求上下文
        s = app_store_serializers.ServiceListSerializer(
            context={"request": SimpleNamespace(env=object())})
        mock_filter.return_value = FakeCountQueryset([1,2])
        class DummyObj: pass
        self.assertEqual(s.get_instance_number(DummyObj()), 2)

class TestAppStoreSerializersExtraUnittest(unittest.TestCase):
    @mock.patch('db_models.models.Service.objects.filter')
    def test_product_detail_serializer_get_pro_instances_info(self, mock_filter):
        s = app_store_serializers.ProductDetailSerializer()
        mock_filter.return_value = []
        class Dummy:
            id = 1
        self.assertIsInstance(s.get_pro_instances_info(Dummy()), list)

    def test_product_detail_serializer_get_pro_labels(self):
        s = app_store_serializers.ProductDetailSerializer()
        class Dummy:
            def pro_labels(self): return self
            def all(self): return self
            def values_list(self, *a, **k): return ['label']
        obj = Dummy()
        obj.pro_labels = lambda: obj
        self.assertIn('label', s.get_pro_labels(obj))

    def test_product_detail_serializer_get_pro_package_md5(self):
        s = app_store_serializers.ProductDetailSerializer()
        class Dummy: pro_package = type('P', (), {'package_md5': 'md5'})()
        self.assertEqual(s.get_pro_package_md5(Dummy()), 'md5')
        class Dummy2: pro_package = None
        self.assertEqual(s.get_pro_package_md5(Dummy2()), '-')

    def test_product_detail_serializer_get_pro_operation_user(self):
        s = app_store_serializers.ProductDetailSerializer()
        class Dummy: pro_package = type('P', (), {'operation_user': 'u'})()
        self.assertEqual(s.get_pro_operation_user(Dummy()), 'u')
        class Dummy2: pro_package = None
        self.assertIsNone(s.get_pro_operation_user(Dummy2()))

    @mock.patch('db_models.models.ApplicationHub.objects.filter')
    @mock.patch('db_models.models.UploadPackageHistory.objects.get')
    def test_product_detail_serializer_get_pro_services(self, mock_get, mock_filter):
        s = app_store_serializers.ProductDetailSerializer()
        class Dummy:
            id = 1
            pro_services = json.dumps([{"name": "a"}])
        mock_filter.return_value = []
        obj = Dummy()
        self.assertIsInstance(s.get_pro_services(obj), list)
        # apps不为空
        class App:
            app_name = 'a'
            app_version = 'v'
            created = '2023-01-01 00:00:00.000000'
            app_package_id = 1
        mock_filter.return_value = [App()]
        mock_get.return_value = type('U', (), {'package_md5': 'md5'})()
        self.assertIsInstance(s.get_pro_services(obj), list)

    def test_component_entrance_serializer_methods(self):
        s = app_store_serializers.ComponentEntranceSerializer()
        class Dummy: pass
        obj = Dummy()
        # 只要能调用即可
        s.get_app_port(obj)
        s.get_app_dependence(obj)
        s.get_app_install_args(obj)
        s.get_deploy_mode(obj)
        s.get_process_continue(obj)
        s.get_process_message(obj)

    @mock.patch('db_models.models.ApplicationHub.objects.filter')
    def test_product_entrance_serializer_get_pro_services(self, mock_filter):
        s = app_store_serializers.ProductEntranceSerializer()
        class Dummy:
            pro_services = json.dumps([{"name": "a", "version": "v"}])
        mock_filter.return_value.last.return_value = None
        obj = Dummy()
        self.assertIsInstance(s.get_pro_services(obj), list)

    def test_install_history_serializer_methods(self):
        s = app_store_serializers.InstallHistorySerializer()
        class Dummy:
            def get_install_status_display(self): return 'ok'
            def __getattr__(self, item): return {}
        obj = Dummy()
        s.parse_single_obj(obj)
        s.get_detail_lst(obj)

    def test_service_install_history_serializer_methods(self):
        s = app_store_serializers.ServiceInstallHistorySerializer()
        class Dummy:
            def get_install_step_display(self): return 'ok'
            def __getattr__(self, item): return {}
        obj = Dummy()
        s.get_install_step_status(obj)
        s.get_log(obj)

    def test_product_composition_serializer_methods(self):
        s = app_store_serializers.ProductCompositionSerializer()
        class Dummy:
            pro_services = '[{"name": "a"}]'
            pro_name = 'n'
            pro_version = 'v'
        obj = Dummy()
        s.get_pro_ser_others(obj)
        s.validate_pro_services('[{"name": "a"}]')
        s.validate({'pro_services': '[{"name": "a"}]'})

    def test_delete_component_serializer_methods(self):
        s = app_store_serializers.DeleteComponentSerializer()
        class Dummy:
            app_name = 'n'
            app_version = 'v'
        obj = Dummy()
        s.get_name(obj)
        s.get_versions(obj)

    def test_delete_product_serializer_methods(self):
        s = app_store_serializers.DeleteProDuctSerializer()
        class Dummy:
            pro_name = 'n'
            pro_version = 'v'
        obj = Dummy()
        s.get_name(obj)
        s.get_versions(obj)

class TestAppStoreFiltersMetaUnittest(unittest.TestCase):
    def test_label_filter_meta(self):
        from app_store.app_store_filters import LabelFilter
        f = LabelFilter()
        self.assertIn('label_type', f.get_fields())
        self.assertEqual(f._meta.model.__name__, 'Labels')

    def test_component_filter_meta(self):
        from app_store.app_store_filters import ComponentFilter
        f = ComponentFilter()
        self.assertIn('app_name', f.get_fields())
        self.assertIn('type', f.get_fields())
        self.assertEqual(f._meta.model.__name__, 'ApplicationHub')

    def test_service_filter_meta(self):
        from app_store.app_store_filters import ServiceFilter
        f = ServiceFilter()
        self.assertIn('pro_name', f.get_fields())
        self.assertIn('type', f.get_fields())
        self.assertEqual(f._meta.model.__name__, 'ProductHub')

    def test_upload_package_history_filter_meta(self):
        from app_store.app_store_filters import UploadPackageHistoryFilter
        f = UploadPackageHistoryFilter()
        self.assertIn('operation_uuid', f.get_fields())
        self.assertEqual(f._meta.model.__name__, 'UploadPackageHistory')

    def test_publish_package_history_filter_meta(self):
        from app_store.app_store_filters import PublishPackageHistoryFilter
        f = PublishPackageHistoryFilter()
        self.assertIn('operation_uuid', f.get_fields())
        self.assertEqual(f._meta.model.__name__, 'UploadPackageHistory')

    def test_component_entrance_filter_meta(self):
        from app_store.app_store_filters import ComponentEntranceFilter
        f = ComponentEntranceFilter()
        self.assertIn('app_name', f.get_fields())
        self.assertEqual(f._meta.model.__name__, 'ApplicationHub')

    def test_product_entrance_filter_meta(self):
        from app_store.app_store_filters import ProductEntranceFilter
        f = ProductEntranceFilter()
        self.assertIn('pro_name', f.get_fields())
        self.assertEqual(f._meta.model.__name__, 'ProductHub')

    def test_install_history_filter_meta(self):
        from app_store.app_store_filters import InstallHistoryFilter
        f = InstallHistoryFilter()
        self.assertIn('operation_uuid', f.get_fields())
        self.assertEqual(f._meta.model.__name__, 'MainInstallHistory')

    def test_service_install_history_filter_meta(self):
        from app_store.app_store_filters import ServiceInstallHistoryFilter
        f = ServiceInstallHistoryFilter()
        self.assertIn('id', f.get_fields())
        self.assertEqual(f._meta.model.__name__, 'Service')
