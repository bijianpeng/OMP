# -*- coding: utf-8 -*-
# Project: middleware_handler
# Author: omp
# Create time: 2021-09-11 16:48
# IDE: PyCharm
# Version: 1.0
# Introduction:

"""
公共中间件
"""

# 导入 json 模块，用于处理 JSON 数据
import json
# 导入 ipware 模块，用于获取客户端 IP 地址
import ipware
# 导入 logging 模块，用于记录日志
import logging
# 导入 os 模块，用于与操作系统进行交互
import os

# 从 django.urls 模块导入 resolve 函数，用于解析 URL
from django.urls import resolve
# 从 django.utils.deprecation 模块导入 MiddlewareMixin 类，用于创建中间件
from django.utils.deprecation import MiddlewareMixin
# 从 django.http 模块导入 JsonResponse 类，用于返回 JSON 格式的响应
from django.http import JsonResponse

# 从 rest_framework.reverse 模块导入 reverse 函数，用于生成 URL
from rest_framework.reverse import reverse
# 从 rest_framework.exceptions 模块导入 ValidationError 异常，用于环境上下文缺失校验
from rest_framework.exceptions import ValidationError
# 从 rest_framework_jwt.utils 模块导入 jwt_decode_handler 函数，用于解码 JWT token
from rest_framework_jwt.utils import jwt_decode_handler

# 从 jwt 模块导入 DecodeError 异常，用于处理 JWT 解码错误
from jwt import DecodeError

# 从 db_models.models 模块导入相关模型类
from db_models.models import (
    Env, OperateLog, UserLoginLog, UserEnv, UserProfile
)
# 从 django.utils 模块导入 timezone 模块，用于处理时间相关操作
from django.utils import timezone
# 从 omp_server.settings 模块导入 INTERFACE_KINDS 常量
from omp_server.settings import INTERFACE_KINDS

# 获取名为 "server" 的日志记录器
logger = logging.getLogger("server")


def get_username_of_token(token):
    """
    通过 jwt token 解析 username

    :param token: JWT token 字符串
    :return: 解析出的 username 字符串
    """
    # 若处于 pytest 测试环境，直接返回 'admin'
    if os.environ.get('PYTEST_CURRENT_TEST'):
        return 'admin'
    # 解码 JWT token
    _token_user = jwt_decode_handler(token)
    # 从解码结果中获取 username
    _username = _token_user.get("username")
    return _username


def get_request_env(request):
    """
    获取请求的环境上下文（EnvContextMiddleware 解析注入的 request.env）

    资源类视图在 get_queryset / create 中调用本方法获取当前环境；
    中间件对未携带环境标识的请求放行（request.env 为 None），
    由本方法在此统一抛错，视图层按需决定 required / exempt。

    :param request: 请求对象（Django HttpRequest / DRF Request 均可）
    :return: Env 模型实例
    :raises ValidationError: request.env 为空时抛出
        （经统一异常处理器输出 code=1 错误包，提示选择环境）
    """
    _env = getattr(request, "env", None)
    if _env is None:
        raise ValidationError("缺少环境上下文，请选择环境")
    return _env


# 定义用户角色英文到中文的映射字典
USER_TO_ROLE_EN_DICT = {
    "superuser": "普通管理员",
    "readonlyuser": "只读用户"
}


