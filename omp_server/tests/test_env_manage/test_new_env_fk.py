"""Task 3: 十模型新增 env FK + 存量回填的模型与迁移行为测试。

覆盖：
1. 十模型 env 字段为 FK(Env)，on_delete 按 brief（SelfHealingSetting/
   WaitSelfHealing CASCADE，其余八表 SET_NULL），null/blank=True、default=1、
   DB 列名 env_id，级联/置空行为真实生效；
2. 迁移回填：新十表存量行 env_id=1；已有 FK 表（Host/Service/InspectionHistory/
   InspectionCrontab/UpgradeHistory/RollbackHistory）NULL 归 1；Alert 按主机
   IP 反查（匹配到取主机 env，匹配不到归 1）；存量非 superuser 用户补
   UserEnv(env=1)；存量巡检 PeriodicTask kwargs 补 "env": 1（严格签名任务
   不动）；回填函数前向幂等。
"""

import json
from importlib import import_module

import pytest

from django.db import connection
from django.db import models as dj_models
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from db_models.models import Env

# 本任务新增的迁移
FK_MIGRATION = "0034_multi_env_ten_fk"

# 十模型 -> on_delete 约定（brief：配置/瞬时类 CASCADE，其余 SET_NULL）
NEW_FK_ON_DELETE = {
    "MainInstallHistory": dj_models.SET_NULL,
    "DeploymentPlan": dj_models.SET_NULL,
    "ExecutionRecord": dj_models.SET_NULL,
    "BackupSetting": dj_models.SET_NULL,
    "BackupHistory": dj_models.SET_NULL,
    "ToolExecuteMainHistory": dj_models.SET_NULL,
    "SelfHealingHistory": dj_models.SET_NULL,
    "OperateLog": dj_models.SET_NULL,
    "SelfHealingSetting": dj_models.CASCADE,
    "WaitSelfHealing": dj_models.CASCADE,
}

# 已有 env FK、迁移需 NULL 回填归 1 的表
EXISTING_FK_MODELS = (
    "Host",
    "Service",
    "InspectionHistory",
    "InspectionCrontab",
    "UpgradeHistory",
    "RollbackHistory",
)

INSPECTION_TASK = "inspection.tasks.inspection_crontab"
SELF_HEALING_TASK = "services.self_healing.self_healing"


def _create_ten_rows(models):
    """用当前模型各造一行，全部挂在 env2 下（必填字段最小化）"""
    tool = models["ToolInfo"].objects.create(
        name="t", source_package_path="a",
        tool_folder_path="b", script_path="c", description="d")
    return {
        "MainInstallHistory": models["MainInstallHistory"].objects.create(
            operation_uuid="op-1", install_log="log",
            env=models["env2"]),
        "DeploymentPlan": models["DeploymentPlan"].objects.create(
            plan_name="plan", create_user="u", operation_uuid="op-1",
            env=models["env2"]),
        "ExecutionRecord": models["ExecutionRecord"].objects.create(
            env=models["env2"]),
        "BackupSetting": models["BackupSetting"].objects.create(
            crontab_detail={}, env=models["env2"]),
        "BackupHistory": models["BackupHistory"].objects.create(
            backup_name="bk", env=models["env2"]),
        "ToolExecuteMainHistory":
            models["ToolExecuteMainHistory"].objects.create(
                tool=tool, env=models["env2"]),
        "SelfHealingHistory": models["SelfHealingHistory"].objects.create(
            host_ip="1.1.1.1", env=models["env2"]),
        "OperateLog": models["OperateLog"].objects.create(
            username="u", request_method="GET", request_url="/a",
            description="d", env=models["env2"]),
        "SelfHealingSetting": models["SelfHealingSetting"].objects.create(
            env=models["env2"]),
        "WaitSelfHealing": models["WaitSelfHealing"].objects.create(
            env=models["env2"]),
    }


