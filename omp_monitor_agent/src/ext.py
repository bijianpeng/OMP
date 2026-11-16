import os
import sys
import logging
from sanic import Sanic
from ruamel.yaml import YAML


def _get_project_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app():
    app = Sanic("monitor_agent")
    project_path = _get_project_path()
    config_path = os.path.join(project_path, "conf", "config.yaml")
    yaml = YAML()
    with open(config_path, 'r') as f:
        config = yaml.load(f)
    for key, value in config.items():
        app.config[key] = value
    return app


_project_path = _get_project_path()
_config_path = os.path.join(_project_path, "conf", "config.yaml")
_log_level = logging.ERROR
_log_path = os.path.join(_project_path, "log", "app.log")

try:
    yaml = YAML()
    with open(_config_path, 'r') as f:
        _config = yaml.load(f)
    if _config.get('LOG_LEVEL'):
        _log_level = getattr(logging, _config['LOG_LEVEL'].upper(), logging.ERROR)
    if _config.get('LOG_PATH'):
        _log_path = os.path.join(_project_path, _config['LOG_PATH'])
except Exception:
    pass

logger = logging.getLogger("monitor_agent")
logger.setLevel(_log_level)
handler = logging.FileHandler(_log_path)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
