# 基于 Django 3.1.4 makemigrations 产物手工改写（2026-11-15）
#
# 已安装产品表（omp_product_instance）新增 env FK(Env)：
# 应用商店产品卡片"已安装数量"按环境隔离统计（验收反馈修复）。
# - Product 为历史记录类实例表：SET_NULL + null=True（T3 十表惯例）；
# - default=1：存量代码路径（安装编排三处创建点）未传 env 时防
#   IntegrityError，新创建点已同步写 env；
# - AddField 后 RunPython 回填存量 env=1（幂等，反向 noop）；
# - 剔除 autodetector 顺带检出的 3 个预存在字段漂移
#   （backupcustom.notes / backuphistory.retain_path /
#   customscript.enabled），与本任务无关，保持变更范围严格。

from django.db import migrations, models
import django.db.models.deletion


def backfill_product_env(apps, schema_editor):
    """存量产品实例归默认环境 1（前向幂等，反向 noop）

    统一走 _base_manager：迁移态历史模型上自定义 manager 不可用
    （Product.objects 为 None 占位，历史类无该属性）。
    """
    Product = apps.get_model("db_models", "Product")
    Product._base_manager.filter(env__isnull=True).update(env_id=1)


class Migration(migrations.Migration):

    dependencies = [
        ('db_models', '0036_inspection_cron_task_env_prefix'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='env',
            field=models.ForeignKey(blank=True, default=1, help_text='环境', null=True, on_delete=django.db.models.deletion.SET_NULL, to='db_models.env', verbose_name='环境'),
        ),
        migrations.RunPython(backfill_product_env,
                             migrations.RunPython.noop),
    ]
