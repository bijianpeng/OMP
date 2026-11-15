# 基于 Django 3.1.4 makemigrations 产物手工改写（2026-11-14）
#
# 六张环境配置表的裸整数 env_id 改为 FK(Env, CASCADE)。autodetector 对
# "字段改名 + 换类型"只会生成 RemoveField + AddField（会删列丢数据），故按
# 规范改写为：RunPython 清理脏数据 -> RenameField(env_id -> env) ->
# AlterField(整数 -> FK)，DB 列名保持 env_id，既有数据不变。
# 另剔除 autodetector 顺带检出的 3 个预存在字段漂移
# (backupcustom.notes / backuphistory.retain_path / customscript.enabled)，
# 与本任务无关，保持变更范围严格。

from django.db import migrations, models
import django.db.models.deletion

# 六张环境配置表（历史模型名）
CONFIG_MODEL_NAMES = (
    "HostThreshold",
    "ServiceThreshold",
    "ServiceCustomThreshold",
    "AlertRule",
    "ModuleSendEmailSetting",
    "AlertSendWaySetting",
)


def clean_config_env_id(apps, schema_editor):
    """六张配置表脏 env_id 清理（前向幂等）：
    - env_id=0 行删除（历史 default=0 产生的脏数据，而非归并）；
    - 指向不存在环境的非法 env_id 统一归并到默认环境 1
      （0032 已保证 id=1 默认环境存在）。
    """
    Env = apps.get_model("db_models", "Env")
    valid_ids = list(Env.objects.values_list("id", flat=True))
    for name in CONFIG_MODEL_NAMES:
        model = apps.get_model("db_models", name)
        # env_id=0 行直接删除
        model.objects.filter(env_id=0).delete()
        # 非法 env_id 归并默认环境 1
        model.objects.exclude(env_id__in=valid_ids).update(env_id=1)


class Migration(migrations.Migration):

    dependencies = [
        ('db_models', '0032_multi_env_env'),
    ]

    operations = [
        # 先清数据，保证 AlterField 加 FK 约束时全表现有行指向合法环境
        migrations.RunPython(clean_config_env_id,
                             migrations.RunPython.noop),
        migrations.RenameField(
            model_name='alertrule',
            old_name='env_id',
            new_name='env',
        ),
        migrations.AlterField(
            model_name='alertrule',
            name='env',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='db_models.env', verbose_name='环境'),
        ),
        migrations.RenameField(
            model_name='alertsendwaysetting',
            old_name='env_id',
            new_name='env',
        ),
        migrations.AlterField(
            model_name='alertsendwaysetting',
            name='env',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='db_models.env', verbose_name='环境'),
        ),
        migrations.RenameField(
            model_name='hostthreshold',
            old_name='env_id',
            new_name='env',
        ),
        migrations.AlterField(
            model_name='hostthreshold',
            name='env',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='db_models.env', verbose_name='环境'),
        ),
        migrations.RenameField(
            model_name='modulesendemailsetting',
            old_name='env_id',
            new_name='env',
        ),
        migrations.AlterField(
            model_name='modulesendemailsetting',
            name='env',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='db_models.env', verbose_name='环境'),
        ),
        migrations.RenameField(
            model_name='servicecustomthreshold',
            old_name='env_id',
            new_name='env',
        ),
        migrations.AlterField(
            model_name='servicecustomthreshold',
            name='env',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='db_models.env', verbose_name='环境'),
        ),
        migrations.RenameField(
            model_name='servicethreshold',
            old_name='env_id',
            new_name='env',
        ),
        migrations.AlterField(
            model_name='servicethreshold',
            name='env',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.CASCADE, to='db_models.env', verbose_name='环境'),
        ),
    ]
