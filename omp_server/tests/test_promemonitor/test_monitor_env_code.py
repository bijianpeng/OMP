# -*- coding: utf-8 -*-
"""
监控生成链路 env_code 化测试（多环境架构 Task 11，spec §6.4；
终审必修项 3 / 5 补充：规则文件按环境过滤、node job files 合并）

约定：进入监控链路的一切 env 字符串均为 Env.code——
1. 规则文件按 Env.code 命名（update_rule_file(env="prod") → prod_rule.yml，含 env='prod'）
2. targets 文件按环境拆分（两环境同服务 → 两个 JSON 文件互不覆盖；主机 targets 同拆分）
3. delete_service 按 (env_code, instance) 匹配删除，不影响其它环境文件
4. update_rule_file 只导出当前环境（env__code 过滤）的启用规则（必修项 3）
5. add_data_disk_rules 创建的 AlertRule 落所属环境（必修项 3）
6. add_node 把 {env_code}_nodeExporter.json 并入 nodeExporter job 的
   file_sd files（线上 node job 为固定文件名非 glob，必修项 5）
"""
import json
import os
import shutil
import tempfile
from unittest import mock

import yaml

from db_models.models import AlertRule, Env
from promemonitor.prometheus_utils import PrometheusUtils
from tests.base import BaseTest


