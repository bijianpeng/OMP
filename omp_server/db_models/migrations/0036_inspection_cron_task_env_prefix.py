# 手工编写（2026-11-15，Task 7b），无 schema 变更，纯数据迁移。
#
# 巡检定时任务名 per-env：inspection_crontab_{type} 改为
# inspection_crontab_{env.code}_{type}（inspection/views.py 同步改造，
# 两环境同类型任务并存互不冲突）。本迁移把存量无前缀任务名补上其归属
# 环境的 code 前缀：
# - 归属环境取任务 kwargs["env"]（0034 已为存量巡检任务回填该键，无该
#   键按默认环境 1 处理）；
# - 目标名已存在（升级前已有环境创建过同名任务）时跳过该条，避免撞名；
# - 非巡检任务（严格签名任务等）不动；kwargs 除 name 外无任何改动；
# - 前向幂等：已带前缀的名称不匹配无前缀模式，重复执行无副作用。

import json

from django.db import migrations

INSPECTION_CRONTAB_TASK = "inspection.tasks.inspection_crontab"

# 无前缀旧命名（按 type 枚举穷举，不做模糊匹配，避免误改带前缀名）
LEGACY_TYPE_NAMES = (
    "inspection_cron_task_deep",
    "inspection_cron_task_host",
    "inspection_cron_task_service",
)


def rename_inspection_cron_tasks(apps, schema_editor):
    """存量无前缀巡检定时任务名按 kwargs 环境补 env code 前缀。"""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    Env = apps.get_model("db_models", "Env")

    code_by_env_id = dict(
        Env._base_manager.values_list("id", "code"))
    existing_names = set(
        PeriodicTask._base_manager.values_list("name", flat=True))

    for task in PeriodicTask._base_manager.filter(
            task=INSPECTION_CRONTAB_TASK,
            name__in=LEGACY_TYPE_NAMES):
        try:
            kwargs = json.loads(task.kwargs) if task.kwargs else {}
        except ValueError:
            continue
        env_id = kwargs.get("env", 1) if isinstance(kwargs, dict) else 1
        env_code = code_by_env_id.get(env_id) or "default"
        task_type = task.name.replace('inspection_cron_task_', '', 1)
        new_name = f"inspection_cron_task_{env_code}_{task_type}"
        if new_name in existing_names:
            continue
        task.name = new_name
        task.save(update_fields=["name"])
        existing_names.add(new_name)


class Migration(migrations.Migration):

    dependencies = [
        ('db_models', '0035_self_healing_setting_env_unique'),
        # 读取 PeriodicTask 历史模型需 beat 表就位
        ('django_celery_beat', '0015_edit_solarschedule_events_choices'),
    ]

    operations = [
        migrations.RunPython(rename_inspection_cron_tasks,
                             migrations.RunPython.noop),
    ]
