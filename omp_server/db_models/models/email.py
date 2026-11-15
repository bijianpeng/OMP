# 导入日志记录模块，用于记录程序运行过程中的信息
import logging
# 导入操作系统相关模块，用于处理文件路径等操作
import os

# 导入 requests 库，用于发送 HTTP 请求
import requests
# 从 django 数据库模块导入模型基类
from django.db import models
# 导入 ruamel.yaml 库，用于处理 YAML 文件
from ruamel import yaml

# 从当前目录的 env 模块导入 Env 类
from .env import Env
# 从当前目录的 monitor 模块导入 AlertSendWaySetting 类
from .monitor import AlertSendWaySetting


# 配置日志记录器，使用名为 'server' 的日志记录器
logger = logging.getLogger('server')


class EmailSMTPSetting(models.Model):
    """
    邮箱 SMTP 服务器配置模型，用于存储和管理平台邮件服务器的相关配置信息。
    """
    # 邮箱 SMTP 主机地址字段，使用 EmailField 类型验证输入的邮箱地址格式
    email_host = models.EmailField("邮箱SMTP主机地址:smtp.163.com", null=True)
    # 邮箱 SMTP 端口字段，整数类型
    email_port = models.IntegerField("邮箱SMTP端口:465", null=True)
    # 邮箱 SMTP 服务器用户名，最大长度为 128
    email_host_user = models.CharField(
        "邮箱SMTP服务器用户名:a@163.com", max_length=128, null=True)
    # 邮箱 SMTP 服务器秘钥，最大长度为 128
    email_host_password = models.CharField(
        "邮箱SMTP服务器秘钥", max_length=128, null=True)

    class Meta:
        # 数据库表名
        db_table = 'omp_email_smtp_setting'
        # 模型的单数和复数显示名称
        verbose_name = verbose_name_plural = '平台邮件服务器配置'

    # 警报管理配置键映射字典，用于将警报管理配置键映射到模型的字段
    alert_manage_key = {
        "EMAIL_SEND": "email_host_user",
        "smtp_auth_username": "email_host_user",
        "EMAIL_SEND_PASSWORD": "email_host_password",
        "smtp_auth_password": "email_host_password",
        "EMAIL_ADDRESS": "email_url",
    }

    def get_dict(self):
        """
        将当前模型实例的邮箱配置信息转换为字典。

        :return: 包含邮箱配置信息的字典
        """
        return {
            "host": self.email_host,
            "port": self.email_port,
            "username": self.email_host_user,
            "password": self.email_host_password
        }

    @property
    def email_url(self):
        """
        获取邮箱地址，若已缓存则直接返回，否则从 AlertSendWaySetting 中查询。

        :return: 邮箱地址
        """
        if hasattr(self, "email"):
            return self.email
        # 查询邮件发送方式设置，获取第一个邮件发送方式
        email_send = AlertSendWaySetting.objects.filter(
            way_name="email").first()
        email = ""
        if email_send and email_send.used:
            # 若邮件发送方式存在且启用，获取服务器 URL 的第一个邮箱地址
            email = email_send.server_url.split(",")[0]
        # 将查询到的邮箱地址缓存到实例属性中
        setattr(self, "email", email)
        return email

    def update_config(self, key):
        """
        根据传入的配置键更新配置值。

        :param key: 配置键
        :return: 对应的配置值，若未匹配到则返回 None
        """
        if key in {"EMAIL_SEND_USER", "smtp_from"}:
            value = self.email_host_user
        elif key in {"SMTP_SMARTHOST", "smtp_smarthost"}:
            value = f"{self.email_host}:{self.email_port}"
        elif key in self.alert_manage_key:
            value = getattr(self, self.alert_manage_key.get(key))
        elif key in {"smtp_hello", "SMTP_HELLO"}:
            value = ".".join(self.email_host.split(".")[-2:])
        elif key == "RECEIVER":
            value = "test"
        else:
            value = None
        return value

    @staticmethod
    def reload_alert_manage():
        """
        重新加载警报管理器配置。

        :return: 重新加载成功返回 True，失败返回 False
        """
        # 从 promemonitor.alertmanager 模块导入 Alertmanager 类
        from promemonitor.alertmanager import Alertmanager
        # 获取警报管理器的配置 URL
        alertmanager_url = Alertmanager.get_alertmanager_config()
        # 获取警报管理器的基本认证信息
        _basic_auth = Alertmanager().basic_auth
        try:
            # 发送 POST 请求重新加载警报管理器配置
            response = requests.post(f"http://{alertmanager_url}/-/reload", auth=_basic_auth)  # NOQA
        except Exception as e:
            # 记录重新加载配置出错的日志
            logger.error(f"重载alertmanager配置出错！错误信息：{str(e)}")
            return False
        if response.status_code == 200:
            return True
        return False

    def set_omp_conf(self):
        """
        更新 omp.yaml 配置文件中的警报管理器相关配置。
        """
        # 从 utils.parse_config 模块导入配置文件路径
        from utils.parse_config import config_file_path
        # 以只读模式打开 omp.yaml 文件
        with open(config_file_path, "r", encoding="utf8") as fp:
            content = fp.read()
        # 创建 YAML 对象
        my_yaml = yaml.YAML()
        # 加载 YAML 文件内容
        code = my_yaml.load(content)
        # 遍历警报管理器配置项
        for key, value in code.get("alert_manager", {}).items():
            if key == "send_email":
                # 根据邮箱地址是否存在设置发送邮件标志
                value = bool(self.email_url)
            else:
                # 根据配置键更新配置值
                value = self.update_config(key)
            if value is None:
                continue
            # 更新警报管理器配置项的值
            code["alert_manager"][key] = value
        # 以写入模式打开 omp.yaml 文件，将更新后的配置写入文件
        with open(config_file_path, "w", encoding="utf8") as fp:
            my_yaml.dump(code, fp)

    def set_alert_manage_config(self):
        """
        更新警报管理器的配置文件，并重新加载配置。

        :return: 重新加载配置成功返回 True，失败返回 False
        """
        # 从 omp_server.settings 模块导入项目根目录
        from omp_server.settings import PROJECT_DIR
        # 拼接警报管理器配置文件路径
        config_path = os.path.join(
            PROJECT_DIR, "component/alertmanager/conf/alertmanager.yml")
        # 以只读模式打开警报管理器配置文件
        with open(config_path, "r", encoding="utf8") as fp:
            code = yaml.load(fp.read(), yaml.Loader)
        # 遍历警报管理器全局配置项
        for key, value in code.get("global", {}).items():
            # 根据配置键更新配置值
            value = self.update_config(key)
            if value is None:
                continue
            # 更新全局配置项的值
            code["global"][key] = value

        if not self.email_url:
            # 若邮箱地址不存在，移除接收者配置中的邮件配置
            for receiver in code.get("receivers"):
                if "email_configs" in receiver:
                    code.get("receivers")[0].pop("email_configs", {})
        else:
            # 若邮箱地址存在，设置邮件配置
            email_configs = [
                {
                    "send_resolved": bool(self.email_url),
                    "to": self.email_url,
                    "headers": {"Subject": "OMP ALERT"},
                    "html": '{{ template \"email.to.html\" . }}'
                }
            ]
            code.get("receivers")[0]["email_configs"] = email_configs
        # 设置警报管理器模板路径
        code["templates"] = [
            f"{PROJECT_DIR}/component/alertmanager/templates/*tmpl"]
        # 以写入模式打开警报管理器配置文件，将更新后的配置写入文件
        with open(config_path, "w", encoding="utf8") as fp:
            yaml.dump(code, fp, Dumper=yaml.RoundTripDumper)
        # 重新加载警报管理器配置
        return self.reload_alert_manage()

    def update_setting_config(self):
        """
        更新配置文件，包括 omp.yaml 和警报管理器配置文件。

        :return: 一个元组，包含警报管理器配置更新结果和邮箱地址
        """
        # 更新 omp.yaml 配置文件
        self.set_omp_conf()
        # 更新警报管理器配置文件并重新加载配置，返回结果和邮箱地址
        return self.set_alert_manage_config(), self.email_url


