from django.contrib.auth.models import AbstractUser
from django.db import models

from .env import Env


class UserProfile(AbstractUser):
    """ 自定义用户表 """
    role = models.CharField("用户角色", max_length=128, null=True, blank=True, help_text="用户角色")

    class Meta:
        """ 元数据 """
        db_table = "omp_user_profile"
        verbose_name = verbose_name_plural = "用户"

    def __str__(self):
        """ 显示用户 """
        return f"用户: {self.username}"


class OperateLog(models.Model):
    """ 用户操作记录表 """

    objects = None
    username = models.CharField(
        "操作用户", max_length=128, help_text="操作用户")
    request_method = models.CharField(
        "请求方法", max_length=32, help_text="请求方法")
    request_ip = models.GenericIPAddressField(
        "请求源IP", blank=True, null=True, help_text="请求源IP")
    request_url = models.CharField(
        "用户目标URL", max_length=256, help_text="用户目标URL")
    description = models.CharField(
        "用户行为描述", max_length=256, help_text="用户行为描述")
    response_code = models.IntegerField(
        "响应状态码", default=0, help_text="响应状态码")
    request_result = models.TextField(
        "请求结果", default="success", help_text="请求结果")
    create_time = models.DateTimeField(
        "操作发生时间", auto_now_add=True, help_text="操作发生时间")
    env = models.ForeignKey(
        Env, null=True, blank=True, default=1,
        on_delete=models.SET_NULL,
        verbose_name="环境", help_text="环境")

    class Meta:
        """ 元数据 """
        db_table = "omp_user_operate_log"
        verbose_name = verbose_name_plural = "用户操作记录"


class UserLoginLog(models.Model):
    """用户登陆记录"""
    objects = None
    username = models.CharField(max_length=128, verbose_name="Username")
    login_time = models.DateTimeField(
        blank=True, null=True, verbose_name="Login time")
    ip = models.CharField(max_length=32, null=True,
                          blank=True, verbose_name="Login ip")
    role = models.CharField(
        max_length=128, verbose_name="role ", null=True, blank=True)
    request_result = models.CharField(
        "请求结果", max_length=512,
        null=True, blank=True, help_text="请求结果")

    class Meta:
        db_table = "omp_login_log"
        verbose_name = verbose_name_plural = "用户登陆记录"


class UserEnv(models.Model):
    """ 用户环境授权表 """

    objects = None
    user = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE,
        verbose_name="授权用户", help_text="授权用户")
    env = models.ForeignKey(
        Env, on_delete=models.CASCADE,
        verbose_name="授权环境", help_text="授权环境")

    class Meta:
        """ 元数据 """
        db_table = "omp_user_env"
        unique_together = ("user", "env")
        verbose_name = verbose_name_plural = "用户环境授权"
