import json
import logging
import traceback

from django.db import models, transaction
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import ListAPIView, GenericAPIView,\
    RetrieveUpdateAPIView
from rest_framework.response import Response

from db_models.mixins import UpgradeStateChoices, RollbackStateChoices
from db_models.models import UpgradeHistory, Service, ApplicationHub, \
    UpgradeDetail, RollbackHistory, RollbackDetail
from utils.common.exceptions import GeneralError
from utils.common.paginations import PageNumberPager
from utils.middleware_handler import get_request_env
from .filters import RollBackHistoryFilter
from .serializers import UpgradeHistorySerializer, ServiceSerializer, \
    UpgradeHistoryDetailSerializer,  ApplicationHubSerializer, \
    UpgradeTryAgainSerializer, RollbackHistorySerializer, \
    RollbackHistoryDetailSerializer, RollbackTryAgainSerializer, \
    RollbackListSerializer
from .tasks import upgrade_service, rollback_service

# 获取名为 "server" 的日志记录器
logger = logging.getLogger("server")


class UpgradeHistoryListAPIView(ListAPIView):
    """
    升级历史记录列表视图，用于展示所有升级历史记录。
    """
    # 升级历史记录注释：该视图返回升级历史记录列表
    pagination_class = PageNumberPager  # 使用页码分页器进行分页
    # 获取所有升级历史记录，并预先加载关联的升级详情
    queryset = UpgradeHistory.objects.all()\
        .prefetch_related("upgradedetail_set")
    filter_backends = (OrderingFilter, )  # 使用排序过滤器进行排序
    serializer_class = UpgradeHistorySerializer  # 使用升级历史记录序列化器
    ordering_fields = ("id", )  # 可排序的字段为 id
    ordering = ('-id',)  # 默认按 id 倒序排序
    get_description = "升级历史记录页"  # GET 请求的描述信息

    def get_queryset(self):
        """ 升级历史列表按当前环境上下文过滤（多环境架构 Task 13） """
        return super(UpgradeHistoryListAPIView, self).get_queryset()\
            .filter(env=get_request_env(self.request))


class UpgradeHistoryDetailAPIView(RetrieveUpdateAPIView):
    """
    升级历史记录详情视图，用于展示单个升级历史记录的详情，并支持升级重试操作。
    """
    # 升级历史记录详情注释：该视图返回升级历史记录详情
    # 获取所有升级历史记录，并预先加载关联的升级详情
    queryset = UpgradeHistory.objects.all()\
        .prefetch_related("upgradedetail_set")
    serializer_class = UpgradeHistoryDetailSerializer  # 使用升级历史记录详情序列化器
    lookup_url_kwarg = 'pk'  # 通过 URL 中的 pk 参数查找对应的记录
    get_description = "升级历史记录详情页"  # GET 请求的描述信息
    put_description = "升级重试"  # PUT 请求的描述信息

    def get_queryset(self):
        """ 详情 / 升级重试按当前环境上下文过滤，跨环境记录 404
        （多环境架构 Task 13） """
        return super(UpgradeHistoryDetailAPIView, self).get_queryset()\
            .filter(env=get_request_env(self.request))

    def update(self, request, *args, **kwargs):
        """
        处理 PUT 请求，实现升级重试功能。

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 响应对象
        """
        # put 升级重试
        instance = self.get_object()  # 获取当前请求对应的升级历史记录实例
        # 使用升级重试序列化器验证请求数据
        serializer = UpgradeTryAgainSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)  # 验证数据，若无效则抛出异常
        upgrade_service.delay(instance.id)  # 异步执行升级服务任务
        return Response()  # 返回响应


