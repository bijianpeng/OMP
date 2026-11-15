# 导入 datetime 模块，用于处理日期和时间相关操作
import datetime
# 导入 logging 模块，用于记录程序运行过程中的日志信息
import logging

# 从 Django 的数据库模型模块导入 F 对象，用于数据库字段的更新操作
from django.db.models import F
# 从 Django REST framework 导入序列化器相关模块
from rest_framework import serializers
# 从 Django REST framework 导入验证错误类，用于处理验证过程中的异常
from rest_framework.exceptions import ValidationError
# 从 Django REST framework 的序列化器模块导入常用的序列化器类
from rest_framework.serializers import ModelSerializer, ListSerializer, \
    Serializer

# 从数据库模型模块导入所需的模型类
from db_models.models import Host, MonitorUrl, Alert, Maintain, Service, Rule, AlertRule, WaitSelfHealing, Env
# 从告警工具模块导入 AlertAnalysis 类，用于分析告警信息
from promemonitor.alert_util import AlertAnalysis
# 从告警管理模块导入 Alertmanager 类，用于管理告警屏蔽规则
from promemonitor.alertmanager import Alertmanager
# 从任务模块导入 monitor_agent_restart 任务，用于重启监控 Agent
from promemonitor.tasks import monitor_agent_restart
# 从通用异常模块导入 OperateError 类，用于处理操作异常
from utils.common.exceptions import OperateError
# 从通用序列化器模块导入 HostIdsSerializer 类，用于处理主机 ID 列表的序列化
from utils.common.serializers import HostIdsSerializer
from utils.middleware_handler import get_request_env
# 从通用验证器模块导入自定义验证器类
from utils.common.validators import (
    NoEmojiValidator, NoChineseValidator
)

# 获取名为 'server' 的日志记录器
logger = logging.getLogger('server')


class MonitorUrlListSerializer(ListSerializer):
    """
    监控 URL 列表序列化器，用于处理批量操作的监控 URL 数据。
    支持批量创建、更新和验证操作。
    """

    def update(self, instance, validated_data):
        """
        更新监控 URL 实例，当前方法为空，暂不实现更新逻辑。

        :param instance: 要更新的监控 URL 实例
        :param validated_data: 验证后的数据
        """
        pass

    def to_internal_value(self, data):
        """
        将输入数据转换为内部可用的格式，从输入数据中提取 'data' 字段。

        :param data: 输入的数据
        :return: 提取的 'data' 字段数据
        """
        return data.get('data')

    def validate(self, data):
        """
        验证输入的监控 URL 数据，确保数据的完整性和合法性。

        :param data: 输入的监控 URL 数据列表
        :return: 验证通过的数据
        :raises serializers.ValidationError: 当数据不满足验证条件时抛出异常
        """
        # 获取所有的监控 URL 实例
        queryset = MonitorUrl.objects.all()
        # 获取请求方法
        method = self.context["request"].method
        for i in data:
            if method in ('PATCH', 'PUT', 'DELETE'):
                if not i.get("id"):
                    # 对于 PATCH、PUT、DELETE 请求，id 字段是必须的
                    raise serializers.ValidationError("id是必须字段")
            # 获取监控 URL
            monitor_url = i.get("monitor_url")
            if method != 'GET':
                if not monitor_url:
                    # 除 GET 请求外，monitor_url 字段是必须的
                    raise serializers.ValidationError("monitor_url是必须字段")
                if len(monitor_url) > 128:
                    # monitor_url 字段长度不能超过 128
                    raise serializers.ValidationError(
                        f"monitor_url字段超过128,detail:{monitor_url}")
                # 获取监控名称
                name = i.get("name")
                if name:
                    if queryset.filter(name=name).exists():
                        # 监控名称不能重复
                        raise serializers.ValidationError(
                            f"name字段已经存在,detail:{name}")
                    if len(name) > 32:
                        # 监控名称长度不能超过 32
                        raise serializers.ValidationError(
                            f"name字段长度超过32,detail:{name}")
                else:
                    # 监控名称不能为空
                    raise serializers.ValidationError("name字段不为空")
        return data

    def create(self, validated_data):
        """
        批量创建监控 URL 实例。

        :param validated_data: 验证后的数据
        :return: 批量创建的监控 URL 实例列表
        """
        # 构建监控 URL 实例列表
        monitor = [MonitorUrl(**item) for item in validated_data]
        # 批量创建监控 URL 实例
        return MonitorUrl.objects.bulk_create(monitor)


