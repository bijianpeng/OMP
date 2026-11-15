# -*- coding: utf-8 -*-
# Project: public_utils
# Author: omp
# Create time: 2021-10-09 19:55
# IDE: PyCharm
# Version: 1.0
# Introduction:

"""
文件md5值处理模块
此模块包含多个实用函数，用于执行本地命令、计算文件MD5值、检查IP地址和端口连通性、
格式化时间差和文件大小等操作。
"""

import os
import socket
import hashlib
import ipaddress
import subprocess


def local_cmd(command):
    """
    执行本地shell命令

    :param command: 要执行的shell命令
    :return: 元组 (stdout, stderr, ret_code)，分别表示标准输出、标准错误输出和命令返回码
    """
    # 为了确保执行的命令是安全的，这里对输入的command进行基本的类型和内容检查
    if not isinstance(command, str):
        return "", "命令必须为字符串类型", -1
    # 禁止执行危险命令，如删除根目录等
    dangerous_patterns = [
        "mkfs", ":(){:|:&};:", "shutdown", "reboot", "init 0", "init 6"
    ]
    for pattern in dangerous_patterns:
        if pattern in command:
            return "", f"检测到危险命令: {pattern}，已拒绝执行", -1
    if command == "rm -rf /":
        return "", f"检测到危险命令: {command}，已拒绝执行", -1
    # 使用subprocess.Popen执行命令，并捕获标准输出和标准错误输出
    p = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=True
    )
    # 等待命令执行完成并获取输出
    stdout, stderr = p.communicate()
    # 对输出进行解码，忽略解码错误
    _out, _err, _code = \
        stdout.decode("utf8", errors='ignore'), stderr.decode("utf8", errors='ignore'), p.returncode
    return _out, _err, _code


def get_file_md5(file_path):
    """
    获取文件的md5值

    :param file_path: 文件的路径
    :return: 元组 (flag, md5_value)，flag表示文件是否存在，md5_value为文件的MD5值或错误信息
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        return False, "File not exists!"
    # 创建md5对象
    # 出于安全考虑，显式指定使用 hashlib.md5 的默认实现（不依赖外部库），避免被 monkey patch
    m = hashlib.md5(usedforsecurity=True)
    # 以二进制只读模式打开文件
    with open(file_path, 'rb') as f_obj:
        while True:
            # 每次读取4096字节数据
            data = f_obj.read(4096)
            if not data:
                break
            # 更新md5对象
            m.update(data)
    return True, m.hexdigest()


def check_is_ip_address(value):
    """
    检查输入值是否为有效的ip地址

    :param value: 要检查的ip地址字符串
    :return: 元组 (flag, result)，flag表示是否为有效ip地址，result为ip地址或错误信息
    """
    try:
        # 尝试将输入值转换为ip地址对象
        ipaddress.ip_address(value)
        return True, value
    except ValueError:
        return False, "not valid ip address!"


def check_ip_port(ip, port):
    """
    检查指定ip和端口的联通性

    :param ip: 要检查的ip地址
    :param port: 要检查的端口号
    :return: 元组 (flag, message)，flag表示是否联通，message为相应的提示信息
    """
    # 检查ip地址是否有效
    if not check_is_ip_address(value=ip)[0]:
        return False, "ip address not correct"
    try:
        # 将端口号转换为整数
        int_port = int(port)
        # 检查端口号是否在有效范围内
        if int_port < 0 or int_port > 65535:
            return False, "port must be 0 ~ 65535"
    except ValueError:
        return False, "port must be 0 ~ 65535, int or string"
    # 创建TCP套接字对象
    sock_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 尝试连接指定ip和端口
    result = sock_obj.connect_ex((ip, int_port))
    if result == 0:
        return_tuple = (True, "success")
    else:
        return_tuple = (False, "failed")
    # 关闭套接字
    sock_obj.close()
    return return_tuple


class DurationTime:
    """
    用于分析和处理时间差的类，将总秒数转换为天、小时、分钟和秒。
    """

    def __init__(self, seconds):
        """
        初始化DurationTime类

        :param seconds: 总秒数
        """
        self.second = seconds
        self.minute = self.hour = self.day = 0

    def analysis_day(self):
        """
        分析小时数，将超过24小时的部分转换为天数
        """
        day, hour = divmod(self.hour, 24)
        setattr(self, "hour", hour)
        setattr(self, "day", day)

    def analysis_hour(self):
        """
        分析分钟数，将超过60分钟的部分转换为小时数
        """
        hour, minute = divmod(self.minute, 60)
        setattr(self, "minute", minute)
        setattr(self, "hour", hour)

    def analysis_minute(self):
        """
        分析秒数，将超过60秒的部分转换为分钟数
        """
        minute, second = divmod(self.second, 60)
        setattr(self, "second", second)
        setattr(self, "minute", minute)

    def __call__(self, *args, **kwargs):
        """
        调用该类的实例时，依次分析秒、分钟、小时并转换为对应的天、小时、分钟和秒

        :return: 处理后的实例对象
        """
        for key in ["minute", "hour", "day"]:
            getattr(self, f"analysis_{key}")()
            if not getattr(self, key):
                return self
        return self


def timedelta_strftime(timedelta):
    """
    四舍五入格式化timedelta对象为字符串

    :param timedelta: datetime.timedelta对象
    :return: 格式化后的字符串，格式为 "XX天XX时XX分XX秒"
    """
    # 对总秒数进行四舍五入
    seconds = round(timedelta.total_seconds())
    # 创建DurationTime实例并处理时间
    duration = DurationTime(seconds)()
    # 定义英文时间单位到中文时间单位的映射
    en_zh = [("day", "天"), ("hour", "时"), ("minute", "分"), ("second", "秒")]
    strftime = ""
    for en, zh in en_zh:
        if strftime:
            strftime += f"{getattr(duration, en)}{zh}"
        elif not strftime and getattr(duration, en):
            strftime += f"{getattr(duration, en)}{zh}"
    return strftime


def file_md5(file_path):
    """
    使用系统的md5sum命令计算文件的md5值

    :param file_path: 文件的路径
    :return: 文件的md5值，如果命令执行失败则返回None
    """
    # 执行md5sum命令
    md5_out = local_cmd(f'md5sum {file_path}')

    # 检查命令返回码
    if md5_out[2] != 0:
        return None
    # 提取md5值
    return md5_out[0].split()[0]


def format_location_size(size):
    """
    格式化文件大小，将字节数转换为合适的单位（K、M、G）

    :param size: 文件大小，单位为字节
    :return: 格式化后的字符串，包含合适的单位
    """
    if int(size/1024) < 100:
        return "%.3f" % (size / 1024) + "K"
    size = size/1024
    if int(size/1024) < 100:
        return "%.3f" % (size / 1024) + "M"
    return "%.3f" % (size/1024/1024) + "G"
