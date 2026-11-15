# !/usr/bin/python3
# 指定使用 Python 3 解释器
# -*-coding:utf-8-*-
# 指定文件编码格式为 UTF-8

import json
import logging

# 从 Django REST framework 导入混合视图类，用于实现不同的视图功能
from rest_framework.mixins import ListModelMixin, CreateModelMixin, DestroyModelMixin, UpdateModelMixin
# 从 Django REST framework 导入通用视图集类
from rest_framework.viewsets import GenericViewSet
# 从 Django REST framework 导入响应类，用于返回 HTTP 响应
from rest_framework.response import Response
# 从 Django REST framework 导入验证错误异常类
from rest_framework.exceptions import ValidationError

# 从备份模块导入备份相关的序列化器类
from backups.backups_serializers import BackupHistorySerializer, \
    BackupHistoryIdsSerializer, BackupSettingSerializer, \
    BackupCustomSerializer, BackupCustomRepeatSerializer

# 从备份工具模块导入删除过期文件和检查实例是否正在备份的函数
from backups.backups_utils import rm_backend_file, \
    check_ing
# 从定时任务工具模块导入更改任务的函数
from utils.plugin.crontab_utils import change_task
# 从中间件模块导入获取请求环境上下文的函数
from utils.middleware_handler import get_request_env
# 从备份任务模块导入备份服务和拉取备份文件的异步任务
from backups.tasks import backup_service, pull_back_file
# 从数据库模型模块导入备份设置、备份历史、服务和备份自定义参数模型
from db_models.models import BackupSetting, BackupHistory, Service, \
    BackupCustom
# 从 django_celery_beat 模块导入周期任务模型，用于补写任务 kwargs
from django_celery_beat.models import PeriodicTask
# 从通用分页模块导入页码分页器类
from utils.common.paginations import PageNumberPager
# 从配置解析工具模块导入可备份的服务列表配置
from utils.parse_config import BACKUP_SERVICE

# 获取名为 "server" 的日志记录器
logger = logging.getLogger("server")


def sync_backup_crontab_env(task_id, env_id, data):
    """
    备份定时任务 kwargs 补 env_id（多环境架构 Task 12）。

    change_task 固定下发 kwargs={"task_id": ...}（共享工具，不在本模块
    改动范围），任务创建后由视图侧按策略归属环境补写 env_id；
    backup_service 任务按 task_id 读取 BackupSetting 自身 env 执行，
    不消费该值，仅作任务归属环境的记录。

    :param task_id: 备份设置 ID
    :param env_id: 备份设置归属环境 ID
    :param data: 创建任务时使用的请求数据（读取 task_name，与 change_task 一致）
    """
    task_name = data.get("task_name", f"backups_cron_task_{task_id}")
    PeriodicTask.objects.filter(name=task_name).update(
        kwargs=json.dumps({"task_id": task_id, "env_id": env_id}))


class CanBackupInstancesView(GenericViewSet, ListModelMixin):
    """
    获取可备份实例列表
    """
    get_description = "读取可备份实例列表"

    def list(self, request, *args, **kwargs):
        """
        处理 GET 请求，返回可备份实例列表。

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含可备份实例名称的响应对象
        """
        # ToDo 找不出更合适的继承
        # 过滤出当前环境上下文中应用名称在可备份服务列表中且状态正常
        # 的服务实例名称（多环境架构 Task 12）
        ser_data = Service.objects.filter(
            env=get_request_env(request),
            service__app_name__in=BACKUP_SERVICE
        ).filter(service_status=Service.SERVICE_STATUS_NORMAL).values_list("service_instance_name", flat=True)
        # 以下代码被注释，功能为排除已在备份设置中的实例
        # back_instance = BackupSetting.objects.all().values_list("backup_instances", flat=True)
        # back_set = []
        # for instance in back_instance:
        #    back_set.extend(instance)
        # ser_data = list(set(ser_data) - set(back_set))
        return Response(data=list(ser_data))


