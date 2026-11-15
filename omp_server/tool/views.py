# Create your views here.
# 从 django.shortcuts 模块导入 get_object_or_404 函数，用于获取对象，若对象不存在则返回 404 错误
from django.shortcuts import get_object_or_404
# 从 django_filters 的 rest_framework 后端模块导入 DjangoFilterBackend 类，用于实现过滤功能
from django_filters.rest_framework.backends import DjangoFilterBackend
# 从 rest_framework 的 filters 模块导入 SearchFilter 和 OrderingFilter 类，分别用于搜索和排序功能
from rest_framework.filters import SearchFilter, OrderingFilter
# 从 rest_framework 的 generics 模块导入 ListAPIView 和 CreateAPIView 类，分别用于列表视图和创建视图
from rest_framework.generics import ListAPIView, CreateAPIView
# 从 rest_framework 的 viewsets 模块导入 GenericViewSet 类，用于创建通用视图集
from rest_framework.viewsets import GenericViewSet
# 从 rest_framework 的 mixins 模块导入 RetrieveModelMixin 和 ListModelMixin 类，分别用于获取单个对象和列表数据
from rest_framework.mixins import RetrieveModelMixin, ListModelMixin
# 从 db_models 应用的 models 模块导入多个模型类
from db_models.models import (ToolExecuteMainHistory, ToolInfo, Host, Service)
# 从 tool 应用的 tool_filters 模块导入自定义的过滤器类
from tool.tool_filters import ToolFilter, ToolInfoKindFilter
# 从 tool 应用的 serializers 模块导入多个序列化器类
from tool.serializers import ToolListSerializer, ToolInfoDetailSerializer, \
    ToolTargetObjectServiceSerializer, ToolFormAnswerSerializer, \
    ToolExecuteHistoryListSerializer
# 从 utils.common.paginations 模块导入自定义的分页类
from utils.common.paginations import PageNumberPager
# 从中间件模块导入环境上下文获取函数（多环境架构 Task 13）
from utils.middleware_handler import get_request_env
# 从 tool 应用的 serializers 模块再次导入部分序列化器类
from tool.serializers import ToolDetailSerializer, ToolFormDetailSerializer, \
    ToolTargetObjectHostSerializer


class ToolRetrieveAPIMixin:
    """
    用于获取工具对象的混合类，提供加载工具对象的方法。
    """
    def load_tool_obj(self):
        """
        根据 URL 中的参数获取对应的工具对象，并更新 kwargs 字典。

        :return: 获取到的工具对象
        """
        # 获取 URL 中的查找关键字参数，若未指定则使用 lookup_field
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        # 使用 get_object_or_404 函数获取工具对象，若不存在则返回 404 错误
        tool = get_object_or_404(
            ToolInfo.objects.all(),
            **{self.lookup_field: self.kwargs[lookup_url_kwarg]}
        )
        # 更新 kwargs 字典，将工具对象添加进去
        self.kwargs.update(tool=tool)
        return tool


class GetToolDetailView(GenericViewSet, RetrieveModelMixin):
    """
    任务详情页视图集，用于获取任务的详细信息。
    """
    # 定义查询集，获取所有的工具执行主历史记录
    queryset = ToolExecuteMainHistory.objects.all()
    # 操作描述信息，用于说明该视图的功能
    get_description = "任务详情页"
    # 指定序列化器类，用于将工具执行主历史记录对象序列化为 JSON 数据
    serializer_class = ToolDetailSerializer

    def get_queryset(self):
        """ 执行结果按 id 查看走当前环境过滤，跨环境记录 404
        （多环境架构 Task 13） """
        return super(GetToolDetailView, self).get_queryset()\
            .filter(env=get_request_env(self.request))


class ToolFormDetailAPIView(GenericViewSet, RetrieveModelMixin):
    """
    小工具执行表单页视图集，用于获取小工具执行表单的详细信息。
    """
    # 定义查询集，获取所有的工具信息
    queryset = ToolInfo.objects.all()
    # 操作描述信息，用于说明该视图的功能
    get_description = "小工具执行表单页"
    # 指定序列化器类，用于将工具信息对象序列化为 JSON 数据
    serializer_class = ToolFormDetailSerializer


class ToolListView(GenericViewSet, ListModelMixin):
    """
    查询所有实用工具列表视图集，用于获取所有实用工具的列表信息。
    """
    # 定义查询集，获取所有的工具信息并按创建时间倒序排序
    queryset = ToolInfo.objects.all().order_by("-created")
    # 指定序列化器类，用于将工具信息对象序列化为 JSON 数据
    serializer_class = ToolListSerializer
    # 指定分页类，用于对查询结果进行分页
    pagination_class = PageNumberPager
    # 定义过滤后端，使用 DjangoFilterBackend 进行过滤
    filter_backends = (DjangoFilterBackend,)
    # 指定过滤器类，用于对工具信息进行过滤
    filter_class = ToolFilter
    # 操作信息描述，用于说明该视图的功能
    get_description = "查询所有实用工具列表"


