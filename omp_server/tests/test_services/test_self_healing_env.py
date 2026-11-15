# -*- coding: utf-8 -*-
"""
自愈历史环境归属测试（多环境架构终审必修项 2）

SelfHealing.write_db 的字段映射需包含 env_id：告警信息
（AlertAnalysis.__call__ 产物，随 WaitSelfHealing.repair_ser 缓存）
恒携带 env_id（取自告警关联主机/服务自身），自愈历史按环境落库，
否则全部落到 default(id=1)，跨环境查看自愈记录串环境。
"""
import datetime

from db_models.models import Env, SelfHealingHistory
from services.self_healing import SelfHealing
from tests.base import BaseTest


class SelfHealingWriteDbEnvTest(BaseTest):
    """ write_db 按告警携带的 env_id 落自愈历史环境 """

    def setUp(self):
        super(SelfHealingWriteDbEnvTest, self).setUp()
        self.env_default = Env.objects.get(id=1)
        self.env_b = Env.objects.create(name="预发环境", code="staging")

    def _alert_data(self, env_id, instance_name):
        """构造一条携带 env_id 的告警信息（字段口径同 AlertAnalysis）"""
        return {
            "alert_host_ip": "10.20.0.2",
            "alert_service_name": "mysql",
            "alert_time": datetime.datetime(2026, 11, 15, 10, 0, 0),
            "alert_describe": "主机 10.20.0.2 中的 mysql 已经down掉超过一分钟",
            "alert_instance_name": instance_name,
            "env_id": env_id,
        }

    def test_write_db_persists_alert_env_id(self):
        """ env2 的告警 → SelfHealingHistory.env == env2（不再落 default） """
        his_b = SelfHealing.write_db(
            self._alert_data(self.env_b.id, "mysql_staging"), 1)
        self.assertEqual(his_b.env_id, self.env_b.id)
        his_default = SelfHealing.write_db(
            self._alert_data(self.env_default.id, "mysql_default"), 1)
        self.assertEqual(his_default.env_id, self.env_default.id)
        # 落库结果复核（非仅返回值）
        self.assertEqual(
            SelfHealingHistory.objects.filter(
                id=his_b.id).first().env, self.env_b)

    def test_write_db_without_env_id_keeps_default(self):
        """ 告警信息未携带 env_id（存量数据防御）：保持模型缺省 default """
        data = self._alert_data(self.env_b.id, "mysql_staging")
        data.pop("env_id")
        his = SelfHealing.write_db(data, 1)
        self.assertEqual(his.env_id, self.env_default.id)