class BackupSettingView(GenericViewSet, ListModelMixin,
                        CreateModelMixin, UpdateModelMixin,
                        DestroyModelMixin):
    """
    操作备份策略
    """

    get_description = "读取备份策略"
    post_description = "更新备份策略"
    serializer_class = BackupSettingSerializer
    # 获取所有备份设置记录，并按 ID 倒序排序
    queryset = BackupSetting.objects.all().order_by("-id")

    def get_queryset(self):
        # 备份策略列表/更新/删除按当前环境上下文过滤；
        # POST 按 id 触发备份时在 create 内单独做环境校验
        # （多环境架构 Task 12）
        return BackupSetting.objects.filter(
            env=get_request_env(self.request)).order_by("-id")

    def create(self, request, *args, **kwargs):
        """
        更新备份策略
        """
        # 请求环境上下文：创建写入该环境，按 id 触发仅允许本环境策略
        env = get_request_env(request)
        # 从请求数据中获取设置 ID，若不存在则默认为 0
        set_id = request.data.pop("id", 0)
        # 从请求数据中获取备份自定义参数列表
        extend_field = request.data.pop("backup_custom", [])
        if set_id:
            # 任务策略制定后触发一次备份任务
            # 检查指定 ID 的备份设置实例是否存在正在备份的实例
            # （仅限本环境的策略，跨环境 id 视为不存在）
            if check_ing(BackupSetting.objects.filter(
                    id=set_id, env=env).first()):
                return Response(data={"code": 1, "message": f"当前策略存在正在备份的实例或id{set_id}不存在"})
            # 异步触发备份服务任务
            backup_service.delay(task_id=set_id)
            return Response("任务下发成功")
        # 使用备份设置序列化器验证请求数据
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # 保存验证后的数据，创建新的备份设置实例（写入当前环境，
        # 请求体伪造 env 字段不在序列化字段内，天然无效）
        obj = serializer.save(env=env)
        # 处理多对多关系
        for field in extend_field:
            # 根据自定义参数查找对应的备份自定义参数实例
            custom = BackupCustom.objects.filter(**field).first()
            # 将备份自定义参数实例添加到备份设置实例的关联关系中
            obj.backup_custom.add(custom)
        # 调用更改任务函数，获取任务执行结果
        code, msg = change_task(obj.id, request.data)
        # 定时任务 kwargs 补 env_id（记录任务归属环境）
        sync_backup_crontab_env(obj.id, env.id, request.data)
        return Response(msg)

    def update(self, request, *args, **kwargs):
        """
        更新备份策略信息。

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含更新结果信息的响应对象
        """
        # 获取要更新的备份设置实例
        instance = self.get_object()
        # 从请求数据中获取备份自定义参数列表
        extend_field = request.data.pop("backup_custom", [])
        # 提取备份自定义参数的 ID 列表
        extend_con = [field["id"] for field in extend_field]
        # 更新备份设置实例的备份自定义参数关联关系
        instance.backup_custom.set(extend_con)
        # 保存更新后的备份设置实例
        instance.save()
        # 调用父类的更新方法完成更新操作
        super(BackupSettingView, self).update(
            request, request, *args, **kwargs)
        # 调用更改任务函数，获取任务执行结果
        code, msg = change_task(instance.id, request.data)
        # 定时任务 kwargs 补 env_id（记录任务归属环境）
        sync_backup_crontab_env(instance.id, instance.env_id, request.data)
        return Response(msg)

    def destroy(self, request, *args, **kwargs):
        """
        删除备份策略。

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含删除结果信息的响应对象
        """
        # 获取要删除的备份设置实例
        instance = self.get_object()
        # 调用父类的删除方法完成删除操作
        super(BackupSettingView, self).destroy(
            request, request, *args, **kwargs)
        # 调用更改任务函数，获取任务执行结果
        code, msg = change_task(instance.id)
        return Response(msg)