class MonitorEnvCodeTest(BaseTest):
    """ 监控规则文件与抓取目标按 Env.code 生成 """

    def setUp(self):
        super(MonitorEnvCodeTest, self).setUp()
        # 用临时目录替换 PROJECT_DIR，规则/targets 落盘断言均在临时目录进行
        self.tmp_project_dir = tempfile.mkdtemp(prefix="omp_monitor_env_code_")
        for patcher in (
                mock.patch("promemonitor.prometheus_utils.PROJECT_DIR",
                           self.tmp_project_dir),
                mock.patch("utils.prometheus.update_threshold.PROJECT_DIR",
                           self.tmp_project_dir)):
            patcher.start()
            self.addCleanup(patcher.stop)
        # 屏蔽向 agent / prometheus 发送的 HTTP 请求
        post_patcher = mock.patch(
            "promemonitor.prometheus_utils.requests.post")
        post_patcher.start()
        self.addCleanup(post_patcher.stop)
        self.utils = PrometheusUtils()
        # 预置目录与 prometheus.yml（add_service 会读取/回写 scrape_configs）
        os.makedirs(self.utils.prometheus_rules_path, exist_ok=True)
        os.makedirs(self.utils.prometheus_targets_path, exist_ok=True)
        with open(self.utils.prometheus_conf_path, "w",
                  encoding="utf8") as fp:
            yaml.dump({"global": {"scrape_interval": "15s"},
                       "scrape_configs": []}, fp)

    def tearDown(self):
        shutil.rmtree(self.tmp_project_dir, ignore_errors=True)
        super(MonitorEnvCodeTest, self).tearDown()

    @staticmethod
    def _make_rule(env, expr, alert, status=1):
        """落库一条指定环境的启用告警规则"""
        return AlertRule.objects.create(
            env=env,
            expr=expr,
            threshold_value=1,
            compare_str="<",
            for_time="1m",
            severity="critical",
            alert=alert,
            service="node",
            status=status,
            labels={"job": "nodeExporter"},
            summary=alert,
            description=alert,
        )

    @staticmethod
    def _service_data(env_code, ip="10.0.0.1"):
        """构造 add_service 入参，env 一律为 Env.code"""
        return {
            "service_name": "mysql",
            "instance_name": "mysql_{}".format(env_code),
            "data_path": "/data/appData/mysql",
            "log_path": "/data/logs/mysql",
            "env": env_code,
            "ip": ip,
            "listen_port": "3306",
            "metric_port": "19018",
        }

    @staticmethod
    def _nodes_data(env_code, ip):
        """构造 add_node 入参，env 一律为 Env.code"""
        return [{
            "data_path": "",
            "env": env_code,
            "ip": ip,
            "instance_name": "host-{}".format(ip),
        }]

    def test_rule_file_per_env_code(self):
        """ update_rule_file(env="prod") → prod_rule.yml 且含 env='prod' """
        env_prod = Env.objects.create(name="生产环境", code="prod")
        self._make_rule(
            env_prod, "up{env='prod', job='nodeExporter'}", "prod 实例宕机")
        flag = self.utils.update_rule_file(env="prod")
        self.assertTrue(flag)
        rules_path = os.path.join(
            self.tmp_project_dir, "component/prometheus/conf/rules")
        prod_rule = os.path.join(rules_path, "prod_rule.yml")
        self.assertTrue(os.path.exists(prod_rule))
        with open(prod_rule, "r", encoding="utf8") as fp:
            content = fp.read()
        self.assertIn("env='prod'", content)
        # 其它环境的规则文件互不影响
        self.assertFalse(os.path.exists(
            os.path.join(rules_path, "default_rule.yml")))

    def test_rule_file_only_exports_own_env_rules(self):
        """ 必修项 3：两环境各建规则 → update_rule_file(env="a") 的
            文件只含 a 环境规则，b 环境规则不再被全量混写 """
        env_a = Env.objects.create(name="环境A", code="enva")
        env_b = Env.objects.create(name="环境B", code="envb")
        self._make_rule(env_a, "up{env='enva'} == 0", "enva 宕机")
        self._make_rule(env_b, "up{env='envb'} == 0", "envb 宕机")
        # 禁用规则也不导出
        self._make_rule(env_a, "up{env='enva'} == 9", "enva 禁用", status=0)

        self.assertTrue(self.utils.update_rule_file(env="enva"))
        rules_path = os.path.join(
            self.tmp_project_dir, "component/prometheus/conf/rules")
        with open(os.path.join(rules_path, "enva_rule.yml"),
                  "r", encoding="utf8") as fp:
            content = fp.read()
        self.assertIn("enva 宕机", content)
        self.assertNotIn("envb 宕机", content)
        self.assertNotIn("enva 禁用", content)
        # b 环境文件同理只含 b 的规则
        self.assertTrue(self.utils.update_rule_file(env="envb"))
        with open(os.path.join(rules_path, "envb_rule.yml"),
                  "r", encoding="utf8") as fp:
            content_b = fp.read()
        self.assertIn("envb 宕机", content_b)
        self.assertNotIn("enva 宕机", content_b)

    def test_add_data_disk_rules_env_attribution(self):
        """ 必修项 3：add_data_disk_rules(env="envb") 创建的 AlertRule
            落 envb（此前缺省落 default=1），规则文件同步只含本环境 """
        env_b = Env.objects.create(name="环境B", code="envb")
        self.utils.add_data_disk_rules("/data/envb", env="envb")
        rules = AlertRule.objects.filter(
            service="node", name="数据分区使用率", severity="warning")
        self.assertEqual(rules.count(), 1)
        self.assertEqual(rules.first().env, env_b)
        # 规则文件按 envb 生成，且 expr 内 env 标签为 envb
        rules_path = os.path.join(
            self.tmp_project_dir, "component/prometheus/conf/rules")
        with open(os.path.join(rules_path, "envb_rule.yml"),
                  "r", encoding="utf8") as fp:
            content = fp.read()
        self.assertIn('env="envb"', content)

    def test_add_node_merges_node_job_files(self):
        """ 必修项 5：add_node 后 nodeExporter job 的 file_sd files 追加
            targets/{env_code}_nodeExporter.json，重复调用不重复追加 """
        # 预置线上形态：nodeExporter job 指向固定文件 nodeExporter_all.json
        with open(self.utils.prometheus_conf_path, "w",
                  encoding="utf8") as fp:
            yaml.dump({
                "global": {"scrape_interval": "15s"},
                "scrape_configs": [{
                    "job_name": "nodeExporter",
                    "metrics_path": "/metrics/monitor/node",
                    "file_sd_configs": [{
                        "refresh_interval": "30s",
                        "files": ["targets/nodeExporter_all.json"],
                    }],
                }]}, fp)
        self.utils.add_node(self._nodes_data("enva", "10.0.0.1"))

        def _node_files():
            with open(self.utils.prometheus_conf_path, "r",
                      encoding="utf8") as fp:
                conf = yaml.safe_load(fp)
            node_jobs = [job for job in conf.get("scrape_configs", [])
                         if job.get("job_name") == "nodeExporter"]
            self.assertEqual(len(node_jobs), 1)
            return node_jobs[0]["file_sd_configs"][0]["files"]

        files = _node_files()
        # 既有固定文件保留，新环境 targets 文件被纳入抓取
        self.assertIn("targets/nodeExporter_all.json", files)
        self.assertIn("targets/enva_nodeExporter.json", files)
        # 再次调用（同环境新主机）不重复追加
        self.utils.add_node(self._nodes_data("enva", "10.0.0.9"))
        files_again = _node_files()
        self.assertEqual(files_again.count("targets/enva_nodeExporter.json"), 1)
        # 第二个环境的主机 → 各自环境的 targets 文件均被并入
        self.utils.add_node(self._nodes_data("envb", "10.0.0.2"))
        files_b = _node_files()
        self.assertIn("targets/envb_nodeExporter.json", files_b)
        self.assertIn("targets/enva_nodeExporter.json", files_b)


    def test_targets_file_split_by_env(self):
        """ 两环境同服务 → 各自 {env_code}_{service}Exporter.json；主机 targets 同拆分 """
        for env_code in ("default", "prod"):
            flag, _ = self.utils.add_service(self._service_data(env_code))
            self.assertTrue(flag)
        targets_path = self.utils.prometheus_targets_path
        default_file = os.path.join(
            targets_path, "default_mysqlExporter.json")
        prod_file = os.path.join(targets_path, "prod_mysqlExporter.json")
        self.assertTrue(os.path.exists(default_file))
        self.assertTrue(os.path.exists(prod_file))
        # 旧的全量共享文件不再生成
        self.assertFalse(os.path.exists(
            os.path.join(targets_path, "mysqlExporter_all.json")))
        for env_code, path in (("default", default_file),
                               ("prod", prod_file)):
            with open(path, "r", encoding="utf8") as fp:
                targets = json.load(fp)
            self.assertEqual(len(targets), 1)
            self.assertEqual(targets[0]["labels"]["env"], env_code)
        # 主机 targets 同样按环境拆分
        self.utils.add_node(self._nodes_data("default", "10.0.0.1"))
        self.utils.add_node(self._nodes_data("prod", "10.0.0.2"))
        self.assertTrue(os.path.exists(os.path.join(
            targets_path, "default_nodeExporter.json")))
        self.assertTrue(os.path.exists(os.path.join(
            targets_path, "prod_nodeExporter.json")))
        self.assertFalse(os.path.exists(os.path.join(
            targets_path, "nodeExporter_all.json")))
        # prometheus.yml 的 file_sd 需引用各环境的新文件（同 job 合并 files）
        with open(self.utils.prometheus_conf_path, "r",
                  encoding="utf8") as fp:
            prom_conf = yaml.safe_load(fp)
        mysql_jobs = [job for job in prom_conf.get("scrape_configs", [])
                      if job.get("job_name") == "mysqlExporter"]
        self.assertEqual(len(mysql_jobs), 1)
        files = mysql_jobs[0]["file_sd_configs"][0]["files"]
        self.assertIn("targets/default_mysqlExporter.json", files)
        self.assertIn("targets/prod_mysqlExporter.json", files)

    def test_del_service_matches_env(self):
        """ 删除 env2 的服务不影响 env1 的 targets 文件 """
        self.utils.add_service(self._service_data("alpha"))
        self.utils.add_service(self._service_data("beta"))
        flag, _ = self.utils.delete_service({
            "service_name": "mysql",
            "instance_name": "mysql_beta",
            "data_path": None,
            "log_path": None,
            "env": "beta",
            "ip": "10.0.0.1",
        })
        self.assertTrue(flag)
        targets_path = self.utils.prometheus_targets_path
        with open(os.path.join(targets_path, "alpha_mysqlExporter.json"),
                  "r", encoding="utf8") as fp:
            alpha_targets = json.load(fp)
        with open(os.path.join(targets_path, "beta_mysqlExporter.json"),
                  "r", encoding="utf8") as fp:
            beta_targets = json.load(fp)
        self.assertEqual(len(alpha_targets), 1)
        self.assertEqual(alpha_targets[0]["labels"]["env"], "alpha")
        self.assertEqual(beta_targets, [])
