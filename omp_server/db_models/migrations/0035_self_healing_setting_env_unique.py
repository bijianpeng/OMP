# 基于 Django 3.1.4 makemigrations 产物手工改写（2026-11-15，Task 7b）
#
# SelfHealingSetting.env 加 unique=True（自愈策略 per-env 单行）：
# - 兜底 SelfHealingSettingView.list 的 get_or_create 并发竞态与
#   serializer 查重漏网（每环境至多一行配置）；
# - AlterField 前先 RunPython 防御性去重：同环境多行时保留首行
#   （0034 已回填存量行全部归属环境，理论上无重复行，防御存量脏数据）；
# - 剔除 autodetector 顺带检出的 3 个预存在字段漂移
#   （backupcustom.notes / backuphistory.retain_path / customscript.enabled），
#   与 Task 1/2 基线一致，保持变更范围严格。
# env 字段 null=True：唯一约束对 NULL 行不生效（MySQL/SQLite 均允许多
# NULL），未归属环境的行不受影响。

from django.db import migrations, models
import django.db.models.deletion


def dedup_self_healing_setting(apps, schema_editor):
    """同环境重复的自愈设置行保留首行（前向幂等，反向 noop）。

    统一走 _base_manager：迁移态历史模型上自定义 manager 不可用。
    """
    setting = apps.get_model("db_models", "SelfHealingSetting")
    seen_env_ids = set()
    duplicate_ids = []
    for row_id, env_id in setting._base_manager.exclude(
            env__isnull=True).order_by("id").values_list("id", "env_id"):
        if env_id in seen_env_ids:
            duplicate_ids.append(row_id)
        else:
            seen_env_ids.add(env_id)
    if duplicate_ids:
        setting._base_manager.filter(id__in=duplicate_ids).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('db_models', '0034_multi_env_ten_fk'),
    ]

    operations = [
        migrations.RunPython(dedup_self_healing_setting,
                             migrations.RunPython.noop),
        migrations.AlterField(
            model_name='selfhealingsetting',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.CASCADE, to='db_models.env', unique=True, verbose_name='环境'),
        ),
    ]
