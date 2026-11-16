# OMP v1.3.0 构建下载源策略

> 依据：2026-11-16 于 omp 服务器（麒麟 V10）实测连通性，均为直连可用。
> P2 构建 fetch 实现按本文件首选列配置；备选列仅在首选失效时启用，启用后回填实测日期。

## 源清单

| 组件类 | 首选源（实测可用） | 备选源（未实测） |
|---|---|---|
| Go 系二进制：Prometheus / Alertmanager / Loki / 第三方 exporter / Tengine | `https://github.com/<org>/<repo>/releases/`（直连 302/200，2026-11-16） | `https://ghproxy.net/https://github.com/...` |
| Python 源码（component/env 基础） | `https://www.python.org/ftp/python/`（200） | `https://mirrors.huaweicloud.com/python/` |
| PyPI 包（env 内 pip 依赖、salt 等） | `https://mirrors.aliyun.com/pypi/simple`（200，`-i` 指定） | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| MySQL 8.4.x（glibc2.28 tarball） | `https://cdn.mysql.com/Downloads/MySQL-8.4/mysql-<ver>-linux-glibc2.28-x86_64.tar.xz`（8.4.0 实测 200） | `https://mirrors.aliyun.com/mysql/Downloads/...` |
| Redis 源码 | `https://download.redis.io/releases/`（200） | `https://github.com/redis/redis/releases` |
| Grafana | `https://dl.grafana.com/oss/release/grafana-<ver>.linux-amd64.tar.gz`（11.0.0 实测 200） | `https://mirrors.aliyun.com/grafana/` |

## 探测备忘

- `cdn.mysql.com` 与 `dl.grafana.com` 的目录 URL 返回 404（索引禁用），必须探测**具体文件路径**；版本号不存在时同样 404，P2 锁版本时以具体文件 200 为准。
- GitHub `releases/latest` 为 302 跳转（正常）；下载 asset 时跟随重定向即可。
- pypi.org 官方源在构建机不可达（000），一律走阿里镜像。

## 校验要求

P2 fetch 对每个工件记录 `sha256` 至 `manifest.yaml`（`scripts/build/manifest.yaml`），下载后校验不一致即失败；本表 URL 模板同步登记在 manifest 对应条目的 `source` 字段。
