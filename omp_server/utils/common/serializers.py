"""
公共序列化器
"""

# 从 rest_framework 库导入 serializers 模块，用于创建序列化器
from rest_framework import serializers
# 从 rest_framework 库的 exceptions 模块导入 ValidationError 异常，用于数据校验错误处理
from rest_framework.exceptions import ValidationError

# 从 db_models 包导入 models 模块
from db_models import models
# 从 db_models 包的 models 模块导入 Host 和 UploadFileHistory 模型
from db_models.models import Host, UploadFileHistory
from utils.middleware_handler import get_request_env


class HostIdsSerializer(serializers.Serializer):
    """ 主机 id 列表序列化类，用于验证主机 ID 列表数据 """

    # 定义一个列表字段，用于接收主机 ID 列表
    host_ids = serializers.ListField(
        help_text="主机 ID 列表",  # 字段说明
        required=True,  # 该字段为必填项
        error_messages={"required": "必须包含[host_ids]字段"},  # 字段缺失时的错误信息
        allow_empty=False  # 不允许列表为空
    )

    def validate_host_ids(self, host_ids):
        """
        校验主机 ID 列表中主机是否都存在（仅限当前请求环境，
        跨环境主机 id 视为不存在——多环境架构 Task 7b）

        :param host_ids: 传入的主机 ID 列表
        :return: 经过校验的主机 ID 列表
        """
        # 查询数据库中存在的主机 ID（按当前环境上下文过滤）
        exists_ids = Host.objects.filter(
            id__in=host_ids,
            env=get_request_env(self.context.get("request"))
        ).values_list("id", flat=True)
        # 计算传入的主机 ID 列表与数据库中存在的主机 ID 列表的差集
        diff = set(host_ids) - set(exists_ids)
        if diff:
            # 若存在不存在的主机 ID，抛出验证错误
            raise ValidationError(
                f"主机列表中有不存在的ID ["
                f"{','.join(map(lambda x: str(x), diff))}"
                f"]")
        return host_ids


class UploadFileSerializer(serializers.Serializer):
    """ 文件上传序列化类，用于验证文件上传相关数据 """

    # 定义文件字段，用于接收上传的文件
    file = serializers.FileField(
        help_text="上传的文件",  # 字段说明
        required=True,  # 该字段为必填项
        error_messages={"required": "必须包含[file]字段"}  # 字段缺失时的错误信息
    )
    # 定义字符字段，用于接收文件存储方式
    storage_klass = serializers.CharField(
        help_text="存储方式", required=False, default="location")
    # 定义字符字段，用于接收需要上传文件的模型名称
    module = serializers.CharField(
        help_text="需要上传文件的model", required=False, default="")
    # 定义整数字段，用于接收需要上传文件的模型 ID
    module_id = serializers.IntegerField(
        help_text="需要上传文件的model id", required=False, default=0)
    # 定义字符字段，用于接收保存后的文件名
    file_name = serializers.CharField(
        help_text="保存后文件名", required=False, default="")
    # 定义字符字段，用于接收保存后文件的访问路径
    file_url = serializers.CharField(
        help_text="保存后文件访问路径", required=False, default="")
    # 定义字符字段，用于接收文件的 union_id
    union_id = serializers.CharField(
        help_text="文件union_id", required=False, default="")

    def validate(self, attrs):
        """
        对整个数据进行校验

        :param attrs: 传入的待校验数据字典
        :return: 经过校验的数据字典
        """
        # 获取模块名称
        module = attrs.get("module")
        # 获取模块 ID
        module_id = attrs.get("module_id")
        if module:
            # 根据模块名称和模块 ID 查询对应的对象
            _obj = getattr(models, module).objects.filter(id=module_id).first()
            if not _obj:
                # 若对象不存在，抛出验证错误
                raise ValidationError({
                    "module": "请确定指定上传文件的module"
                })
            # 将查询到的对象设置为序列化器的属性
            setattr(self, "module_obj", _obj)
        if attrs.get("storage_klass", "location") \
                not in UploadFileHistory.STORAGE_KLASS:
            # 若存储方式不在允许的范围内，抛出验证错误
            raise ValidationError({
                "storage_klass":
                    f"文件存储方式目前只支持{UploadFileHistory.STORAGE_KLASS}"
            })
        return attrs

    def create(self, validated_data):
        """
        创建上传文件记录

        :param validated_data: 经过校验的数据字典
        :return: 更新后的经过校验的数据字典
        """
        # 从上下文中获取请求的用户
        user = self.context.get("request").user
        # 获取上传的文件
        file = validated_data.get("file")
        if hasattr(self, "module_obj"):
            # 若存在模块对象，获取该对象
            module_obj = self.module_obj
        else:
            module_obj = None
        # 根据存储方式调用相应的方法创建上传文件记录
        obj = getattr(
            UploadFileHistory,
            validated_data.get("storage_klass", "location")
        )(file, module_obj, user)
        # 更新经过校验的数据字典，添加文件名、union_id 和文件访问路径
        validated_data.update(
            {
                "file_name": obj.file_name,
                "union_id": obj.union_id,
                "file_url": obj.file_url
            }
        )
        return validated_data


class DynamicFieldsModelSerializer(serializers.ModelSerializer):
    """
    一个继承自 ModelSerializer 的序列化器，它接受一个额外的 `fields` 参数，
    用于控制应该显示哪些字段。
    """

    def __init__(self, *args, **kwargs):
        # 从 kwargs 中移除 'fields' 参数，避免传递给父类
        fields = kwargs.pop('fields', None)

        # 正常地实例化父类
        super(DynamicFieldsModelSerializer, self).__init__(*args, **kwargs)

        if fields is not None:
            # 将传入的字段名转换为集合
            allowed = set(fields)
            # 获取当前序列化器的所有字段名集合
            existing = set(self.fields)
            # 遍历需要移除的字段名
            for field_name in existing - allowed:
                # 从序列化器中移除不需要的字段
                self.fields.pop(field_name)
