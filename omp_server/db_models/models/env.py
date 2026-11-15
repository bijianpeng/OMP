from django.db import models


class Env(models.Model):
    """ 环境表 """

    objects = None
    name = models.CharField(
        "环境名称", max_length=256, help_text="环境名称")
    code = models.CharField(
        "环境标识", max_length=64, unique=True, blank=True,
        help_text="环境英文标识，用于监控规则文件名与 PromQL label，"
                  "创建后不可修改；存量 default 环境由迁移回填")
    description = models.CharField(
        "环境描述", max_length=255, blank=True, default="",
        help_text="环境描述")
    created = models.DateTimeField(
        '创建时间', null=True, auto_now_add=True, help_text='创建时间')

    class Meta:
        db_table = "omp_env"
        verbose_name = verbose_name_plural = "环境"
