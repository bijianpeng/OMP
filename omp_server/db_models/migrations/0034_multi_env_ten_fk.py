# 基于 Django 3.1.4 makemigrations 产物手工改写（2026-11-14）
#
# 十张安装/执行/备份/工具/自愈/操作日志表新增 env FK(Env)：
# - SelfHealingSetting / WaitSelfHealing 为环境级配置或瞬时状态，CASCADE；
# - 其余八张为历史记录类，SET_NULL + null=True；
# - 十表均带 default=1：存量代码路径均会创建这些模型的实例且未传 env，
#   裸 FK 会让创建点当场 IntegrityError（Task 2 惯例）。
# AddField 后 RunPython 回填存量；剔除 autodetector 顺带检出的 3 个
# 预存在字段漂移（backupcustom.notes / backuphistory.retain_path /
# customscript.enabled），与本任务无关，保持变更范围严格。

import json
from collections import defaultdict

from django.db import migrations, models
import django.db.models.deletion

# 本任务新增 env FK 的十张表（历史模型名）
NEW_ENV_MODEL_NAMES = (
    "MainInstallHistory",
    "DeploymentPlan",
    "ExecutionRecord",
    "BackupSetting",
    "BackupHistory",
    "ToolExecuteMainHistory",
    "WaitSelfHealing",
    "SelfHealingSetting",
    "SelfHealingHistory",
    "OperateLog",
)

# 已有 env FK 的表：存量 NULL 属异常（历史写入未带 env），统一归默认环境 1
EXISTING_ENV_MODEL_NAMES = (
    "Host",
    "Service",
    "InspectionHistory",
    "InspectionCrontab",
    "UpgradeHistory",
    "RollbackHistory",
)

# 巡检定时任务（**kwargs 签名，读取 kwargs["env"]）
INSPECTION_CRONTAB_TASK = "inspection.tasks.inspection_crontab"


def backfill_env_data(apps, schema_editor):
    """存量数据回填（前向幂等，反向 noop）：
    1. 新十表存量行归默认环境 1；已有 FK 六表 NULL 行归 1；
    2. Alert 按告警主机 IP 反查 Host.env（Host NULL 已先归 1，无悬空），
       反查不到主机的归 1，已有 env 的行不动；
    3. 存量非 superuser 用户补默认环境授权 UserEnv(env=1)；
    4. 存量巡检 PeriodicTask 的 kwargs 无 "env" 键时补 "env": 1。
    统一走 _base_manager：迁移态历史模型上自定义 manager 不可用
    （如 Service 的 .objects 是过滤型 manager，历史类无该属性）。
    """
    for name in NEW_ENV_MODEL_NAMES + EXISTING_ENV_MODEL_NAMES:
        model = apps.get_model("db_models", name)
        model._base_manager.filter(env__isnull=True).update(env_id=1)

    Host = apps.get_model("db_models", "Host")
    Alert = apps.get_model("db_models", "Alert")
    ip_env = dict(
        Host._base_manager.exclude(env__isnull=True)
        .values_list("ip", "env_id"))
    alert_envs = defaultdict(list)
    null_alerts = Alert._base_manager.filter(
        env__isnull=True).values_list("id", "alert_host_ip")
    for alert_id, alert_ip in null_alerts:
        alert_envs[ip_env.get(alert_ip) or 1].append(alert_id)
    for env_id, alert_ids in alert_envs.items():
        Alert._base_manager.filter(id__in=alert_ids).update(env_id=env_id)

    UserProfile = apps.get_model("db_models", "UserProfile")
    UserEnv = apps.get_model("db_models", "UserEnv")
    for user in UserProfile._base_manager.exclude(role="superuser"):
        UserEnv._base_manager.get_or_create(user=user, env_id=1)

    # 只补巡检任务：inspection_crontab(**kwargs) 容忍并读取 env；
    # self_healing(task_id) 等严格签名任务补 env 会在 beat 触发时
    # TypeError，保持不动
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    for task in PeriodicTask._base_manager.filter(
            task=INSPECTION_CRONTAB_TASK):
        try:
            kwargs = json.loads(task.kwargs) if task.kwargs else {}
        except ValueError:
            continue
        if isinstance(kwargs, dict) and "env" not in kwargs:
            kwargs["env"] = 1
            task.kwargs = json.dumps(kwargs)
            task.save(update_fields=["kwargs"])


class Migration(migrations.Migration):

    dependencies = [
        ('db_models', '0033_multi_env_config_fk'),
        # RunPython 需读取 PeriodicTask 做存量巡检任务 kwargs 回填，
        # 跨 app 取历史模型必须声明对 beat 迁移的依赖（其表已就位）
        ('django_celery_beat', '0015_edit_solarschedule_events_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='maininstallhistory',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.SET_NULL, to='db_models.env', verbose_name='环境'),
        ),
        migrations.AddField(
            model_name='deploymentplan',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.SET_NULL, to='db_models.env', verbose_name='环境'),
        ),
        migrations.AddField(
            model_name='executionrecord',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.SET_NULL, to='db_models.env', verbose_name='环境'),
        ),
        migrations.AddField(
            model_name='backupsetting',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.SET_NULL, to='db_models.env', verbose_name='环境'),
        ),
        migrations.AddField(
            model_name='backuphistory',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.SET_NULL, to='db_models.env', verbose_name='环境'),
        ),
        migrations.AddField(
            model_name='toolexecutemainhistory',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.SET_NULL, to='db_models.env', verbose_name='环境'),
        ),
        migrations.AddField(
            model_name='waitselfhealing',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.CASCADE, to='db_models.env', verbose_name='环境'),
        ),
        migrations.AddField(
            model_name='selfhealingsetting',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.CASCADE, to='db_models.env', verbose_name='环境'),
        ),
        migrations.AddField(
            model_name='selfhealinghistory',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.SET_NULL, to='db_models.env', verbose_name='环境'),
        ),
        migrations.AddField(
            model_name='operatelog',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.SET_NULL, to='db_models.env', verbose_name='环境'),
        ),
        migrations.RunPython(backfill_env_data,
                             migrations.RunPython.noop),
    ]
