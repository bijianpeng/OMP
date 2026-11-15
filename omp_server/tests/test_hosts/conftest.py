# -*- coding: utf-8 -*-

"""
hosts 测试目录配置

本地 Windows venv 未安装 coreapi（omp_server.urls 的 docs 接口
include_docs_urls 在模块导入期实例化 SchemaGenerator，缺包即断言失败），
参照 tests/test_promemonitor/conftest.py 的做法以 MagicMock 占位，
使 URLconf 可导入；CI 环境装有真实 coreapi，本 stub 不影响其行为
（docs 接口在测试中不会被请求）。
"""

import sys
from unittest.mock import MagicMock

if "coreapi" not in sys.modules:
    sys.modules["coreapi"] = MagicMock()
