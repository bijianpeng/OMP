import json
import os

# 从 Django 配置模块导入设置
from django.conf import settings

# 从数据库模型模块导入所需的模型类
from db_models.models import DetailInstallHistory, Service, Host, UpgradeDetail
# 从工具插件模块导入 Salt 客户端类
from utils.plugin.salt_client import SaltClient
from app_store.new_install_utils import merge_ports_into_install_args


class DataJsonUpdate(object):
    """ 生成data.json数据 """

    def __init__(self, operation_uuid, env_id=None):
        """
        data.json数据生成方法
        :param operation_uuid: 唯一操作uuid
        :type operation_uuid: str
        :param env_id: 升级所属环境 id（多环境架构：按环境过滤服务
            来源与 json 下发主机，避免混入/下发到其它环境；None 时
            保持存量全量行为，兼容历史调用方）
        :type env_id: int
        """
        # 根据操作 UUID 生成 JSON 文件的名称
        self.json_name = f"{operation_uuid}.json"
        # 拼接 JSON 文件在数据文件目录下的路径
        self.data_path = os.path.join("data_files", self.json_name)
        self.env_id = env_id

    def get_ser_install_args(self, obj, app_install_args=None):
        """
        获取服务的安装参数
        :param obj: Service obj，服务对象
        :param app_install_args: app_install_args, list，应用安装参数列表
        :return: 包含安装参数和部署模式的字典
        """
        # 从安装历史记录中查找该服务的部署详情
        deploy_detail = DetailInstallHistory.objects.filter(
            service=obj).first()
        # 初始化安装参数列表
        install_args = []
        # 初始化部署模式
        deploy_mode = ""
        if deploy_detail:
            # 从部署详情中获取安装参数
            install_args = \
                deploy_detail.install_detail_args.get("install_args", [])
            # 从部署详情中获取部署模式
            deploy_mode = \
                deploy_detail.install_detail_args.get("deploy_mode")
        # 初始化旧参数字典，用于快速查找
        old_arg_dict = {}
        for old_arg in install_args:
            # 以参数键为键，将旧参数存入字典
            old_arg_dict[old_arg["key"]] = old_arg
        if app_install_args:
            for new_arg in app_install_args:
                if new_arg.get("key") not in old_arg_dict:
                    # 格式化新参数的默认值
                    new_arg["default"] = new_arg["default"].format(
                        data_path="data_path")
                    # 将新参数添加到安装参数列表中
                    install_args.append(new_arg)
        if deploy_detail:
            # 更新部署详情中的安装参数
            deploy_detail.install_detail_args["install_args"] = install_args
            # 保存更新后的部署详情
            deploy_detail.save()
        return {
            "install_args": install_args,
            "deploy_mode": deploy_mode
        }

    def parse_single_service(self, service, tag_app=None):
        """
        解析单个服务数据
        :param service: Service，服务对象
        :param tag_app: Service，目标应用对象
        :return: 包含服务信息的字典
        """
        # 初始化服务信息字典
        _ser_dic = {
            "ip": service.ip,  # 服务所在主机的 IP 地址
            "name": service.service.app_name,  # 服务的应用名称
            "role": service.service_role if service.service_role else "master",  # 服务角色，默认为 master
            "instance_name": service.service_instance_name,  # 服务实例名称
            "cluster_name": service.cluster.cluster_name if service.cluster else None,  # 服务所在集群名称
            "vip": service.vip,  # 服务的虚拟 IP 地址
            "ports": json.loads(service.service_port or '[]'),  # 服务使用的端口列表
            "dependence": json.loads(service.service_dependence or '[]'),  # 服务的依赖列表
        }
        if service.service.app_name == "hadoop":
            # 若服务为 hadoop，重新生成实例名称
            _ser_dic["instance_name"] = \
                "hadoop-" + "-".join(service.ip.split(".")[-2:])
        if tag_app:
            # 若存在目标应用，更新端口信息
            _ser_dic["ports"] = service.update_port(
                json.loads(tag_app.app_port or '[]')
            )
            # 若存在目标应用，更新依赖信息
            _ser_dic["dependence"] = service.update_dependence(
                service.service_dependence,
                json.loads(tag_app.app_dependence or '[]')
            )
            # 获取服务的安装参数
            _others = self.get_ser_install_args(
                service, json.loads(tag_app.app_install_args or '[]'))
        else:
            # 若不存在目标应用，直接获取服务的安装参数
            _others = self.get_ser_install_args(service)
        # 将安装参数和部署模式信息更新到服务信息字典中
        _ser_dic.update(_others)
        # 合并 ports 到 install_args 末尾(幂等),保证目标机 install.py
        # 能从 self.install_args 取到端口字段
        _ser_dic["install_args"] = merge_ports_into_install_args(
            _ser_dic.get("install_args") or [],
            _ser_dic.get("ports") or [],
        )
        return _ser_dic

    def make_data_json(self, json_lst):
        """
        创建data.json数据文件
        :param json_lst: 服务及分布信息组成的列表
        :type json_lst: list
        :return: 无
        """
        # 拼接 data.json 文件的完整路径
        _path = os.path.join(
            settings.PROJECT_DIR,
            "package_hub",
            self.data_path
        )
        # 检查文件目录是否存在，若不存在则创建
        if not os.path.exists(os.path.dirname(_path)):
            os.makedirs(os.path.dirname(_path))
        # 以写入模式打开文件，将服务信息列表写入文件
        with open(_path, "w", encoding="utf8") as fp:
            json.dump(json_lst, fp, ensure_ascii=False, indent=2)

    def decompose_detail(self, details):
        """
        分解升级详情，生成服务实例名称到目标应用的映射字典
        :param details: 升级详情列表
        :return: 服务实例名称到目标应用的映射字典
        """
        _dic = {}
        if not details:
            return _dic
        for detail in details:
            if isinstance(detail, UpgradeDetail):
                # 若为升级详情，将服务实例名称和目标应用存入字典
                _dic[detail.service.service_instance_name] = detail.target_app
            else:
                # 若不是升级详情，将升级记录中的服务实例名称和当前应用存入字典
                _dic[detail.upgrade.service.service_instance_name] = \
                    detail.current_app
        return _dic

    def load_json_lst(self, details):
        """
        加载服务信息列表，用于生成 data.json 文件
        :param details: 升级详情分解后的字典
        :return: 包含服务信息的列表
        """
        # 在json文件中标记该服务所在主机上的agent的地址
        ip_agent_dir_dir = {
            ip: agent_dir for ip, agent_dir in
            Host.objects.values_list("ip", "agent_dir")
        }
        # 初始化服务信息列表
        json_lst = list()
        # 多环境按升级所属环境过滤服务来源，避免 data.json 混入
        # 其它环境的服务（与安装链路 DataJson 同款隔离，见
        # app_store install_utils/new_install_utils）；env_id 为
        # None 时保持存量全量行为（兼容历史调用方）
        if self.env_id:
            services = Service.split_objects.filter(env_id=self.env_id)
        else:
            services = Service.split_objects.all()
        for service in services:
            # 获取该服务对应的目标应用
            tag_app = details.get(service.service_instance_name)
            # 解析单个服务的数据
            _item = self.parse_single_service(service, tag_app)
            # 添加该服务所在主机的 agent 目录信息
            _item["agent_dir"] = ip_agent_dir_dir.get(_item.get("ip"))
            # 将该服务信息添加到列表中
            json_lst.append(_item)
        return json_lst

    def send_data_json_target(self, salt_obj, target_ip):
        """
        向指定 IP 地址的主机发送 data.json 文件
        :param salt_obj: SaltClient 对象，用于文件传输
        :param target_ip: 目标主机的 IP 地址
        :return: Salt 客户端文件传输的结果
        """
        # 根据 IP 地址获取主机对象
        host = Host.objects.get(ip=target_ip)
        # 拼接目标主机上 data.json 文件的路径
        json_target_path = os.path.join(
            host.data_folder, "omp_packages", self.json_name)
        # 调用 Salt 客户端的文件传输方法
        return salt_obj.cp_file(
            target=target_ip,
            source_path=self.data_path,
            target_path=json_target_path
        )

    def send_data_json_all(self):
        """
        向所有主机发送 data.json 文件
        :return: 包含发送失败信息的列表
        """
        # 获取所有主机的 IP 地址和数据文件夹路径；
        # 多环境按升级所属环境过滤，json 不再 cp 到其它环境主机
        # （env_id 为 None 时保持存量全量行为）
        if self.env_id:
            hosts = Host.objects.filter(
                env_id=self.env_id).values_list("ip", "data_folder")
        else:
            hosts = Host.objects.all().values_list("ip", "data_folder")
        # 初始化失败信息列表
        fail_message = []
        # 创建 Salt 客户端对象
        salt_obj = SaltClient()
        for host in hosts:
            # 拼接目标主机上 data.json 文件的路径
            json_target_path = os.path.join(
                host[1], "omp_packages", self.json_name)
            # 调用 Salt 客户端的文件传输方法
            state, message = salt_obj.cp_file(
                target=host[0],
                source_path=self.data_path,
                target_path=json_target_path
            )
            if not state:
                # 若发送失败，将失败信息添加到列表中
                fail_message.append(
                    f"ip:{host[1]}更新data.json失败，错误：{message}")
        return fail_message

    def create_json_file(self, details=None):
        """
        更新data.json
        :param details: 升级details
        :return: 无
        """
        # 分解升级详情
        details = self.decompose_detail(details)
        # 加载服务信息列表
        current_json_lst = self.load_json_lst(details)
        # 生成data.json
        self.make_data_json(json_lst=current_json_lst)
