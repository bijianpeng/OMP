# -*- coding: utf-8 -*-
"""
环境管理视图（多环境架构 Task 5）

设计要点：
- 本视图不依赖环境上下文（不调用 get_request_env）：环境列表按用户
  授权过滤（superuser 全量），与 X-Env-Id 无关——前端刷新会随请求
  携带 X-Env-Id（Task 16 交接），列表不得按其过滤；
- 环境增删改与授权管理仅 superuser：RoleAuthenticationMiddleware 已
  在运行时拦截非 superuser 的非 GET 请求，此处为视图层兜底校验
  （兼容 pytest 下中间件放行的测试链路）。
"""
import json
import logging

from django.db import transaction
from django.db.models import Count
from django_celery_beat.models import PeriodicTask

from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.mixins import (
    CreateModelMixin, DestroyModelMixin, ListModelMixin)
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from db_models.models import (
    BackupSetting, DeploymentPlan, Env, Host, MainInstallHistory,
    Service, UserEnv, UserProfile)
from env_manage.env_utils import copy_env_config
from env_manage.serializers import (
    EnvCreateSerializer, EnvListSerializer, EnvUpdateSerializer,
    EnvUsersSerializer)

logger = logging.getLogger("server")

# MainInstallHistory 非终态（待安装/安装中/正在注册）：存在时禁止删环境
INSTALL_RUNNING_STATUS = (
    MainInstallHistory.INSTALL_STATUS_READY,
    MainInstallHistory.INSTALL_STATUS_INSTALLING,
    MainInstallHistory.INSTALL_STATUS_REGISTER,
)

# 删除保护：环境存在以下资源关联时禁止删除（label 用于错误提示）；
# 计数走 _base_manager，避免自定义 manager（如 Service 拆分过滤）漏计
DELETE_PROTECT_MODELS = (
    ("主机", Host),
    ("服务", Service),
    ("部署计划", DeploymentPlan),
    ("备份设置", BackupSetting),
)