class ModuleSendEmailSetting(models.Model):
    """
    功能模块邮件发送设置模型，用于存储和管理各功能模块的邮件发送配置信息。
    """
    # 功能模块名称字段，最大长度为 64
    module = models.CharField(
        "功能模块:BackupSetting,JobSetting", max_length=64)
    # 是否开启邮件推送字段，布尔类型，默认值为 False
    send_email = models.BooleanField("是否开启邮件推送", default=False)
    # 邮箱接收用户字段，文本类型，默认值为空字符串
    to_users = models.TextField("邮箱接收用户", default="")
    # 环境字段，外键类型，关联环境表，级联删除，默认值为 1
    env = models.ForeignKey(
        Env, on_delete=models.CASCADE, verbose_name="环境", default=1)

    class Meta:
        # 数据库表名
        db_table = 'omp_module_email_send_setting'
        # 模型的单数和复数显示名称
        verbose_name = verbose_name_plural = '平台邮件发送账号配置'

    @classmethod
    def get_email_settings(cls, env_id, module):
        """
        根据环境 id 和功能模块名称获取邮件发送设置。

        :param env_id: 环境 id
        :param module: 功能模块名称
        :return: 邮件发送设置模型实例，若不存在则返回 None
        """
        try:
            # 根据环境 id 和功能模块名称查询邮件发送设置
            _obj = cls.objects.get(env_id=env_id, module=module)
        except Exception as e:
            # 记录查询出错的日志
            logger.error(e)
            logger.error(f"module: {module}, env_id:{env_id}邮箱配置不存在")
            return None
        return _obj

    @classmethod
    def update_email_settings(cls, env_id, module, send_email, to_users):
        """
        根据环境 id 和功能模块名称更新邮件发送设置。

        :param env_id: 环境 id
        :param module: 功能模块名称
        :param send_email: 是否开启邮件推送
        :param to_users: 邮箱接收用户
        :return: 更新后的邮件发送设置模型实例
        """
        # 根据环境 id 和功能模块名称获取或创建邮件发送设置实例
        _obj, _ = cls.objects.get_or_create(env_id=env_id, module=module)
        # 更新是否开启邮件推送字段
        _obj.send_email = send_email
        # 更新邮箱接收用户字段
        _obj.to_users = to_users
        # 保存更新后的实例
        _obj.save()