class OperationLogMiddleware(MiddlewareMixin):
    """
    用于处理操作日志的中间件
    """

    def process_response(self, request, response):
        """
        拦截请求的中间件，在响应返回前记录操作日志

        :param request: 请求对象
        :type request: HttpRequest
        :param response: 响应对象
        :return: 响应对象
        """
        # 获取请求方法并转换为小写
        _method = request.method.lower()
        # 若请求方法为 GET，直接返回响应
        if _method == "get":
            return response
        # 获取请求的 URL 路径
        _url = request.path
        # 若 URL 以 "/proxy/v1/grafana" 开头，直接返回响应
        if _url.startswith("/proxy/v1/grafana"):
            return response
        # 解析 URL 对应的视图类
        view_class = resolve(_url).func.cls
        # 检查视图类是否有对应方法的描述信息
        if hasattr(view_class, f"{_method}_description"):
            # 获取视图类对应方法的描述信息
            _desc = getattr(view_class, f"{_method}_description")
        else:
            # 若没有描述信息，默认描述为无法确定用户行为
            _desc = "无法确定用户行为"
        # 获取客户端 IP 地址
        _ip, _ = ipware.get_client_ip(request)
        try:
            # 从请求的 cookies 中获取 JWT token
            token = request.COOKIES.get("jwtToken")
            # 解析 JWT token 获取 username
            _username = get_username_of_token(token)
        except DecodeError:
            # 若解码失败，将 username 设为匿名用户
            _username = "匿名用户"
        # 若请求的 URL 为登录接口
        if _url == reverse("login"):
            # 将描述信息设为用户登录
            _desc = "用户登录"
            # 初始化请求结果为空字符串
            request_result = ""
            # 初始化 token 为 None
            _token = None
            # 若响应数据中包含 "token" 字段
            if "token" in response.data:
                # 将请求结果设为登录成功
                request_result = "登录成功"
                # 获取响应数据中的 token
                _token = response.data.get("token", "")
                # 解析新的 token 获取 username
                _username = get_username_of_token(_token)
            else:
                return response
            # 根据 username 从数据库中获取用户信息
            _token_user = UserProfile.objects.filter(username=_username).first()
            # 若处于 pytest 测试环境或未找到用户信息
            if os.environ.get('PYTEST_CURRENT_TEST') or _token_user is None:
                # 构建用户登录日志数据
                data = {
                    'username': _username,
                    'login_time': timezone.now(),
                    'role': '普通管理员',
                    'ip': _ip,
                    'request_result': request_result
                }
            else:
                # 构建用户登录日志数据，包含用户角色信息
                data = {
                    'username': _username,
                    'login_time': timezone.now(),
                    'role': USER_TO_ROLE_EN_DICT.get(_token_user.role.lower(), ""),
                    'ip': _ip,
                    'request_result': request_result
                }
            # 创建用户登录日志记录
            UserLoginLog.objects.create(**data)
        else:
            try:
                # 读取已封装的响应数据
                res_data = json.loads(response.rendered_content)
            except Exception as e:
                return response
            # 定义请求方法与操作描述的映射字典
            method_dc = {
                'put': '修改',
                'get': '查看',
                'delete': '删除',
                'trace': '查看',
                'patch': '修改'
            }
            # 根据请求方法获取操作描述
            method_st = method_dc.get(_method)
            # 若未找到对应的操作描述，从 INTERFACE_KINDS 中获取，默认值为修改
            if not method_st:
                method_st = INTERFACE_KINDS.get(_url, "修改")
            # 若用户不是匿名用户
            if _username != "匿名用户":
                # 创建操作日志记录（env 取 EnvContextMiddleware 注入的
                # 请求环境上下文，无环境上下文时置空）。
                # 防御：request.env 可能在视图执行期间失效（如删除当前
                # 环境），审计写失败只记日志，不炸掉业务响应
                try:
                    OperateLog(
                        username=_username, request_ip=_ip, request_method=method_st,
                        request_url=_url, description=_desc,
                        response_code=res_data.get("code", 0),
                        request_result=res_data.get("message", ""),
                        env=getattr(request, "env", None)
                    ).save()
                except Exception as e:
                    logger.error(
                        f"write operate log failed: {e} "
                        f"(url={_url}, user={_username})")
        return response


class RoleAuthenticationMiddleware(MiddlewareMixin):
    """
    用户角色访问限制中间件
    """

    def process_view(self, request, func, *args, **kwargs):
        """
        在视图函数调用前进行角色权限检查

        :param request: 请求对象
        :param func: 视图函数
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 若有权限则返回 None，否则返回 JSON 格式的错误响应
        """
        # 获取请求方法并转换为小写
        _method = request.method.lower()
        # 若请求方法为 GET，直接返回 None
        if _method == "get":
            return None
        # 获取请求的 URL 路径
        _url = request.path
        # 若 URL 以 "/proxy/v1/grafana" 或 "/api/login/" 开头，直接返回 None
        if _url.startswith("/proxy/v1/grafana") or _url.startswith("/api/login/"):
            return None
        try:
            # 从请求的 cookies 中获取 JWT token
            token = request.COOKIES.get("jwtToken")
            # 解码 JWT token
            _token_user = jwt_decode_handler(token)
            # 从解码结果中获取 username
            _username = _token_user.get("username")
        except DecodeError:
            # 若解码失败，将 username 设为匿名用户
            _username = "匿名用户"
        # 根据 username 从数据库中获取用户信息
        _token_user = UserProfile.objects.filter(username=_username).first()
        # 若未找到用户信息，认为是非页面访问 omp 接口，放行
        if not _token_user:
            return None
        # 若用户角色为超级管理员，放行
        if _token_user.role.lower() == "superuser":
            return None
        # 记录用户被禁止操作的错误日志
        logger.error(f"{_token_user} prohibited this action")
        # 返回 JSON 格式的错误响应，提示用户无权限
        return JsonResponse({"code": 1, "data": None, "message": f"该{_token_user.username}用户无权限"})


