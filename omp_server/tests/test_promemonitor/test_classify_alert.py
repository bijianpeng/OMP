# -*- coding: utf-8 -*-
"""
classify_alert 单元测试：覆盖告警归类（host/database/service/component）的各边界。
该函数统一仪表盘（InstrumentPanelView）与异常清单（explain_prometheus）两条链路
的告警分类口径，修复“job=nodeExporter 但 instance_name 是组件实例名”被误判为 host。
"""
from unittest.mock import MagicMock

from promemonitor.grafana_url import classify_alert


def _service(instance_name=None, app_name=None):
    """构造一个假的 Service 对象供 classify_alert 匹配。"""
    m = MagicMock()
    m.service_instance_name = instance_name
    m.service.app_name = app_name
    return m


class TestClassifyAlert:

    def test_node_exporter_with_component_instance_name_returns_component(self):
        """核心修复：job=nodeExporter 但 instance_name 命中组件 → component（而非 host）。"""
        labels = {"job": "nodeExporter", "instance_name": "kafka-30-159", "app": "kafka"}
        component_list = [_service(instance_name="kafka-30-159", app_name="kafka")]
        assert classify_alert(labels, [], [], component_list) == "component"

    def test_node_exporter_with_host_instance_name_returns_host(self):
        """纯主机告警（nodeExporter + 主机实例名，匹配不到任何服务）→ host。"""
        labels = {"job": "nodeExporter", "instance_name": "Node1"}
        assert classify_alert(labels, [], [], []) == "host"

    def test_database_alert_returns_database(self):
        labels = {"job": "mysqlExporter", "instance_name": "mysql-30-154", "app": "mysql"}
        database_list = [_service(instance_name="mysql-30-154", app_name="mysql")]
        assert classify_alert(labels, database_list, [], []) == "database"

    def test_service_alert_returns_service(self):
        labels = {"job": "ifms_alertExporter", "instance_name": "ifms_alert-30-154", "app": "ifms_alert"}
        service_list = [_service(instance_name="ifms_alert-30-154", app_name="ifms_alert")]
        assert classify_alert(labels, [], service_list, []) == "service"

    def test_component_alert_returns_component(self):
        labels = {"job": "redisExporter", "instance_name": "redis-30-154", "app": "redis"}
        component_list = [_service(instance_name="redis-30-154", app_name="redis")]
        assert classify_alert(labels, [], [], component_list) == "component"

    def test_empty_instance_name_falls_back_to_app_name(self):
        """instance_name 缺失时，回退用 app/job 推断 app_name 匹配（保留原 get_item_type 行为）。"""
        labels = {"job": "redisExporter", "app": "redis"}
        component_list = [_service(instance_name="redis-30-154", app_name="redis")]
        assert classify_alert(labels, [], [], component_list) == "component"

    def test_no_match_node_exporter_returns_host(self):
        """都不匹配 + nodeExporter → host。"""
        labels = {"job": "nodeExporter", "instance_name": "unknown-1-2", "app": "node"}
        assert classify_alert(labels, [], [], []) == "host"

    def test_no_match_non_node_exporter_returns_service(self):
        """都不匹配且非 nodeExporter → service（与原 get_item_type 最终回退一致）。"""
        labels = {"job": "fooExporter", "instance_name": "unknown-1-2", "app": "foo"}
        assert classify_alert(labels, [], [], []) == "service"