class UpgradeChoiceAllVersionListAPIView(GenericAPIView):
    """
    可升级服务列表（可选择升级的所有目标版本）视图，用于展示所有可升级服务及其可选择的升级目标版本。
    """
    # 可升级服务列表（可选择升级的目标）注释：该视图返回可升级服务列表
    # 获取所有服务状态在指定范围内的服务，并预先加载关联的服务信息
    queryset = Service.split_objects.filter(
        service_status__in=[0, 1, 2, 3, 4]
    ).select_related("service")
    filter_backends = (SearchFilter, )  # 使用搜索过滤器进行搜索
    search_fields = ("service__app_name",)  # 可搜索的字段为服务的应用名称
    get_description = "可升级服务列表"  # GET 请求的描述信息

    def get_queryset(self):
        """ 可升级服务列表按当前环境上下文过滤，跨环境服务不可选入
        （多环境架构收口第二波） """
        return super(UpgradeChoiceAllVersionListAPIView, self).get_queryset()\
            .filter(env=get_request_env(self.request))

    def get_service_info(self, services_data):
        """
        确定已安装服务最小版本，缩小查询范围及组装数据。

        :param services_data: 服务数据列表
        :return: 服务版本字典和服务最小应用 ID 字典
        """
        service_min_app_ids, services_versions = {}, {}
        for service_data in services_data:
            app_name = service_data.get("app_name")
            app_id = service_data.get("app_id")
            min_app_id = service_min_app_ids.get(app_name, None)
            if app_name not in services_versions:
                services_versions[app_name] = [service_data]
            else:
                services_versions[app_name].append(service_data)
            if min_app_id is None or app_id < min_app_id:
                service_min_app_ids[app_name] = app_id
        return services_versions, service_min_app_ids

    def get(self, requests):
        """
        处理 GET 请求，返回可升级服务列表及其可选择的升级目标版本。

        :param requests: 请求对象
        :return: 响应对象
        """
        queryset = self.filter_queryset(self.get_queryset())  # 过滤查询集
        # 使用服务序列化器序列化查询集
        services_data = ServiceSerializer(queryset, many=True).data
        if not services_data:
            return Response({"results": []})  # 若没有服务数据，返回空列表
        services_v, min_app_ids = self.get_service_info(
            services_data)  # 获取服务版本和最小应用 ID 信息
        # 查询服务可能存在可升级的安装包
        apps = ApplicationHub.objects.filter(
            id__gt=min(min_app_ids.values()),
            app_name__in=services_v.keys()
        ).order_by("-id").exclude(id__in=min_app_ids.values())
        if not apps:
            return Response({"results": []})  # 若没有可升级的安装包，返回空列表
        # 使用应用中心序列化器序列化可升级的安装包
        apps_data = ApplicationHubSerializer(apps, many=True).data
        for app_data in apps_data:
            app_id = app_data.get("app_id")
            app_name = app_data.pop("app_name")
            if min_app_ids.get(app_name, float("inf")) >= app_id:
                apps_data.remove(app_data)  # 移除不符合条件的安装包
                continue
            for service_v in services_v.get(app_name):
                if service_v.get("app_id", float("inf")) >= app_id:
                    continue
                if "can_upgrade" not in service_v:
                    service_v["can_upgrade"] = [app_data]
                else:
                    service_v["can_upgrade"].append(app_data)
        # 格式化数据，排除不可升级服务
        results = []
        # {"a": [{""}, {}]}
        for app_name, services in services_v.items():
            if not services:
                services_v.pop(app_name)
            upgrade_services = []
            for service in services:
                if service.get("can_upgrade"):
                    upgrade_services.append(service)
            if upgrade_services:
                results.append(
                    {"app_name": app_name, "children": upgrade_services}
                )
        # results: [{"app_name": a, "service": [{"can_upgrade": []...}]
        return Response({"results": results})  # 返回可升级服务列表


class UpgradeChoiceMaxVersionListAPIView(UpgradeChoiceAllVersionListAPIView):
    """
    可升级服务列表（只展示可供升级的最高版本）视图，继承自 UpgradeChoiceAllVersionListAPIView。
    """
    # 可升级服务列表（只展示可供升级的最高版本）注释：该视图返回可升级服务列表
    get_description = "可升级服务列表"  # GET 请求的描述信息

    def get_service_max_app(self, apps):
        """
        确定每个应用的最高版本。

        :param apps: 应用数据列表
        :return: 应用名称到最高版本应用数据的字典
        """
        max_apps = {}
        for app in apps:
            app_info = max_apps.get(app["app_name"], {})
            if app_info.get("app_id", float("-inf")) <= app["app_id"]:
                max_apps[app["app_name"]] = app
        return max_apps

    def get(self, requests):
        """
        处理 GET 请求，返回可升级服务列表及其可供升级的最高版本。

        :param requests: 请求对象
        :return: 响应对象
        """
        queryset = self.filter_queryset(self.get_queryset())  # 过滤查询集
        # 使用服务序列化器序列化查询集
        services_data = ServiceSerializer(queryset, many=True).data
        if not services_data:
            return Response({"results": []})  # 若没有服务数据，返回空列表
        services_v, min_app_ids = self.get_service_info(
            services_data)  # 获取服务版本和最小应用 ID 信息
        # 查询服务可能存在可升级的安装包
        apps = ApplicationHub.objects.filter(
            id__gt=min(min_app_ids.values()),
            app_name__in=services_v.keys()
        ).order_by("-id").exclude(id__in=min_app_ids.values())
        if not apps:
            return Response({"results": []})  # 若没有可升级的安装包，返回空列表
        # 使用应用中心序列化器序列化可升级的安装包
        apps_data = ApplicationHubSerializer(apps, many=True).data
        max_apps_dict = self.get_service_max_app(apps_data)  # 获取每个应用的最高版本
        results = []
        for app_name, max_app in max_apps_dict.items():
            services = services_v.get(app_name)
            upgrade_services = []
            for service_v in services:
                if service_v.get("app_id", float("inf")) >= max_app["app_id"]:
                    continue
                service_v["can_upgrade"] = [max_app]
                upgrade_services.append(service_v)
            if upgrade_services:
                results.append(
                    {
                        "app_name": app_name,
                        "children": upgrade_services,
                        "can_upgrade": max_app
                    }
                )
        return Response({"results": results})  # 返回可升级服务列表