class MonitorUrlSerializer(ModelSerializer):
    """
    监控配置项序列化器，用于序列化和反序列化监控配置项数据。
    提供对监控名称、ID 和监控 URL 的验证和序列化。
    """
    # 监控名称字段，最大长度为 32，必填
    name = serializers.CharField(
        max_length=32, required=True,
        error_messages={"invalid": "监控名字重复"},
        help_text="监控名字")
    # 监控 ID 字段，最大值为 100，非必填
    id = serializers.IntegerField(
        max_value=100, required=False,
        error_messages={"invalid": "id格式不正确"},
        help_text="id")

    # 监控 URL 字段，必填，使用自定义验证器验证
    monitor_url = serializers.CharField(
        required=True,
        error_messages={"invalid": "监控地址格式不正确"},
        validators=[
            NoEmojiValidator(message="url地址存在非法字符"),
            NoChineseValidator(message="url地址存在非法字符"),
        ],
        help_text="监控地址")

    class Meta:
        """
        元数据类，指定序列化器对应的模型和字段。
        """
        model = MonitorUrl
        fields = "__all__"
        list_serializer_class = MonitorUrlListSerializer

    def validate_name(self, name):
        """
        校验监控名称是否重复。

        :param name: 监控名称
        :return: 验证通过的监控名称
        :raises ValidationError: 当监控名称重复时抛出异常
        """
        # 获取所有的监控 URL 实例
        queryset = MonitorUrl.objects.all()
        if self.instance is not None:
            # 排除当前实例
            queryset = queryset.exclude(id=self.instance.id)
        if queryset.filter(name=name).exists():
            # 监控名称重复
            raise ValidationError("name已经存在")
        return name

    def validate_monitor_url(self, monitor_url):
        """
        校验监控 URL 是否包含非法字符。

        :param monitor_url: 监控 URL
        :return: 验证通过的监控 URL
        :raises ValidationError: 当监控 URL 包含非法字符时抛出异常
        """
        if len(monitor_url.split(" ")) > 1:
            # 监控 URL 包含非法字符
            raise ValidationError("url地址存在非法字符")
        return monitor_url


class ListAlertSerializer(ModelSerializer):
    """
    告警列表序列化器，用于序列化告警记录数据。
    """
    class Meta:
        """
        元数据类，指定序列化器对应的模型和字段。
        """
        model = Alert
        fields = "__all__"


class UpdateAlertSerializer(Serializer):
    """
    告警记录序列化器，用于更新告警记录的已读状态。
    """

    # 告警记录 ID 列表字段，必填
    ids = serializers.ListField(
        help_text="告警记录ID列表",
        required=True,
        error_messages={"required": "必须包含ID列表字段"}
    )

    # 是否已读字段，必填
    is_read = serializers.IntegerField(
        help_text="是否已读",
        required=True,
        error_messages={"required": "必须包含是否已读字段"}
    )

    # def validate(self, attrs):
    #     # TODO 做校验
    #     return attrs

    def create(self, validated_data):
        """
        更新告警记录的已读状态。

        :param validated_data: 验证后的数据
        :return: 验证后的数据
        """
        # 根据 ID 列表更新告警记录的已读状态（仅当前环境的记录，
        # 跨环境 id 不产生效果——多环境架构 Task 7b）
        Alert.objects.filter(
            id__in=validated_data.get('ids'),
            env=get_request_env(self.context.get("request"))).update(
            is_read=validated_data.get('is_read'))
        return validated_data

    def update(self, instance, validated_data):
        """
        更新告警记录实例，当前方法为空，暂不实现更新逻辑。

        :param instance: 要更新的告警记录实例
        :param validated_data: 验证后的数据
        """
        pass