@pytest.mark.django_db
def test_ten_models_env_field_semantics():
    """十模型 env 字段：FK(Env)、on_delete 约定、null/blank、default=1、列名 env_id"""
    from db_models.models import (
        BackupHistory, BackupSetting, DeploymentPlan, ExecutionRecord,
        MainInstallHistory, OperateLog, SelfHealingSetting,
        SelfHealingHistory, ToolExecuteMainHistory, ToolInfo,
        WaitSelfHealing,
    )
    models = {
        "MainInstallHistory": MainInstallHistory,
        "DeploymentPlan": DeploymentPlan,
        "ExecutionRecord": ExecutionRecord,
        "BackupSetting": BackupSetting,
        "BackupHistory": BackupHistory,
        "ToolExecuteMainHistory": ToolExecuteMainHistory,
        "ToolInfo": ToolInfo,
        "SelfHealingHistory": SelfHealingHistory,
        "SelfHealingSetting": SelfHealingSetting,
        "WaitSelfHealing": WaitSelfHealing,
        "OperateLog": OperateLog,
        "env2": Env.objects.create(name="env2", code="e2"),
    }
    for name, on_delete in NEW_FK_ON_DELETE.items():
        field = models[name]._meta.get_field("env")
        assert field.related_model is Env, name
        assert field.remote_field.on_delete is on_delete, name
        assert field.null is True and field.blank is True, name
        # 十表均有存量创建点（见任务报告），FK 需 default=1 防 IntegrityError
        assert field.default == 1, name
        assert field.get_attname_column()[1] == "env_id", name

    # 删除环境：SET_NULL 八表行保留且 env 置空，CASCADE 两表行级联删除
    rows = _create_ten_rows(models)
    Env.objects.get(id=models["env2"].id).delete()
    for name, on_delete in NEW_FK_ON_DELETE.items():
        model = models[name]
        obj = model.objects.filter(id=rows[name].id).first()
        if on_delete is dj_models.CASCADE:
            assert obj is None, name
        else:
            assert obj is not None and obj.env_id is None, name


