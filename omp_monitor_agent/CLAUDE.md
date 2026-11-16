# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is an **OMP Monitor Agent** deployment package — a monitoring agent that runs on managed hosts, collects service metrics via Prometheus exporters, and exposes them through an HTTP API. The core application is a PyInstaller-packed Python 3.8 binary (`monitor_agent_exporter`). Source Python code is embedded inside the binary, not present as `.py` files on disk.

Three PyInstaller binaries are present:
- `monitor_agent_exporter` — main monitoring agent (Sanic web server)
- `install` — installation helper
- `manage` — management helper

## Running the Agent

```bash
bash monitor_agent.sh start    # Start agent (runs monitor_agent_exporter in background)
bash monitor_agent.sh stop     # Stop agent (kill -9)
bash monitor_agent.sh restart  # Restart
bash monitor_agent.sh status   # Check running status
bash monitor_agent.sh alive    # Auto-restart if dead
bash monitor_agent.sh init     # Register crontab watchdog (every 5 min)
```

Config is at `conf/config.yaml` (port defaults to 19031, host 0.0.0.0). On first start, `monitor_agent.sh` replaces `${PROJECT_PATH}` in the config with the actual directory path.

## Architecture (reconstructed from binary)

The binary contains this Python module layout:

```
main.py              → Starts Sanic app on 0.0.0.0:PORT, imports lib.webapp + lib.views
lib/
  webapp.py          → create_app() + Scheduler singleton
  views.py           → All HTTP route handlers (Sanic blueprints)
  scheduler.py       → uvloop-based async job scheduler in a daemon thread
  job.py             → GetMonitorInfo (metric collection), ServiceInstallerJob, ServiceDeleteJob
  boot.py            → Services class — generates exporter configs and starts/stops them
  utils.py           → Token auth decorator, JSON helpers, process lookup, Prometheus formatting
  constants.py       → TOKEN, service name lists, file paths, process-to-service mappings
scripts/
  __init__.py
  core.py            → Shared utilities (run_cmd, format_desc) for custom scripts
  host_check.py      → Host-level inspection metrics (CPU top 10, memory, disk, firewall, etc.)
  inspection_common.py → PublicQuote base class for service inspection scripts
  redis_check.py     → Redis-specific inspection (role, slaves, cluster)
  test.py            → Example custom script (CustomMetrics class)
```

### Data Flow

1. Central OMP server calls `POST /update/service_info` with full service config → saved to `conf/service_info.json`, loaded into `app.config["services"]`
2. Central server calls `GET /metrics/monitor/<service>` → agent creates `GetMonitorInfo` job → probes TCP port, queries exporter HTTP endpoint, collects process stats via psutil → returns Prometheus text format
3. For services with exporters, agent generates config files in `exporters/<service>Exporter/conf/` and manages the exporter process via shell scripts
4. Custom scripts in `scripts/` are dynamically imported via `importlib.import_module("scripts.<name>")`

### Request Auth

All API endpoints are protected by `@authorized` decorator which checks the `CWAccessToken` header against the hardcoded TOKEN in constants.py.

## Exporter Directory Structure

Each exporter follows this pattern under `exporters/<service>Exporter/`:

```
sbin/<binary>                  → Pre-compiled Go/Java exporter binary
scripts/<service>Exporter      → Bash wrapper (start/stop/status subcommands)
conf/<service>.conf            → Config template (filled by boot.py)
```

Active exporters on disk: beanstalkd, clickhouse, elasticsearch, httpd, kafka, mysql, node, postgreSql, promtail, redis, rocketmq, tengine, zookeeper.

Exporter port assignments are in `conf/promemonitor_port.ini`. Each bash wrapper uses a PID file in `pid/` and logs to `log/`.

## Key Configuration Files

| File | Purpose |
|------|---------|
| `conf/config.yaml` | Agent host, port, log level, credentials |
| `conf/service_info.json` | Runtime service definitions (port, exporter port, credentials, process keywords) |
| `conf/scripts_info.json` | Custom monitoring script registry |
| `conf/promemonitor_port.ini` | Exporter name → port mapping |

## Supported Services

**With exporters**: mysql, redis, kafka, zookeeper, clickhouse, postgreSql, elasticsearch, httpd, ignite, arangodb, beanstalkd, tengine, node, rocketmq

**Process-only monitoring**: nacos, flink, gotty, grafana, ntpd, prometheus, minio, pushgateway, mongodb, xxlJob, victoriaMetrics, namenode, secondarynamenode, datanode, resourcemanager, nodemanager, zkfc, journalnode

**DOIM proprietary**: ProcessWatcher, TaskDispatcherManager, bluesky, CenterControlUnit, WebExpress, MxAgent, mxagentrun, pyweb, ProxyWebExpress

The process-to-service name mapping (for PID lookup) is defined in `lib/utils.py` via `get_pid_by_name()` — it matches on process cmdline patterns (e.g. `kafka.Kafka` → `kafka`, `mongod` → `mongodb`).

## Custom Script System

Scripts in `scripts/` follow the convention: a class `CustomMetrics` with static methods named `get_<metric_name>()`, each returning a dict with keys `help`, `type`, `metric`, `value`, `labels`. Added/removed at runtime via the `/update/custom_scripts/add` and `/update/custom_scripts/delete` API endpoints.

## Promtail Integration

The agent manages Promtail (log collector) config at `exporters/promtail/conf/promtail.yml` (YAML, loki URL, scrape configs) and `exporters/promtail/conf/targets.json` (file discovery targets). Updated via `/update/promtail/add` and `/update/promtail/json` endpoints.

## Reverse Engineering Notes

The binary is PyInstaller-packed (Python 3.8, ~20MB). To extract embedded code:
- Magic cookie `MEI\x0c\x0b\x0a\x0b\x0e` marks the archive (near EOF)
- TOC contains entries for scripts (type `s`), modules (type `m`), binaries (type `b`), and the PYZ archive (type `z`)
- Application modules in PYZ are zlib-compressed marshalled Python 3.8 code objects
- System Python is 3.7 so `marshal.loads()` fails on 3.8 format — string extraction from raw decompressed data works as an alternative
- Extracted artifacts are saved in `extracted/` for reference

---

## 入库备注（2026-11-16 P0）

- 本目录源自 omp 主机 `/root/project/omp_monitor_agent/`（二进制逆向重建），已剥离全部二进制；`install`/`manage` 原二进制随安装包沿用（源码逆向未完成）。
- 出厂内置凭据：`conf/config.yaml` 的 `USERNAME/PASSWORD`（mokey）与服务端 `omp_server/utils/plugin/monitor_agent.py:149` 硬编码成对，属平台出厂值，P2 现代化时统一配置化（服务端 TODO 亦然）。
- `conf/service_info.json` 已模板化（清除真实环境哈希）；exporter conf 中口令为模板默认值，运行时由 boot.py 以服务端下发值覆盖。
- 第三方 exporter 二进制不入本目录，版本与 sha256 见 `scripts/build/manifest.yaml`（exporters 段），构建时下载组装。