class MaintainSerializer(ModelSerializer):
    """
    维护模式序列化器，用于进入或退出维护模式。
    提供对维护唯一标识、匹配标签和匹配标签值的验证和序列化。
    """
    # 维护唯一标识字段，非必填，最大长度为 1024
    maintain_id = serializers.CharField(
        help_text="维护唯一标识",
        required=False, max_length=1024,
        error_messages={"required": "maintain_id不可重复"}
    )
    # 匹配标签字段，必填，最大长度为 1024
    matcher_name = serializers.CharField(
        help_text="匹配标签",
        required=True, max_length=1024,
        error_messages={"required": "必须包含匹配标签"}
    )
    # 匹配标签值字段，必填，最大长度为 1024
    matcher_value = serializers.CharField(
        help_text="维护唯一标识",
        required=True, max_length=1024,
        error_messages={"required": "必须包含匹配标签值"}
    )

    def validate(self, attrs):
        """
        校验环境是否存在，当前方法直接返回验证数据，暂不实现校验逻辑。

        :param attrs: 验证数据
        :return: 验证数据
        """
        """ 校验env是否存在 """
        return attrs

    def create(self, validated_data):
        """
        进入或退出维护模式。

        :param validated_data: 验证后的数据
        :return: 验证后的数据
        :raises OperateError: 当操作失败时抛出异常
        """
        # 获取匹配标签
        matcher_name = validated_data.get("matcher_name")
        # 获取匹配标签值
        matcher_value = validated_data.get("matcher_value")
        # 查询匹配的维护记录
        maintain_queryset = Maintain.objects.filter(
            matcher_name=matcher_name, matcher_value=matcher_value)

        # 根据是否存在维护记录判断操作状态
        status = "开启" if not maintain_queryset.exists() else "关闭"

        # 创建 Alertmanager 实例
        alert_manager = Alertmanager()
        if not maintain_queryset.exists():
            # 若不存在维护记录，开启维护模式
            res_ls = alert_manager.set_maintain_by_env_name(matcher_value)
        else:
            # 若存在维护记录，关闭维护模式
            res_ls = alert_manager.revoke_maintain_by_env_name(matcher_value)

        # 操作失败
        if not res_ls:
            logger.error(f"全局{status}维护模式失败")
            # 操作失败记录写入
            raise OperateError(f"全局{status}维护模式失败")

        # 操作成功
        logger.info(f"全局{status}维护模式成功")
        return validated_data

    class Meta:
        """
        元数据类，指定序列化器对应的模型和字段。
        """
        model = Maintain
        fields = "__all__"


