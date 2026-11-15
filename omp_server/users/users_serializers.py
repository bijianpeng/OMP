# -*- coding: utf-8 -*-
# Project: users_serializers
# Author: omp
# Create time: 2021-09-10 17:16
# IDE: PyCharm
# Version: 1.0
# Introduction:

"""
用户序列化使用方法
"""
# 从 Django 认证模块导入用户认证函数，用于验证用户凭据
from django.contrib.auth import authenticate
# 从 Django 密码哈希模块导入密码加密函数，用于对用户密码进行加密
from django.contrib.auth.hashers import make_password

# 从 DRF 导入序列化器相关模块
from rest_framework import serializers
# 从 DRF 导入验证错误异常类，用于在验证失败时抛出异常
from rest_framework.exceptions import ValidationError
# 从 DRF 序列化器模块导入模型序列化器和基础序列化器类
from rest_framework.serializers import (
    ModelSerializer, Serializer
)
# 从 DRF JWT 序列化器模块导入 JWT 序列化器类
from rest_framework_jwt.serializers import JSONWebTokenSerializer

# 从数据库模型模块导入用户信息、操作日志、用户登录日志、环境与用户环境授权模型
from db_models.models import (
    UserProfile, OperateLog,
    UserLoginLog, Env, UserEnv
)
# 从工具通用验证器模块导入用户密码验证器类
from utils.common.validators import UserPasswordValidator
# 从工具加密模块导入 RSA 解密函数
from utils.plugin.crypto import decrypt_rsa


class UserSerializer(ModelSerializer):
    """ 用户序列化类，用于用户信息的序列化和反序列化。 """
    # 二次确认密码字段，只用于写入操作，必填
    re_password = serializers.CharField(
        max_length=32, required=True,
        write_only=True,
        error_messages={"required": "必须包含re_password字段"},
        help_text="二次确认密码")
    # 邮箱字段，必填，会验证邮箱格式
    email = serializers.EmailField(
        required=True,
        error_messages={"required": "必须包含email字段", "invalid": "邮箱格式不正确"},
        help_text="电子邮件")
    # 密码字段，只用于写入操作，必填
    password = serializers.CharField(
        max_length=32, required=True,
        write_only=True,
        error_messages={"required": "必须包含password字段"},
        help_text="密码")
    # 用户名字段，必填
    username = serializers.CharField(
        max_length=32, required=True,
        error_messages={"required": "必须包含名字"},
        help_text="用户名")
    # 用户授权环境 id 列表，选填，仅写入；视图在保存后全量同步 UserEnv
    # （role 为 superuser 的用户不写 UserEnv 行，收到 envs 也会被忽略）
    envs = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Env.objects.all(), required=False,
        write_only=True,
        help_text="用户授权环境 id 列表（全量覆盖）")
    # 用户授权环境名称列表，只读输出（与 envs 顺序一致）
    env_names = serializers.SerializerMethodField(
        help_text="用户授权环境名称列表")

    class Meta:
        """ 元数据类，用于配置序列化器关联的模型和字段。 """
        model = UserProfile  # 指定关联的模型为 UserProfile
        fields = ("id", "username", "password", "email", "re_password",
                  "date_joined", "is_active", "is_superuser", "role",
                  "envs", "env_names")  # 指定序列化的字段
        read_only_fields = ("date_joined", "is_active", "is_superuser")  # 指定只读字段

    def get_env_names(self, obj):
        """
        获取用户授权环境名称列表（按环境 id 升序，与 envs 输出顺序一致）。

        :param obj: 用户实例
        :return: 环境名称列表
        """
        return list(
            UserEnv.objects.filter(user=obj).order_by("env_id")
            .values_list("env__name", flat=True))

    def to_representation(self, instance):
        """
        输出补充 envs 字段（授权环境 id 列表）。

        envs 为纯写入字段（UserProfile 无该关联属性），
        因此读输出在此处由 UserEnv 表组装，与 env_names 保持同序。

        :param instance: 用户实例
        :return: 序列化后的数据字典
        """
        data = super(UserSerializer, self).to_representation(instance)
        data["envs"] = list(
            UserEnv.objects.filter(user=instance).order_by("env_id")
            .values_list("env_id", flat=True))
        return data

    def validate_username(self, username):
        """
        校验用户名是否唯一，非 PUT 请求时检查用户名是否已存在。

        :param username: 用户名
        :return: 校验通过的用户名
        """
        request = self.context["request"]
        if request.method != "PUT" and \
                UserProfile.objects.filter(username=username).count() != 0:
            raise ValidationError("用户名已存在")
        return username

    def validate(self, attrs):
        """
        校验密码和二次确认密码是否一致，并对密码进行加密处理。

        partial PATCH（如编辑超管只发 {email}）不会携带
        password / re_password，此时跳过密码校验与加密，
        避免缺 re_password 抛 KeyError、缺 password 时把密码覆盖为不可用密码。

        :param attrs: 包含序列化数据的字典
        :return: 校验并处理后的字典
        """
        password = attrs.get('password')
        re_password = attrs.pop('re_password', None)
        if password is not None and password != re_password:
            raise ValidationError({'re_password': '两次密码不一致'})
        if password is not None:
            attrs["password"] = make_password(password)  # 对密码进行加密
        return attrs


