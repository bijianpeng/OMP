import os
import sys
import types
import django
from django.conf import settings

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Windows 本地开发测试 stub:避免直接 import salt(SaltStack 在 Windows 上
# 无法运行,需要 OpenSSL libcrypto 等系统库)。
# 仅当设置 OMP_TEST_DB=sqlite 时注入 stub,生产 CI/测试环境不影响。
if os.environ.get("OMP_TEST_DB") == "sqlite":
    if "salt" not in sys.modules:
        salt_stub = types.ModuleType("salt")
        salt_client_stub = types.ModuleType("salt.client")
        salt_client_stub.LocalClient = object  # 仅占位,测试不会真实调用
        salt_stub.client = salt_client_stub
        sys.modules["salt"] = salt_stub
        sys.modules["salt.client"] = salt_client_stub
    # migration 0024 调用 find_tools_package() 会用 RedisDB().conn.lock,
    # 本地无 Redis 时跳过(测试不依赖 ToolInfo 扫描结果)。
    from unittest.mock import patch as _patch
    _patch("tool.find_tools.find_tools_package", lambda *a, **k: None).start()

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'omp_server.settings')

# 配置Django
django.setup()

# 强制使用MySQL数据库进行测试
if not settings.configured:
    settings.configure(
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': 'omp',
                'USER': 'root',
                'PASSWORD': os.environ.get('OMP_TEST_MYSQL_PASSWORD', ''),
                'HOST': '127.0.0.1',
                'PORT': '3306',
                'OPTIONS': {
                    'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                },
            }
        },
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'db_models',
            'users',
            'app_store',
            'services',
            'hosts',
            'inspection',
            'promemonitor',
        ],
        MIDDLEWARE=[
            'django.middleware.security.SecurityMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            'django.contrib.messages.middleware.MessageMiddleware',
            'django.middleware.clickjacking.XFrameOptionsMiddleware',
        ],
        ROOT_URLCONF='omp_server.urls',
        SECRET_KEY='test-secret-key',
        USE_TZ=False,
    )
    django.setup()
else:
    # 如果settings已经配置，强制覆盖数据库设置
    # 默认走 MySQL(CI/测试环境)。
    # 本地 Windows 开发若设置 OMP_TEST_DB=sqlite,则切换为 in-memory sqlite。
    # 三处必须同步覆盖:
    #   1) settings.DATABASES(供 TestCase setup_databases 读取)
    #   2) connections._databases(底层 ConnectionHandler 数据源)
    #   3) 清 cached_property `databases` 与 `_connections.default` 缓存,
    #      避免 setup() 过程中已实例化的 MySQL wrapper 复用。
    if os.environ.get("OMP_TEST_DB") == "sqlite":
        _sqlite_db = {
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        }
        settings.DATABASES = _sqlite_db
        from django.db import connections
        connections._databases = _sqlite_db
        connections.__dict__.pop("databases", None)
        try:
            del connections._connections.default
        except AttributeError:
            pass
    else:
        settings.DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': 'omp',
                'USER': 'root',
                'PASSWORD': os.environ.get('OMP_TEST_MYSQL_PASSWORD', ''),
                'HOST': '127.0.0.1',
                'PORT': '3306',
                'OPTIONS': {
                    'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                },
            }
        } 