class DoUpgradeAPIView(GenericAPIView):
    """
    执行升级操作视图，用于处理服务升级请求。
    """
    post_description = "升级服务"  # POST 请求的描述信息

    def valid_can_upgrade(self, data):
        """
        校验服务是否可以升级。

        :param data: 包含服务 ID 和应用 ID 的字典
        :return: 经过校验的服务列表
        """
        # 校验信息
        # 获取符合条件的服务，并添加额外的字段信息
        services = list(
            Service.split_objects.filter(
                id__in=data.keys(),
                service_status__in=[0, 1, 2, 3, 4]
            ).annotate(
                app_name=models.F("service__app_name"),
                current_app_id=models.F("service_id")
            ).values(
                "id", "app_name", "ip", "current_app_id", "service_dependence"
            )
        )
        if not services:
            raise GeneralError("请选择需要升级的服务！")  # 若没有服务，抛出异常
        # 获取符合条件的应用信息
        apps = ApplicationHub.objects.filter(
            id__in=data.values(),
            is_release=True
        ).values("id", "app_name", "app_version", "app_dependence")
        app_dict = {}
        for app in apps:
            # todo: app_dependence字段有问题，后续需修改
            app_dict[app.get("app_name")] = {
                "target_app_id": app.get("id"),
                "app_dependence": json.loads(
                    app.get("app_dependence") or '[]'
                )
            }
        for service in services:
            app_name = service.get("app_name")
            app_info = app_dict.get(app_name, {})
            if app_info.get("target_app_id", float("-inf")) \
                    <= service["current_app_id"]:
                # 若升级版本小于或等于当前版本，抛出异常
                raise GeneralError(f"服务{app_name}升级版本小于或等于当前版本！")
            try:
                # 更新服务依赖信息
                Service.update_dependence(
                    service.get("service_dependence"),
                    app_info.get("app_dependence", [])
                )
            except Exception as e:
                # 若依赖校验失败，抛出异常
                raise GeneralError(
                    f"服务{service.get('app_name')}依赖校验失败：{str(e)}")
            service.update(app_dict.get(app_name))  # 更新服务信息
        return services

    def post(self, requests):
        """
        处理 POST 请求，执行服务升级操作。

        :param requests: 请求对象
        :return: 响应对象
        """
        if UpgradeHistory.objects.filter(
            upgrade_state__in=[
                UpgradeStateChoices.UPGRADE_WAIT,
                UpgradeStateChoices.UPGRADE_ING,
            ]
        ).exists():
            # 若存在正在升级的服务，抛出异常
            raise GeneralError("存在正在升级的服务，请稍后！")
        if RollbackHistory.objects.filter(
            rollback_state__in=[
                RollbackStateChoices.ROLLBACK_WAIT,
                RollbackStateChoices.ROLLBACK_ING,
            ]
        ).exists():
            # 若存在正在回滚的服务，抛出异常
            raise GeneralError("存在正在回滚的服务，请稍后！")
        fail_query = UpgradeDetail.objects.filter(
                upgrade_state=UpgradeStateChoices.UPGRADE_FAIL,
                service__isnull=False
        ).exclude(has_rollback=True)
        if fail_query.exists():
            fail_services = list(
                fail_query.values_list("union_server", flat=True)
            )
            # 若存在升级失败的服务，抛出异常
            raise GeneralError(
                f"存在升级失败的服务，请继续升级或回滚！失败服务：{fail_services}")
        choices = requests.data.get("choices", [])
        if not choices:
            raise GeneralError("请选择需要升级的服务！")  # 若没有选择服务，抛出异常
        try:
            data = {}
            for choice in choices:
                if choice.get("service_id") in data:
                    # 若服务 ID 重复，抛出异常
                    raise KeyError(f'{choice.get("service_id")}重复！')
                data[choice.get("service_id")] = choice.get("app_id")
        except Exception as e:
            # 若解析升级数据出错，记录日志并抛出异常
            logger.error(
                f"解析升级数据错误：{str(e)}, 详情为：\n{traceback.format_exc()}")
            raise GeneralError("解析升级数据错误！")
        # 升级对象来自服务列表：校验所选服务均属于当前环境
        # （与 valid_can_upgrade 一致使用 split_objects 视角）
        env = get_request_env(requests)
        service_ids = set(data.keys())
        env_service_count = Service.split_objects.filter(
            id__in=service_ids, env=env).count()
        if env_service_count != len(service_ids):
            raise GeneralError("所选服务包含非当前环境的服务，请刷新后重试！")
        services = self.valid_can_upgrade(data)  # 校验服务是否可以升级
        with transaction.atomic():  # 开启事务
            # 创建升级历史记录
            history = UpgradeHistory.objects.create(
                env=env,
                operator=requests.user
            )
            details = []
            for service in services:
                service_id = service.pop("id")
                app_name = service.pop("app_name")
                ip = service.pop("ip")
                service.pop("app_dependence")
                service.pop("service_dependence")
                # 创建升级详情对象
                details.append(
                    UpgradeDetail(
                        history=history,
                        service_id=service_id,
                        union_server=f"{ip}-{app_name}",
                        **service,
                    )
                )
            # 批量创建升级详情记录
            UpgradeDetail.objects.bulk_create(details)
        upgrade_service.delay(history.id)  # 异步执行升级服务任务
        return Response({"history": history.id})  # 返回升级历史记录 ID