class ToolDetailView(GenericViewSet, RetrieveModelMixin):
    """
    获取实用工具详情视图集，用于获取单个实用工具的详细信息。
    """
    # 定义查询集，获取所有的工具信息并按创建时间倒序排序
    queryset = ToolInfo.objects.all().order_by("-created")
    # 指定序列化器类，用于将工具信息对象序列化为 JSON 数据
    serializer_class = ToolInfoDetailSerializer
    # 操作描述信息，用于说明该视图的功能
    get_description = "获取实用工具详情"


class ToolTargetObjectAPIView(ListAPIView, ToolRetrieveAPIMixin):
    """
    小工具执行对象展示页视图，用于展示小工具执行对象的列表信息。
    """
    # 操作描述信息，用于说明该视图的功能
    get_description = "小工具执行对象展示页"
    # 指定分页类，用于对查询结果进行分页
    pagination_class = PageNumberPager

    def get(self, request, *args, **kwargs):
        """
        处理 GET 请求，加载工具对象后调用列表视图方法。

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 列表视图的响应结果
        """
        # 调用混合类的方法加载工具对象
        self.load_tool_obj()
        return self.list(request, *args, **kwargs)

    def get_queryset(self):
        """
        根据工具对象的目标名称获取对应的查询集。

        :return: 主机对象查询集或服务对象查询集
        """
        if self.kwargs["tool"].target_name == "host":
            # 若工具目标名称为 "host"，返回当前环境的主机对象
            # （跨环境主机不可作为执行对象，多环境架构收口第二波）
            return Host.objects.filter(env=get_request_env(self.request))
        # 否则，返回指定应用名称的当前环境服务对象
        # （跨环境服务不可作为执行对象，多环境架构收口第二波）
        return Service.objects.filter(
            service__app_name=self.kwargs["tool"].target_name,
            env=get_request_env(self.request)
        )

    def get_serializer_class(self):
        """
        根据工具对象的目标名称获取对应的序列化器类。

        :return: 主机对象序列化器类或服务对象序列化器类
        """
        if self.kwargs["tool"].target_name == "host":
            # 若工具目标名称为 "host"，返回主机对象序列化器类
            return ToolTargetObjectHostSerializer
        # 否则，返回服务对象序列化器类
        return ToolTargetObjectServiceSerializer


class ToolFormAnswerAPIView(CreateAPIView, ToolRetrieveAPIMixin):
    """
    小工具执行表单页视图，用于创建小工具执行表单的答案信息。
    """
    # 操作描述信息，用于说明该视图的功能
    get_description = "小工具执行表单页"
    # 指定序列化器类，用于将表单答案数据反序列化为对象
    serializer_class = ToolFormAnswerSerializer

    def post(self, request, *args, **kwargs):
        """
        处理 POST 请求，加载工具对象后调用创建视图方法。

        :param request: 请求对象
        :param args: 可变位置参数
        :param kwargs: 可变关键字参数
        :return: 创建视图的响应结果
        """
        # 调用混合类的方法加载工具对象
        self.load_tool_obj()
        return self.create(request, *args, **kwargs)


class ToolExecuteHistoryListApiView(ListAPIView):
    """
    小工具执行列表页视图，用于获取小工具执行历史的列表信息。
    """
    # 操作描述信息，用于说明该视图的功能
    get_description = "小工具执行列表页"
    # 指定分页类，用于对查询结果进行分页
    pagination_class = PageNumberPager
    # 指定序列化器类，用于将工具执行主历史记录对象序列化为 JSON 数据
    serializer_class = ToolExecuteHistoryListSerializer
    # 定义查询集，获取所有的工具执行主历史记录并关联查询工具信息
    queryset = ToolExecuteMainHistory.objects.all().select_related("tool")
    # 定义过滤后端，使用 SearchFilter、OrderingFilter 和 ToolInfoKindFilter 进行搜索、排序和分类过滤
    filter_backends = (SearchFilter, OrderingFilter, ToolInfoKindFilter)
    # 指定搜索字段，可根据任务名称进行搜索
    search_fields = ("task_name", )
    # 指定排序字段，可根据开始时间进行排序
    ordering_fields = ("start_time",)
    # 默认排序规则，按开始时间倒序排序
    ordering = ('-start_time',)

    def get_queryset(self):
        """ 执行历史列表按当前环境上下文过滤（多环境架构 Task 13） """
        return super(ToolExecuteHistoryListApiView, self).get_queryset()\
            .filter(env=get_request_env(self.request))