class ReceiveAlertSerializer(Serializer):
    """
    接收告警序列化器，用于处理接收到的告警信息并创建告警记录。
    """
    # 接收者字段，必填
    receiver = serializers.CharField(
        help_text="接收者",
        required=True,
        error_messages={"required": "不可为空"},
    )
    # 状态字段，必填
    status = serializers.CharField(
        help_text="状态",
        required=True,
        error_messages={"required": "不可为空"},
    )
    # 告警内容字段，必填
    alerts = serializers.ListField(
        help_text="告警内容",
        required=True,
        error_messages={"required": "不可为空"},
    )

    def update(self, instance, validated_data):
        """
        更新告警实例，当前方法为空，暂不实现更新逻辑。

        :param instance: 要更新的告警实例
        :param validated_data: 验证后的数据
        """
        pass

    def create(self, validated_data):
        """
        处理接收到的告警信息并创建告警记录。

        告警所属环境由 AlertAnalysis 三级解析（labels env 标签 →
        alert_host_ip 反查 Host.env → default），env_code 恒有值，
        此处仅按 code 取 Env 实例；取不到（Env 表异常）兜底 default
        并记录 warning（spec §6.2）。

        :param validated_data: 验证后的数据
        :return: 验证后的数据
        """
        # 获取告警内容列表
        alerts = validated_data.get('alerts')
        for ele in alerts:
            # 创建 AlertAnalysis 实例分析告警信息
            alert_analysis = AlertAnalysis(ele)
            alert_info = alert_analysis()
            if not alert_info:
                continue
            if alert_info.get('status') != 'firing':
                continue
            # 告警所属环境（解析链路见 AlertAnalysis.analysis_labels）
            env = Env.objects.filter(
                code=alert_info.get('env_code', 'default')).first()
            if env is None:
                env = Env.objects.filter(id=1).first()
                logger.warning(
                    f"告警 {alert_info.get('fingerprint')} 环境解析失败"
                    f"（env_code={alert_info.get('env_code')!r}），"
                    f"归入 default 环境")
            # 创建告警记录实例
            alert = Alert(
                is_read=0,
                alert_type=alert_info.get('alert_type'),
                alert_host_ip=alert_info.get('alert_host_ip'),
                alert_service_name=alert_info.get('alert_service_name'),
                alert_instance_name=alert_info.get('alert_instance_name'),
                alert_service_type='',  # TODO 暂时拿不到值
                alert_level=alert_info.get('alert_level'),
                alert_describe=alert_info.get('alert_describe'),
                alert_receiver=alert_info.get('alert_receiver'),
                alert_resolve='',  # TODO 待后续
                alert_time=alert_info.get('alert_time'),
                create_time=datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"),
                monitor_path=alert_info.get('monitor'),
                monitor_log=alert_info.get('monitor_log'),
                fingerprint=alert_info.get('fingerprint'),
                env=env
            )
            # 保存告警记录
            alert.save()
            # TODO service_name暂时为告警类型
            service_name = alert_info.get('alert_type')
            # 创建待自愈记录（同步写环境）
            WaitSelfHealing.objects.create(
                repair_ser=alert_info, service_name=service_name, env=env)
            if alert_info.get('alert_type') == 'host':
                # 若告警类型为主机，更新主机的告警数量
                Host.objects.filter(ip=alert_info.get('alert_host_ip')).update(
                    alert_num=F("alert_num") + 1)
            if alert_info.get('alert_type') == 'service':
                # 若告警类型为服务，更新服务的状态和告警数量
                Service.objects.filter(service_instance_name=alert_info.get(
                    'alert_instance_name')).filter(
                    ip=alert_info.get('alert_host_ip')).update(
                    service_status=Service.SERVICE_STATUS_STOP,
                    alert_count=F("alert_count") + 1)  # TODO 后续在模型中增加异常字段
        return validated_data


class MonitorAgentRestartSerializer(HostIdsSerializer):
    """ 监控Agent重启序列化类，用于处理监控 Agent 重启操作。 """

    def update(self, instance, validated_data):
        """
        更新监控 Agent 实例，当前方法为空，暂不实现更新逻辑。

        :param instance: 要更新的监控 Agent 实例
        :param validated_data: 验证后的数据
        """
        pass

    def create(self, validated_data):
        """
        监控Agent重启。

        :param validated_data: 验证后的数据
        :return: 验证后的数据
        """
        # 获取主机 ID 列表
        host_ids = validated_data.get("host_ids", [])
        # 过滤出符合条件的主机 ID 列表
        filter_host_ids = list(
            Host.objects.filter(
                id__in=host_ids,
                monitor_agent__in=[
                    str(Host.AGENT_RUNNING),
                    str(Host.AGENT_RESTART),
                    str(Host.AGENT_START_ERROR)
                ]
            ).values_list("id", flat=True)
        )
        for item in filter_host_ids:
            # 异步执行监控 Agent 重启任务
            monitor_agent_restart.delay(item)
        # 下发任务后批量更新重启主机状态
        Host.objects.filter(
            id__in=filter_host_ids
        ).update(monitor_agent=Host.AGENT_RESTART)
        return validated_data


class RuleSerializer(ModelSerializer):
    """
    内置规则序列化类，用于序列化和反序列化内置规则数据。
    """

    class Meta:
        """
        元数据类，指定序列化器对应的模型和字段。
        """
        model = Rule
        fields = '__all__'


class QuotaSerializer(ModelSerializer):
    """
    告警规则序列化类，用于序列化和反序列化告警规则数据。
    """

    class Meta:
        """
        元数据类，指定序列化器对应的模型和字段。
        """
        model = AlertRule
        fields = '__all__'