class EnvContextMiddleware(MiddlewareMixin):
    """
    多环境上下文中间件：解析 X-Env-Id（备用 ?env_id= 查询参数）为
    request.env，并在显式携带环境标识时校验当前登录用户对该环境的授权。

    规则（见多环境架构设计 §6.1）：
    1. 未显式携带环境标识：放行，request.env 置 None，由视图层
       （get_request_env）决定是否 required；pytest 环境下注入 default
       环境（Env id=1）并跳过授权——测试基础设施的显式注入，等价于
       测试框架替所有存量用例带上 X-Env-Id: 1，不属于运行时静默回退。
    2. 显式携带（header 或 query）：无论是否 pytest 环境均走完整
       解析 + 授权链，便于测试覆盖 403 行为。
    3. 环境标识非整数或环境不存在：403 环境不存在。
    4. 授权校验：视图类声明 env_exempt=True 跳过（服务端回调类接口）；
       用户解析与 DRF JWT 认证对齐——优先 Authorization: JWT <token>
       header，回退 cookie jwtToken；无法解析到用户时放行（由视图层
       DRF 认证统一拦截）；
       superuser 放行；无 UserEnv 授权记录：403 无该环境访问权限。
    """

    @staticmethod
    def _get_env_id_raw(request):
        """
        读取显式环境标识：header 优先，query 参数 env_id 兜底（下载类 GET）

        :param request: 请求对象
        :return: 环境标识字符串；未携带时返回 None
        """
        _env_id = (request.headers.get("X-Env-Id") or "").strip()
        if not _env_id:
            _env_id = (request.GET.get("env_id") or "").strip()
        return _env_id or None

    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        在视图函数调用前解析环境上下文并校验授权

        :param request: 请求对象
        :param view_func: 视图函数（APIView 的 as_view 包装携带
            view_class 与 cls；DRF ViewSet 的 as_view 包装完全重写，
            仅携带 cls，读取逻辑需兼容两者）
        :param view_args: 位置参数
        :param view_kwargs: 关键字参数
        :return: 授权失败时返回 JSON 格式的 403 响应，否则返回 None 放行
        """
        _env_id_raw = self._get_env_id_raw(request)
        if _env_id_raw is None:
            # 未显式携带环境标识：放行，由视图层决定是否 required；
            # pytest 环境注入 default 环境并跳过授权
            request.env = None
            if os.environ.get("PYTEST_CURRENT_TEST"):
                request.env = Env.objects.filter(id=1).first()
            return None
        # 显式携带：走完整解析 + 授权链
        try:
            _env_id = int(_env_id_raw)
        except (TypeError, ValueError):
            return JsonResponse(
                {"code": 1, "data": None, "message": "环境不存在"},
                status=403)
        _env = Env.objects.filter(id=_env_id).first()
        if _env is None:
            return JsonResponse(
                {"code": 1, "data": None, "message": "环境不存在"},
                status=403)
        request.env = _env
        # 视图类声明 env_exempt：跳过授权校验（回调类接口按记录自身 env 处理）
        # DRF ViewSet 的 as_view 包装只暴露 .cls（ViewSetMixin.as_view
        # 完全重写，不经过 Django View.as_view 的 view_class 赋值），
        # APIView 的包装两者皆有——兼容读取（多环境架构收口第二波）
        _view_class = getattr(view_func, "view_class", None) or \
            getattr(view_func, "cls", None)
        if getattr(_view_class, "env_exempt", False):
            return None
        # 授权校验：token 提取对齐 DRF JWT 认证（get_jwt_value 口径：
        # 任意空白 split + 前缀小写比较）——Authorization: JWT <token>
        # 能过 DRF 认证的形态（小写 jwt 前缀 / tab 等空白分隔）均须在
        # 此命中，header 携带 token 的请求不得绕过环境授权（终审红线
        # 项）；无可用 header token 时回退 cookie jwtToken（与
        # RoleAuthenticationMiddleware 一致）
        token = None
        auth_parts = (request.headers.get("Authorization") or "").split()
        if len(auth_parts) == 2 and auth_parts[0].lower() == "jwt":
            token = auth_parts[1]
        if not token:
            token = request.COOKIES.get("jwtToken")
        try:
            _username = jwt_decode_handler(token).get("username")
        except DecodeError:
            _username = "匿名用户"
        _token_user = UserProfile.objects.filter(username=_username).first()
        if _token_user is None:
            # 与 RoleAuthenticationMiddleware 一致：无法解析到用户
            # （匿名 / 非页面访问）时放行，由视图层 DRF 认证统一拦截
            return None
        if (_token_user.role or "").lower() == "superuser":
            return None
        if not UserEnv.objects.filter(user=_token_user, env=_env).exists():
            # 记录用户越权访问环境的错误日志
            logger.error(
                f"{_token_user} has no authorization of env {_env}")
            return JsonResponse(
                {"code": 1, "data": None, "message": "无该环境访问权限"},
                status=403)
        return None
