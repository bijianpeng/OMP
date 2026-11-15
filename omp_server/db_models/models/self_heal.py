from django.db import models
from django.core.validators import MaxValueValidator

from .env import Env


class WaitSelfHealing(models.Model):
    # 0 等待自愈 1 自愈中 存在自愈中的服务不被允许再次触发自愈，保证自愈过程中只有一个自愈在进行。
    service_name = models.CharField("自愈服务名称", max_length=64, default="")
    repair_ser = models.JSONField("自愈缓存服务详情", default=dict)
    repair_status = models.IntegerField("自愈缓存服务", default=0)
    # 瞬时状态表：随环境删除级联清理
    env = models.ForeignKey(
        Env, null=True, blank=True, default=1,
        on_delete=models.CASCADE,
        verbose_name="环境", help_text="环境")

    class Meta:
        db_table = "omp_wait_self_healing"  # 数据库表名
        verbose_name = verbose_name_plural = "自愈等待队列"  # 模型在管理界面中的显示名称


class SelfHealingSetting(models.Model):
    """
    自愈策略设置模型
    用于配置自愈策略的各项参数
    """
    # 修复操作类型选项
    REPAIR_CHOICES = [
        (0, "启动"),
        (1, "重新启动")
    ]

    used = models.BooleanField("是否启用", default=False)
    max_healing_count = models.IntegerField("最多自愈操作次数", default=5, validators=[MaxValueValidator(20)])
    fresh_rate = models.IntegerField("周期内采集告警消息频次", default=10, validators=[MaxValueValidator(60)])
    instance_tp = models.IntegerField("实例类别", choices=REPAIR_CHOICES, default=0)
    repair_instance = models.JSONField("修复实例", default=dict, blank=False, null=False)
    # 环境级配置：随环境删除级联清理；每环境至多一行（自愈策略 per-env
    # 唯一，兜底 get_or_create 竞态与查重漏网——多环境架构 Task 7b）
    env = models.ForeignKey(
        Env, null=True, blank=True, default=1,
        on_delete=models.CASCADE,
        unique=True,
        verbose_name="环境", help_text="环境")

    class Meta:
        db_table = "omp_self_healing_setting"  # 数据库表名
        verbose_name = verbose_name_plural = "自愈设置"  # 模型在管理界面中的显示名称


class SelfHealingHistory(models.Model):
    """自愈历史记录"""
    is_read = models.IntegerField("此消息是否已读，0-未读；1-已读", default=0)
    host_ip = models.CharField("自愈主机ip", max_length=64)
    service_name = models.CharField("自愈服务名称", max_length=64, default="")
    instance_name = models.CharField("自愈实例名称", max_length=128, default="", help_text="自愈实例名称")
    HEALING_FAIL = 0
    HEALING_ING = 2
    HEALING_SUCCESS = 1
    STATE_CHOICES = (
        (HEALING_ING, "自愈中"),
        (HEALING_FAIL, "自愈失败"),
        (HEALING_SUCCESS, "自愈成功")
    )
    state = models.IntegerField("自愈状态", choices=STATE_CHOICES, default=HEALING_ING)
    healing_count = models.IntegerField("已运行自愈次数", default=0)
    start_time = models.DateTimeField("自愈开始时间", null=True)
    end_time = models.DateTimeField("自愈结束时间", null=True)
    healing_log = models.TextField("自愈日志", default="")
    alert_time = models.DateTimeField("关联告警时间，与fingerprint确定同一次告警", null=True)
    alert_content = models.TextField("告警日志内容", default="")
    monitor_log = models.TextField("grafana日志url", default="")
    env = models.ForeignKey(
        Env, null=True, blank=True, default=1,
        on_delete=models.SET_NULL,
        verbose_name="环境", help_text="环境")

    class Meta:
        db_table = "omp_self_healing_history"  # 数据库表名
        verbose_name = verbose_name_plural = "自愈历史记录"  # 模型在管理界面中的显示名称
