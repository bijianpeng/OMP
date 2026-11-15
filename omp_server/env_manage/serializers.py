# -*- coding: utf-8 -*-
"""
环境管理序列化器（多环境架构 Task 5）
"""
import re

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from db_models.models import Env

# 环境标识：字母开头，仅字母/数字/下划线/中划线，最长 64（含首字符）
ENV_CODE_REGEX = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")

ENV_CODE_ERROR_MESSAGE = (
    "环境标识须以字母开头，仅含字母、数字、下划线、中划线，最长64位")


class EnvCreateSerializer(serializers.ModelSerializer):
    """ 环境创建序列化器：name/code 必填，config_source 可选 """
    code = serializers.CharField(
        max_length=64, required=True,
        error_messages={"required": "必须包含code字段"},
        help_text="环境标识，创建后不可修改")
    config_source = serializers.IntegerField(
        required=False, allow_null=True, default=None,
        help_text="配置复制来源环境 id，null/缺省表示创建空环境")

    class Meta:
        model = Env
        fields = ("id", "name", "code", "description",
                  "created", "config_source")
        read_only_fields = ("id", "created")

    def validate_code(self, code):
        """
        校验环境标识格式（Global Constraints 约定的 slug 正则）

        :param code: 环境标识字符串
        :return: 校验通过的环境标识
        """
        if not ENV_CODE_REGEX.match(code or ""):
            raise ValidationError(ENV_CODE_ERROR_MESSAGE)
        return code

    def validate_config_source(self, config_source):
        """
        校验配置复制来源环境存在

        :param config_source: 来源环境 id 或 None
        :return: 校验通过的来源环境 id
        """
        if config_source is not None and \
                not Env.objects.filter(id=config_source).exists():
            raise ValidationError("配置复制来源环境不存在")
        return config_source


class EnvUpdateSerializer(serializers.ModelSerializer):
    """ 环境修改序列化器：仅 name/description 可改，code 只读拒改 """

    class Meta:
        model = Env
        fields = ("id", "name", "code", "description", "created")
        read_only_fields = ("id", "created", "code")


class EnvListSerializer(serializers.ModelSerializer):
    """ 环境列表序列化器：附主机/服务资源统计 """
    host_count = serializers.IntegerField(
        read_only=True, help_text="环境主机数")
    service_count = serializers.IntegerField(
        read_only=True, help_text="环境服务数")
    created = serializers.SerializerMethodField()

    class Meta:
        model = Env
        fields = ("id", "name", "code", "description", "created",
                  "host_count", "service_count")

    def get_created(self, obj):
        """
        获取格式化后的创建时间（去除毫秒，与平台其它序列化器一致）

        :param obj: 环境实例
        :return: 格式化时间字符串
        """
        if obj.created:
            return str(obj.created).split(".")[0]
        return obj.created


class EnvUsersSerializer(serializers.Serializer):
    """ 环境用户授权序列化器：user_ids 全量覆盖 """
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True, allow_empty=True,
        help_text="授权用户 id 列表，全量覆盖")