class RollbackHistoryListAPIView(ListAPIView):
    """
    回滚历史记录列表视图，用于展示所有回滚历史记录。
    """
    pagination_class = PageNumberPager  # 使用页码分页器进行分页
    # 获取所有回滚历史记录，并预先加载关联的回滚详情
    queryset = RollbackHistory.objects.all()\
        .prefetch_related("rollbackdetail_set")
    filter_backends = (OrderingFilter, )  # 使用排序过滤器进行排序
    serializer_class = RollbackHistorySerializer  # 使用回滚历史记录序列化器
    ordering_fields = ("id", )  # 可排序的字段为 id
    ordering = ('-id',)  # 默认按 id 倒序排序
    get_description = "回滚历史记录页"  # GET 请求的描述信息

    def get_queryset(self):
        """ 回滚历史列表按当前环境上下文过滤（多环境架构 Task 13） """
        return super(RollbackHistoryListAPIView, self).get_queryset()\
            .filter(env=get_request_env(self.request))


class RollbackHistoryDetailAPIView(RetrieveUpdateAPIView):
    """
    回滚历史记录详情视图，用于展示单个回滚历史记录的详情，并支持回滚重试操作。
    """
    # 获取所有回滚历史记录，并预先加载关联的回滚详情
    queryset = RollbackHistory.objects.all()\
        .prefetch_related("rollbackdetail_set")
    serializer_class = RollbackHistoryDetailSerializer  # 使用回滚历史记录详情序列化器
    lookup_url_kwarg = 'pk'  # 通过 URL 中的 pk 参数查找对应的记录
    get_description = "回滚历史记录详情页"  # GET 请求的描述信息
    put_description = "回滚重试"  # PUT 请求的描述信息

    def get_queryset(self):
        """ 详情 / 回滚重试按当前环境上下文过滤，跨环境记录 404
        （多环境架构 Task 13） """
        return super(RollbackHistoryDetailAPIView, self).get_queryset()\
            .filter(env=get_request_env(self.request))

    def update(self, request, *args, **kwargs):
        """
        处理 PUT 请求，实现回滚重试功能。

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 响应对象
        """
        instance = self.get_object()  # 获取当前请求对应的回滚历史记录实例
        # 使用回滚重试序列化器验证请求数据
        serializer = RollbackTryAgainSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)  # 验证数据，若无效则抛出异常
        rollback_service.delay(instance.id)  # 异步执行回滚服务任务
        return Response()  # 返回响应


