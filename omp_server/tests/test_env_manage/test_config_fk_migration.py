"""Task 2: 六张配置表 env_id 裸整数改 FK(CASCADE) 的模型与迁移行为测试。

覆盖：
1. 六模型 env 字段为 FK(Env, CASCADE)，裸 env_id 字段不复存在，级联删除生效；
2. 迁移数据清理：env_id=0 行删除（而非归并）、非法 env_id 归并默认环境 1、
   清理函数前向幂等。
"""

from importlib import import_module

import pytest

from django.db import connection
from django.db import models as dj_models
from django.db.migrations.executor import MigrationExecutor

from db_models.models import (
    AlertRule,
    AlertSendWaySetting,
    Env,
    HostThreshold,
    ModuleSendEmailSetting,
    ServiceCustomThreshold,
    ServiceThreshold,
)

# 六张环境配置表
CONFIG_MODELS = (
    HostThreshold,
    ServiceThreshold,
    ServiceCustomThreshold,
    AlertRule,
    ModuleSendEmailSetting,
    AlertSendWaySetting,
)

# 本任务新增的迁移
FK_MIGRATION = "0033_multi_env_config_fk"


@pytest.mark.django_db
def test_config_models_env_is_fk_to_env():
    """六模型的 env 字段是 FK(Env, on_delete=CASCADE)，DB 列名保持 env_id"""
    for model in CONFIG_MODELS:
        field = model._meta.get_field("env")
        assert field.related_model is Env, model.__name__
        assert field.remote_field.on_delete is dj_models.CASCADE, model.__name__
        assert field.get_attname_column()[1] == "env_id", model.__name__
    # 级联删除真实生效：删环境后其下配置行随之删除
    HostThreshold.objects.create(
        index_type="cpu_used", condition=">=",
        condition_value="90", alert_level="critical")
    assert HostThreshold.objects.count() == 1
    Env.objects.get(id=1).delete()
    assert HostThreshold.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_migration_deletes_env0_and_merges_invalid_env_id():
    """
    真实迁移行为：回滚到 0032 造脏数据（env_id 为裸整数，可写非法值），
    再前滚到 0033 验证数据清理 + FK 转换。
    需 transaction=True：迁移含 DDL，SQLite schema editor 不能在事务内工作。
    """
    executor = MigrationExecutor(connection)
    executor.migrate([("db_models", "0032_multi_env_env")])
    old_apps = executor.loader.project_state(
        ("db_models", "0032_multi_env_env")).apps

    # AlertRule 脏数据：合法行 / 非法环境行 / env_id=0 行
    old_rule = old_apps.get_model("db_models", "AlertRule")
    rule_kwargs = dict(
        expr="up == 1", threshold_value=1, compare_str="==",
        for_time="1m", severity="critical", alert="a", service="s")
    rule_ok = old_rule.objects.create(env_id=1, **rule_kwargs)
    rule_bad = old_rule.objects.create(env_id=999, **rule_kwargs)
    old_rule.objects.create(env_id=0, **rule_kwargs)

    # AlertSendWaySetting 脏数据（历史 default=0 产生了 env_id=0 行）
    old_way = old_apps.get_model("db_models", "AlertSendWaySetting")
    way_ok = old_way.objects.create(env_id=1, way_name="email")
    way_bad = old_way.objects.create(env_id=42, way_name="email")
    way_zero = old_way.objects.create(env_id=0, way_name="email")

    # loader 的 applied 集合是构建时缓存的，回滚后需重建再前滚，
    # 否则 0033 仍被视作已应用，前滚计划为空
    executor.loader.build_graph()
    executor.migrate([("db_models", FK_MIGRATION)])

    # env_id=0 行被删除而非归并
    assert AlertSendWaySetting.objects.filter(env_id=0).exists() is False
    assert AlertRule.objects.filter(env_id=0).exists() is False
    assert not AlertSendWaySetting.objects.filter(id=way_zero.id).exists()
    # 非法 env_id 归并到默认环境 1，合法行保持不变
    assert AlertRule.objects.get(id=rule_bad.id).env_id == 1
    assert AlertSendWaySetting.objects.get(id=way_bad.id).env_id == 1
    assert AlertRule.objects.get(id=rule_ok.id).env_id == 1
    assert AlertSendWaySetting.objects.get(id=way_ok.id).env_id == 1
    # 迁移后全部行的 env 指向合法环境
    assert AlertRule.objects.filter(env__isnull=True).exists() is False
    assert AlertSendWaySetting.objects.filter(env__isnull=True).exists() is False

    # 数据清理函数前向幂等：终态重复执行无副作用
    migration = import_module("db_models.migrations." + FK_MIGRATION)
    head_apps = executor.loader.project_state(
        ("db_models", FK_MIGRATION)).apps
    migration.clean_config_env_id(head_apps, None)
    assert AlertSendWaySetting.objects.filter(env_id=0).exists() is False
    assert AlertRule.objects.get(id=rule_bad.id).env_id == 1
