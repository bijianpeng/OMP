# 导入操作系统相关功能模块，用于处理文件路径等操作
import os

# 从 django 数据库模块导入模型基类
from django.db import models

# 从自定义的 mixins 模块导入时间戳混合类
from db_models.mixins import TimeStampMixin
# 从当前目录的 env 模块导入 Env 类
from .env import Env


class BackupCustom(models.Model):
    """
    自定义备份字段模型，用于存储自定义备份相关的字段信息。
    """
    # 自定义字段 k，最大长度为 64，不允许为空
    field_k = models.CharField("自定义字段k", max_length=64, null=False)
    # 自定义字段 v，最大长度为 256，不允许为空
    field_v = models.CharField("自定义字段v", max_length=256, null=False)
    # 备注信息，最大长度为 32，默认值为空字符串
    notes = models.CharField("备注", max_length=32, default="")

    class Meta:
        # 数据库表名
        db_table = 'omp_backup_custom'
        # 模型的单数和复数显示名称
        verbose_name = verbose_name_plural = '自定义备份'


class BackupSetting(models.Model):
    """
    备份设置模型，用于存储备份服务的相关设置信息。
    """
    # 备份服务实例名称，以 JSON 格式存储，默认值为空字典
    backup_instances = models.JSONField("备份服务实例名称", default=dict)
    # 是否开启备份服务，布尔类型，默认值为 False
    is_on = models.BooleanField("是否开启", default=False)
    # 定时任务详情，以 JSON 格式存储
    crontab_detail = models.JSONField("定时任务详情")
    # 文件保存天数，整数类型，默认值为 1
    retain_day = models.IntegerField("文件保存天数", default=1)
    # 文件保存路径，最大长度为 256，不允许为空，默认值为指定路径
    retain_path = models.CharField("文件保存路径", default="/data/omp/data/backup/",
                                   null=False, max_length=256)
    # 与 BackupCustom 模型建立多对多关系
    backup_custom = models.ManyToManyField(BackupCustom)
    env = models.ForeignKey(
        Env, null=True, blank=True, default=1,
        on_delete=models.SET_NULL,
        verbose_name="环境", help_text="环境")

    class Meta:
        # 数据库表名
        db_table = 'omp_backup_setting'
        # 模型的单数和复数显示名称
        verbose_name = verbose_name_plural = '备份设置'


class BackupHistory(TimeStampMixin):
    """
    备份历史记录模型，用于存储备份任务的历史信息，继承自 TimeStampMixin 类。
    """
    # 备份任务名称，最大长度为 128
    backup_name = models.CharField("备份任务名称", max_length=128)
    # 备份实例信息，最大长度为 256，默认值为空字符串
    content = models.CharField('备份实例', max_length=256, default="")
    # 备份成功状态码
    SUCCESS = 1
    # 备份进行中状态码
    ING = 2
    # 备份失败状态码
    FAIL = 0
    # 备份结果的可选值元组，包含状态码和对应的中文描述
    RESULT_CHOICES = (
        (SUCCESS, "成功"),
        (ING, "备份中"),
        (FAIL, "失败")
    )
    # 备份结果，整数类型，可选值为 RESULT_CHOICES 中的值，默认值为 ING
    result = models.IntegerField("结果", choices=RESULT_CHOICES, default=ING)
    # 备份返回信息，文本类型，最大长度为 512，默认值为空字符串
    message = models.TextField("返回信息", default="", max_length=512)
    # 备份文件名，最大长度为 128，默认值为空字符串
    file_name = models.CharField("备份文件名", max_length=128, default="")
    # 备份文件大小，单位为 MB，最大长度为 64，默认值为 "0"
    file_size = models.CharField("备份文件大小, MB", default="0", max_length=64)
    # 备份文件的过期时间，日期时间类型，允许为空
    expire_time = models.DateTimeField("过期时间", null=True)
    # 文件是否被删除，布尔类型，默认值为 False
    file_deleted = models.BooleanField("文件是否被删除", default=False)
    # 记录生成时间，日期时间类型，在创建记录时自动设置
    create_time = models.DateTimeField("记录生成时间", auto_now_add=True)
    # 文件保存路径，文本类型，最大长度为 256，允许为空
    retain_path = models.TextField(
        "文件保存路径", default="/data/omp/data/backup/", max_length=256, null=True, blank=True
    )
    # 远端备份路径，最大长度为 256，允许为空
    remote_path = models.CharField("远端备份路径", max_length=256, null=True, blank=True)
    # 冗余字段，以 JSON 格式存储，默认值为空字典
    extend_field = models.JSONField("冗余字段", default=dict)
    env = models.ForeignKey(
        Env, null=True, blank=True, default=1,
        on_delete=models.SET_NULL,
        verbose_name="环境", help_text="环境")

    class Meta:
        # 数据库表名
        db_table = 'omp_backup_history'
        # 模型的单数和复数显示名称
        verbose_name = verbose_name_plural = '备份历史记录'

    def fetch_file_kwargs(self):
        """
        获取备份文件的相关参数。

        :return: 包含备份文件路径的字典
        """
        # 拼接备份文件的完整路径
        file_path = os.path.join(self.retain_path, self.file_name)
        return {"path": file_path}
