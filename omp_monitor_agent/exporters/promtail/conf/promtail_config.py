# coding=utf-8
import json
import os
import socket
import sys

if len(sys.argv) != 6:
    print('参数个数须为6，请重新传入！')
    quit()

promtail_file = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), 'promtail.yml')
targets_json_file = os.path.join(os.path.dirname(
    os.path.abspath(__file__)), 'targets.json')
root_logs_dir = sys.argv[1]  # 产品日志路径
listen_port = sys.argv[2]  # promtail监听端口
loki_ip = sys.argv[3]  # loki的 ip
loki_port = sys.argv[4]  # loki的端口
install_dir = sys.argv[5]  # promtail 安装路径
loki_api_url = 'http://{}:{}/loki/api/v1/push'.format(loki_ip, loki_port)
instance = socket.gethostbyname(socket.gethostname())
promtail_config = '''# promtail config
server:
  grpc_listen_port: 0
  http_listen_port: {}
clients:
- url: {}
positions:
  filename: {}/promtail/conf/positions.yml
scrape_configs:
- job_name: cloudwise
  file_sd_configs:
  - files:
    - {}/promtail/conf/targets.json
'''.format(listen_port, loki_api_url, install_dir, install_dir)

file_sd_configs_list = list()
dirs = os.listdir(root_logs_dir)

for ele in dirs:
    abs_path = os.path.join(root_logs_dir, ele)
    if os.path.isfile(abs_path):
        continue
    temp_dict = dict()
    temp_dict.update(
        {'targets': ['localhost'], 'labels': {'job': ele,
                                              '__path__': abs_path + '/*.log', 'instance': instance}}
    )
    file_sd_configs_list.append(temp_dict)
with open(promtail_file, 'w') as f:
    f.write(promtail_config)
with open(targets_json_file, 'w') as f2:
    json.dump(file_sd_configs_list, f2, sort_keys=True, indent=2,
              separators=(',', ':'), ensure_ascii=False)