class EnvView(ListModelMixin, CreateModelMixin, DestroyModelMixin,
              GenericViewSet):
    """
        list:
        查询环境列表（superuser 全量；否则按 UserEnv 授权过滤）

        create:
        创建一个环境（superuser，可选从来源环境复制配置）

        partial_update:
        修改环境名称/描述（code 不可改）

        delete:
        删除一个环境（superuser，带资源/任务删除保护）

        users:
        环境-用户授权管理（superuser，user_ids 全量覆盖）
    """
    queryset = Env.objects.all().order_by("id")
    serializer_class = EnvListSerializer
    pagination_class = None

    get_description = "获取环境列表"
    post_description = "创建环境"
    patch_description = "修改环境"
    delete_description = "删除环境"

    @staticmethod
    def _is_superuser(request):
        """ 判断请求用户是否超级管理员（与中间件 role 映射一致） """
        return (getattr(request.user, "role", None) or "").lower() == "superuser"

    def _check_superuser(self, request):
        """ 非超级管理员访问环境管理接口时抛出权限异常 """
        if not self._is_superuser(request):
            raise PermissionDenied("仅超级管理员可管理环境")

    def get_queryset(self):
        """
        superuser 返回全量环境；非 superuser 仅返回其被授权
        （UserEnv 记录）的环境，与 X-Env-Id 无关
        """
        queryset = super(EnvView, self).get_queryset()
        if not self._is_superuser(self.request):
            queryset = queryset.filter(userenv__user=self.request.user)
        return queryset

    def list(self, request, *args, **kwargs):
        """ 环境列表：annotate 主机/服务资源统计 """
        queryset = self.get_queryset().annotate(
            host_count=Count("host", distinct=True),
            service_count=Count("service", distinct=True))
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        """ 创建环境；config_source 非 None 时从来源环境复制配置 """
        self._check_superuser(request)
        serializer = EnvCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        config_source = serializer.validated_data.pop("config_source", None)
        with transaction.atomic():
            env = serializer.save()
            if config_source is not None:
                copy_env_config(config_source, env.id)
        return Response(EnvCreateSerializer(env).data)

    def partial_update(self, request, *args, **kwargs):
        """ 修改环境名称/描述（code 只读，提交亦被忽略） """
        self._check_superuser(request)
        env = self.get_object()
        serializer = EnvUpdateSerializer(
            env, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """
        删除环境：默认环境/存在关联资源/存在进行中安装任务时拒绝；
        通过后删除（配置经 CASCADE 清理、UserEnv 级联清理），并注销
        该环境的 celery beat 周期任务（kwargs 携带 env/env_id 的任务）
        """
        self._check_superuser(request)
        env = self.get_object()
        if env.id == 1:
            raise ValidationError("默认环境不可删除")
        existed = [
            (label, model._base_manager.filter(env=env).count())
            for label, model in DELETE_PROTECT_MODELS]
        existed = [(label, count) for label, count in existed if count > 0]
        if existed:
            detail = "、".join(
                f"{label} {count}" for label, count in existed)
            raise ValidationError(
                f"环境下仍存在关联资源（{detail}），无法删除")
        running_count = MainInstallHistory._base_manager.filter(
            env=env, install_status__in=INSTALL_RUNNING_STATUS).count()
        if running_count:
            raise ValidationError(
                f"环境下存在 {running_count} 个进行中的安装任务，无法删除")
        self.remove_env_periodic_tasks(env)
        # Model.delete() 会把实例 pk 置 None，删除前先记录 id
        deleted_env_id = env.id
        env.delete()
        # 防御：删除的环境正是本次请求的环境上下文（X-Env-Id 指向自身）
        # 时，内存中的 request.env 已指向被删行——清掉引用，避免
        # OperationLogMiddleware 在响应阶段用它写 OperateLog 触发 FK 违反
        # （删除已生效但响应 500）。注意两点：
        # 1. DRF Request 只代理属性读取，写入必须落到底层 HttpRequest
        #    （process_response 阶段中间件持有的是底层 request）；
        # 2. 比较 id 而非实例（EnvContextMiddleware 与 get_object 是
        #    两个不同实例）。
        raw_request = getattr(request, "_request", request)
        request_env = getattr(raw_request, "env", None)
        if request_env is not None and request_env.id == deleted_env_id:
            raw_request.env = None
        return Response()

    @staticmethod
    def remove_env_periodic_tasks(env):
        """
        注销该环境的 celery beat 周期任务

        PeriodicTask.kwargs 为 JSON 字符串，逐条解析判断 kwargs 中的
        env/env_id 是否命中该环境后删除（巡检任务携带 env、备份任务
        携带 env_id，见设计 §6.5）

        :param env: 环境实例
        :return: None
        """
        for task in PeriodicTask.objects.all().only("id", "name", "kwargs"):
            try:
                kwargs = json.loads(task.kwargs) if task.kwargs else {}
            except ValueError:
                continue
            if not isinstance(kwargs, dict):
                continue
            if kwargs.get("env") == env.id or kwargs.get("env_id") == env.id:
                logger.info(f"remove periodic task {task.name} of env {env.id}")
                task.delete()

    @action(methods=["get", "patch"], detail=True, url_path="users")
    def users(self, request, pk=None):
        """
        环境-用户授权管理：GET 返回当前授权，PATCH user_ids 全量覆盖
        """
        self._check_superuser(request)
        env = self.get_object()
        if request.method == "PATCH":
            serializer = EnvUsersSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user_ids = serializer.validated_data.get("user_ids")
            exists_ids = set(
                UserProfile.objects.filter(id__in=user_ids)
                .values_list("id", flat=True))
            missing_ids = [
                user_id for user_id in user_ids if user_id not in exists_ids]
            if missing_ids:
                raise ValidationError(f"用户不存在: {missing_ids}")
            with transaction.atomic():
                # 全量覆盖：删除未保留的授权，补齐新增的授权
                UserEnv.objects.filter(env=env).exclude(
                    user_id__in=user_ids).delete()
                for user_id in user_ids:
                    UserEnv.objects.get_or_create(env=env, user_id=user_id)
        user_envs = UserEnv.objects.filter(env=env).select_related(
            "user").order_by("user_id")
        return Response({
            "env_id": env.id,
            "user_ids": [user_env.user_id for user_env in user_envs],
            "users": [
                {"id": user_env.user_id, "username": user_env.user.username}
                for user_env in user_envs],
        })