class BackupHistoryView(GenericViewSet, ListModelMixin,
                        DestroyModelMixin, UpdateModelMixin
                        ):
    """
    备份记录相关视图
    """
    # 环境豁免宽度收窄（多环境架构 Task 7b）：不再声明类级 env_exempt
    # ——类级豁免会把 list/destroy/create 一并放出环境授权校验。回调
    # （被管节点 PUT/PATCH）天然不携带 X-Env-Id 与登录态，EnvContextMiddleware
    # 对未携带环境标识的请求本就放行，视图内 get_queryset 的回调分支
    # 按记录自身 env 处理；页面操作（list/destroy/create）照常走环境
    # 授权 + get_request_env 过滤。
    # 获取所有备份历史记录，并按创建时间倒序排序
    queryset = BackupHistory.objects.all().order_by("-create_time")
    pagination_class = PageNumberPager
    # 关闭权限、认证设置
    authentication_classes = ()
    permission_classes = ()

    delete_description = "删除备份记录文件"
    get_description = "获取备份历史记录"

    def get_queryset(self):
        """
        update / partial_update 为被管节点备份回调，无环境上下文，
        不做环境过滤，按记录 id（body 中的 remote_path 等）定位记录、
        按记录自身 env 处理；list / destroy 为页面操作，按当前环境过滤。
        """
        queryset = BackupHistory.objects.all().order_by("-create_time")
        if self.action in ("update", "partial_update"):
            return queryset
        return queryset.filter(env=get_request_env(self.request))

    def get_serializer_class(self):
        """
        根据请求方法返回相应的序列化器类。

        :return: 序列化器类
        """
        if self.request is not None and self.request.method == "POST":
            return BackupHistoryIdsSerializer
        return BackupHistorySerializer

    def create(self, request, *args, **kwargs):
        """
        删除备份记录文件。

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含删除结果信息的响应对象
        """
        # 使用备份历史记录 ID 序列化器验证请求数据
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # 获取验证后的数据中的备份历史记录对象列表
        instance = serializer.validated_data["id"]
        # 调用删除过期文件函数，获取删除失败的文件列表
        fail_files = rm_backend_file(instance)
        if fail_files:
            return Response(data={"code": 0, "message": f"删除{','.join(fail_files)}可能已不存在！"})
        return Response("删除记录成功")

    def update(self, request, *args, **kwargs):
        """
        更新备份历史记录信息，处理文件拉取逻辑。

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 调用父类更新方法的返回结果
        """
        # 转换code意义，考虑是否把含义变更
        # 根据请求数据中的 result 字段转换 code 的值
        code = 0 if request.data.pop("result") != "0" else 1
        # 从请求数据中获取远程文件路径
        remote_path = request.data.get("remote_path", "")
        # 从请求数据中获取是否需要拉取文件的标志
        need_push = request.data.get("need_push", False)
        # 文件备份
        # 根据远程文件路径设置文件是否已删除的标志
        request.data["file_deleted"] = False if remote_path else True
        # 成功 且 存在要拉取的文件
        if code and remote_path and need_push:
            if remote_path.startswith("/") and remote_path.endswith(".tar.gz"):
                # 获取要更新的备份历史记录实例
                instance = self.get_object()
                # 异步触发拉取备份文件任务
                pull_back_file.delay(
                    instance.id, remote_path, request.data["ip"])
            else:
                # 若文件路径不合法，抛出验证错误
                raise ValidationError(f"文件不合法{remote_path}")
            # 清空远程文件路径
            request.data["remote_path"] = ""
        else:
            # 清空保留路径
            request.data["retain_path"] = ""
            # 设置备份结果
            request.data["result"] = code
        # 调用父类的更新方法完成更新操作
        return super(BackupHistoryView, self).update(
            request, request, *args, **kwargs)


class BackupCustomView(GenericViewSet, ListModelMixin,
                       CreateModelMixin, UpdateModelMixin,
                       DestroyModelMixin):
    """
    备份自定义字典视图
    """
    serializer_class = BackupCustomSerializer
    # 获取所有备份自定义参数记录
    queryset = BackupCustom.objects.all()

    delete_description = "删除备份自定义字典"
    get_description = "获取备份自定义字典"
    put_description = "修改备份自定义字典"
    post_description = "创建备份自定义字典"

    def create(self, request, *args, **kwargs):
        """
        创建备份自定义字典。

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 包含创建结果信息的响应对象
        """
        # 使用备份自定义参数序列化器验证请求数据
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # 根据验证后的数据创建新的备份自定义参数实例
        BackupCustom.objects.create(**serializer.data)
        return Response("创建成功")


class BackupCustomRepeatView(GenericViewSet, ListModelMixin):
    """
        list:
        查询备份字典是否有多对多关联
    """

    serializer_class = BackupCustomRepeatSerializer

    get_description = "查询备份字典是否有多对多关联"

    def get_queryset(self):
        """
        根据请求查询参数中的 id 获取备份自定义参数实例。

        :return: 备份自定义参数查询集
        """
        # 从请求查询参数中获取 id
        bk_id = self.request.query_params.get('id')
        if bk_id:
            return BackupCustom.objects.filter(id=bk_id)
        else:
            # 若未提供 id，抛出验证错误
            raise ValidationError("需要填写id")