@pytest.mark.django_db(transaction=True)
def test_migration_backfills_env():
    """
    真实迁移行为：回滚到 0033 造存量数据（十表无 env 列，已有 FK 表可写
    NULL），前滚 0034 验证 schema + 全量回填。需 transaction=True：迁移含
    DDL，SQLite schema editor 不能在事务内工作。
    历史模型统一走 _base_manager：Service 首个 manager 是自定义
    split_objects，迁移态模型没有 .objects，且自定义 manager 带过滤。
    """
    executor = MigrationExecutor(connection)
    executor.migrate([("db_models", "0033_multi_env_config_fk")])
    old_apps = executor.loader.project_state(
        ("db_models", "0033_multi_env_config_fk")).apps

    def om(name):
        return old_apps.get_model("db_models", name)._base_manager

    # 前序 transaction 测试可能已把库留在 0033 且 flush 掉 0032 回填的
    # 默认环境（真实库 0032 后恒有 id=1），此处补齐以对齐生产态
    if not om("Env").filter(id=1).exists():
        om("Env").create(id=1, name="default", code="default")
    env2 = om("Env").create(name="env2", code="e2")

    # --- 已有 FK 表的 NULL 存量 + 合法存量 ---
    host_null = om("Host").create(
        instance_name="h1", ip="1.1.1.1", username="u",
        password="p", operate_system="centos")            # env NULL
    host_env2 = om("Host").create(
        instance_name="h2", ip="2.2.2.2", username="u",
        password="p", operate_system="centos", env_id=env2.id)
    svc_null = om("Service").create(
        ip="1.1.1.1", service_instance_name="svc-1")      # env NULL
    insp_his = om("InspectionHistory").create(
        inspection_name="i1", inspection_operator="admin")
    insp_cron = om("InspectionCrontab").create(
        job_name="jc", crontab_detail={})
    upgrade = om("UpgradeHistory").create()
    rollback = om("RollbackHistory").create()

    # --- Alert：按主机 IP 反查 / 反查不到 / 已有值不动 ---
    alert_from_null_host = om("Alert").create(
        alert_host_ip="1.1.1.1", alert_time=timezone.now())   # -> 1(主机NULL归1)
    alert_from_env2_host = om("Alert").create(
        alert_host_ip="2.2.2.2", alert_time=timezone.now())   # -> env2
    alert_no_host = om("Alert").create(
        alert_host_ip="9.9.9.9", alert_time=timezone.now())   # 无主机 -> 1
    alert_kept = om("Alert").create(
        alert_host_ip="2.2.2.2", alert_time=timezone.now(),
        env_id=env2.id)                                        # 已有值 -> 不动

    # --- 新十表存量行（0033 时点无 env 字段） ---
    old_tool = om("ToolInfo").create(
        name="t", source_package_path="a",
        tool_folder_path="b", script_path="c", description="d")
    new_row_ids = {
        "MainInstallHistory": om("MainInstallHistory").create(
            operation_uuid="op-1", install_log="log").id,
        "DeploymentPlan": om("DeploymentPlan").create(
            plan_name="plan", create_user="u", operation_uuid="op-1").id,
        "ExecutionRecord": om("ExecutionRecord").create().id,
        "BackupSetting": om("BackupSetting").create(
            crontab_detail={}).id,
        "BackupHistory": om("BackupHistory").create(
            backup_name="bk").id,
        "ToolExecuteMainHistory": om("ToolExecuteMainHistory").create(
            tool=old_tool).id,
        "WaitSelfHealing": om("WaitSelfHealing").create().id,
        "SelfHealingSetting": om("SelfHealingSetting").create().id,
        "SelfHealingHistory": om("SelfHealingHistory").create(
            host_ip="1.1.1.1").id,
        "OperateLog": om("OperateLog").create(
            username="u", request_method="GET", request_url="/a",
            description="d").id,
    }

    # --- 存量用户授权：非 superuser 补 env1，superuser 不补，已有不重复 ---
    user_ops = om("UserProfile").create(username="u-ops", role="ops")
    user_ro = om("UserProfile").create(
        username="u-ro", role="readonlyuser")
    user_su = om("UserProfile").create(
        username="u-su", role="superuser")
    om("UserEnv").create(user=user_ro, env_id=1)

    # --- 存量 beat 任务：巡检无 env 补 1 / 巡检有 env 不动 / 严格签名任务不动 ---
    from django_celery_beat.models import CrontabSchedule, PeriodicTask
    schedule = CrontabSchedule.objects.create()  # 字段默认全 '*'
    cron_no_env = PeriodicTask.objects.create(
        name="inspection_cron_task_host", crontab=schedule,
        task=INSPECTION_TASK,
        kwargs=json.dumps({"job_type": 1, "job_name": "主机巡检"}))
    cron_has_env = PeriodicTask.objects.create(
        name="inspection_cron_task_service", crontab=schedule,
        task=INSPECTION_TASK,
        kwargs=json.dumps({"env": env2.id, "job_type": 2, "job_name": "组件巡检"}))
    strict_task = PeriodicTask.objects.create(
        name="self_health_cron_task_5", crontab=schedule,
        task=SELF_HEALING_TASK,
        kwargs=json.dumps({"task_id": 5}))
    cron_has_env_kwargs = cron_has_env.kwargs
    strict_task_kwargs = strict_task.kwargs

    # loader 的 applied 集合是构建时缓存的，回滚后需重建再前滚
    executor.loader.build_graph()
    executor.migrate([("db_models", FK_MIGRATION)])
    head_apps = executor.loader.project_state(
        ("db_models", FK_MIGRATION)).apps

    def hm(name):
        return head_apps.get_model("db_models", name)._base_manager

    # 新十表存量行 env_id=1
    for name, row_id in new_row_ids.items():
        assert hm(name).get(id=row_id).env_id == 1, name
    # 已有 FK 表 NULL 归 1、合法值不动
    assert hm("Host").get(id=host_null.id).env_id == 1
    assert hm("Host").get(id=host_env2.id).env_id == env2.id
    assert hm("Service").get(id=svc_null.id).env_id == 1
    assert hm("InspectionHistory").get(id=insp_his.id).env_id == 1
    assert hm("InspectionCrontab").get(id=insp_cron.id).env_id == 1
    assert hm("UpgradeHistory").get(id=upgrade.id).env_id == 1
    assert hm("RollbackHistory").get(id=rollback.id).env_id == 1
    # Alert 按 IP 反查：主机 NULL 先归 1 故随 1；env2 主机随 env2；无主机归 1；已有值不动
    assert hm("Alert").get(id=alert_from_null_host.id).env_id == 1
    assert hm("Alert").get(id=alert_from_env2_host.id).env_id == env2.id
    assert hm("Alert").get(id=alert_no_host.id).env_id == 1
    assert hm("Alert").get(id=alert_kept.id).env_id == env2.id
    # 全部表无 env NULL 行
    for name in list(new_row_ids) + list(EXISTING_FK_MODELS) + ["Alert"]:
        assert not hm(name).filter(env__isnull=True).exists(), name

    # 存量用户授权（user_id 过滤：旧态实例与 head 态模型类不互通）
    assert hm("UserEnv").filter(user_id=user_ops.id, env_id=1).count() == 1
    assert hm("UserEnv").filter(user_id=user_ro.id).count() == 1  # 不重复补
    assert hm("UserEnv").filter(user_id=user_su.id).count() == 0

    # beat 任务 kwargs 回填：json 往返其余键无损
    cron_no_env.refresh_from_db()
    assert json.loads(cron_no_env.kwargs) == {
        "job_type": 1, "job_name": "主机巡检", "env": 1}
    cron_has_env.refresh_from_db()
    assert cron_has_env.kwargs == cron_has_env_kwargs  # 原串不动
    strict_task.refresh_from_db()
    assert strict_task.kwargs == strict_task_kwargs   # 严格签名任务不动

    # 回填函数前向幂等：终态重复执行无副作用
    migration = import_module("db_models.migrations." + FK_MIGRATION)
    migration.backfill_env_data(head_apps, None)
    cron_no_env.refresh_from_db()
    assert json.loads(cron_no_env.kwargs) == {
        "job_type": 1, "job_name": "主机巡检", "env": 1}
    assert hm("UserEnv").filter(user_id=user_ops.id, env_id=1).count() == 1
    assert not hm("Alert").filter(env__isnull=True).exists()