class RollbackChoiceListAPIView(GenericAPIView):
    """
    可回滚服务列表视图，用于展示所有可回滚的服务。
    """
    # 获取符合条件的升级详情记录
    queryset = UpgradeDetail.objects.filter(
        upgrade_state__in=[
            UpgradeStateChoices.UPGRADE_SUCCESS,
            UpgradeStateChoices.UPGRADE_FAIL
        ]
    ).exclude(has_rollback=True).exclude(service__isnull=True)
    filter_backends = (SearchFilter, RollBackHistoryFilter)  # 使用搜索过滤器和回滚历史过滤器
    search_fields = ("target_app__app_name", )  # 可搜索的字段为目标应用的名称
    get_description = "可回滚服务列表页"  # GET 请求的描述信息

    def get_queryset(self):
        """ 可回滚明细经所属升级记录按当前环境过滤，跨环境明细不可选入
        （多环境架构收口第二波） """
        return super(RollbackChoiceListAPIView, self).get_queryset()\
            .filter(history__env=get_request_env(self.request))

    def get(self, requests):
        """
        处理 GET 请求，返回可回滚服务列表。

        :param requests: 请求对象
        :return: 响应对象
        """
        queryset = self.filter_queryset(self.get_queryset())  # 过滤查询集
        # 使用回滚列表序列化器序列化查询集
        upgrades_data = RollbackListSerializer(queryset, many=True).data
        service_id_max_d, service_name_max_d = {}, {}
        for upgrade_data in upgrades_data:
            service_id = upgrade_data.get("service_id")
            detail_id = upgrade_data.get("id")
            app_name = upgrade_data.get("app_name")
            service_max_data = service_id_max_d.get(service_id, {})
            if service_max_data.get("id", float("-inf")) > detail_id:
                continue
            service_id_max_d[service_id] = upgrade_data
            if app_name not in service_name_max_d:
                service_name_max_d[app_name] = {service_id: upgrade_data}
            else:
                service_name_max_d[app_name].update({service_id: upgrade_data})
        response_data = [
            {"app_name": app_name, "children": list(max_info.values())}
            for app_name, max_info in service_name_max_d.items()
        ]
        return Response(data={"results": response_data})  # 返回可回滚服务列表


class DoRollbackAPIView(GenericAPIView):
    """
    执行回滚操作视图，用于处理服务回滚请求。
    """
    get_description = "回滚服务"  # GET 请求的描述信息

    def post(self, requests):
        """
        处理 POST 请求，执行服务回滚操作。

        :param requests: 请求对象
        :return: 响应对象
        """
        if UpgradeHistory.objects.filter(
            upgrade_state__in=[
                UpgradeStateChoices.UPGRADE_WAIT,
                UpgradeStateChoices.UPGRADE_ING,
            ]
        ).exists():
            # 若存在正在升级的服务，抛出异常
            raise GeneralError("存在正在升级的服务，请稍后！")
        if RollbackHistory.objects.filter(
            rollback_state__in=[
                RollbackStateChoices.ROLLBACK_WAIT,
                RollbackStateChoices.ROLLBACK_ING,
            ]
        ).exists():
            # 若存在正在回滚的服务，抛出异常
            raise GeneralError("存在正在回滚的服务，请稍后！")
        choices = requests.data.get("choices", [])
        if not choices:
            raise GeneralError("请选择需要回滚的记录！")  # 若没有选择记录，抛出异常
        # 获取符合条件的升级详情记录（按 id 操作：升级明细经所属升级
        # 记录校验当前环境，跨环境明细计入数量不一致 -> 400）
        env = get_request_env(requests)
        upgrade_details = UpgradeDetail.objects.filter(
            id__in=choices,
            upgrade_state__in=[
                UpgradeStateChoices.UPGRADE_SUCCESS,
                UpgradeStateChoices.UPGRADE_FAIL
            ],
            history__env=env
        ).values("id", "current_app_id", "union_server")
        if upgrade_details.count() != len(choices):
            # 若提交信息校验失败，抛出异常
            raise GeneralError("提交信息校验失败，请刷新重试！")
        # 校验同一个服务是否回滚至同一版本
        union_app = {}
        for detail in upgrade_details:
            rollback_app_id = detail.get("current_app_id")
            union_server = detail.get("union_server")
            if not union_server:
                # 若实例不在平台纳管范围，抛出异常
                raise GeneralError(f"实例{union_server}不在平台纳管范围！")
            if not union_app.get(union_server):
                union_app[union_server] = rollback_app_id
                continue
            if union_app.get(union_server) != rollback_app_id:
                # 若实例将回滚的服务版本不一致，抛出异常
                raise GeneralError(f"实例{union_server}将回滚的服务版本不一致！")
        with transaction.atomic():  # 开启事务
            # 创建回滚历史记录
            history = RollbackHistory.objects.create(
                env=env,
                operator=requests.user
            )
            # 批量创建回滚详情记录
            RollbackDetail.objects.bulk_create(
                [
                    RollbackDetail(
                        history=history,
                        upgrade_id=upgrade_detail.get("id")
                    )
                    for upgrade_detail in upgrade_details
                ]
            )
        rollback_service.delay(history.id)  # 异步执行回滚服务任务
        return Response({"history": history.id})  # 返回回滚历史记录 ID