class OperateLogSerializer(ModelSerializer):
    """ 用户操作记录序列化类，用于用户操作记录的序列化。 """

    # 自定义创建时间字段，通过方法获取格式化后的时间
    create_time = serializers.SerializerMethodField()

    class Meta:
        """ 元数据类，用于配置序列化器关联的模型和字段。 """
        model = OperateLog  # 指定关联的模型为 OperateLog
        fields = (
            "id", "username", "request_ip", "request_method",
            "description", "create_time"
        )  # 指定序列化的字段

    def get_create_time(self, obj):
        """
        获取格式化后的创建时间，去除毫秒部分。

        :param obj: 操作记录对象
        :return: 格式化后的创建时间
        """
        if obj.create_time:
            return str(obj.create_time).split(".")[0]
        return obj.create_time


class UserLoginOperateSerializer(ModelSerializer):
    """登录记录序列化类，用于用户登录记录的序列化。 """

    # 自定义登录时间字段，通过方法获取格式化后的时间
    login_time = serializers.SerializerMethodField()

    class Meta:
        """ 元数据类，用于配置序列化器关联的模型和字段。 """
        model = UserLoginLog  # 指定关联的模型为 UserLoginLog
        fields = "__all__"  # 指定序列化所有字段

    def get_login_time(self, obj):
        """
        获取格式化后的登录时间，去除毫秒部分。

        :param obj: 登录记录对象
        :return: 格式化后的登录时间
        """
        if obj.login_time:
            return str(obj.login_time).split(".")[0]
        return obj.login_time


class JwtSerializer(JSONWebTokenSerializer):
    """ Jwt序列化类，继承自 JSONWebTokenSerializer，添加 remember 字段。 """

    # remember 字段，用于标记是否记住用户，非必填，默认值为 False
    remember = serializers.BooleanField(
        required=False, default=False,
        help_text="Boolean类型，缺省值为False")

    def validate(self, attrs):
        """
        验证并添加 remember 字段到验证结果中。

        :param attrs: 包含序列化数据的字典
        :return: 验证并处理后的字典
        """
        validate_dict = super(JwtSerializer, self).validate(attrs)
        validate_dict["remember"] = attrs.get("remember")
        return validate_dict


class UserUpdatePasswordSerializer(Serializer):
    """ 用户更新密码序列化器，用于用户密码更新操作的数据验证。 """

    # 用户名字段，必填，长度固定为 344
    username = serializers.CharField(
        help_text="用户名",
        min_length=344, max_length=344, required=True,
        error_messages={"required": "必须包含名字"})
    # 原密码字段，必填，长度固定为 344
    old_password = serializers.CharField(
        help_text="原密码", required=True,
        min_length=344, max_length=344,
        error_messages={"required": "必须包含password字段"}
    )
    # 新密码字段，必填，长度固定为 344
    new_password = serializers.CharField(
        help_text="新密码", required=True,
        min_length=344, max_length=344,
        error_messages={"required": "必须包含new_password字段"}
    )

    def validate(self, attrs):
        """
        校验用户的原密码是否正确，并验证新密码的格式。

        :param attrs: 包含序列化数据的字典
        :return: 校验并处理后的字典
        """
        credentials = {
            "username": decrypt_rsa(attrs.get("username")),  # 对用户名进行 RSA 解密
            "password": decrypt_rsa(attrs.get("old_password"))  # 对原密码进行 RSA 解密
        }
        user = authenticate(**credentials)  # 验证用户凭据
        if not user:
            raise ValidationError({"old_password": "当前密码不正确"})
        new_password = decrypt_rsa(attrs.get("new_password"))  # 对新密码进行 RSA 解密
        UserPasswordValidator()(new_password, self.fields.get("new_password"))  # 验证新密码格式
        attrs["user_obj"] = user
        attrs["new_password"] = new_password
        return attrs

    def create(self, validated_data):
        """ 用户密码加密入库，更新用户密码并保存。

        :param validated_data: 验证后的数据
        :return: 处理后的数据
        """
        user = validated_data["user_obj"]
        user.set_password(validated_data.get("new_password"))  # 设置新密码并加密
        user.save()
        return validated_data
