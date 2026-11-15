import { requestClient } from '#/api/request';

export namespace ExceptionListApi {
  /** 异常清单项 */
  export interface ExceptionRecord {
    /** 告警时间 */
    date?: null | string;
    /** 告警描述 */
    description?: null | string;
    /** 实例名称 */
    instance_name?: null | string;
    /** 主机 IP */
    ip?: null | string;
    /** Grafana 日志面板 URL */
    log_url?: null | string;
    /** 是否已读（0 未读；仪表盘内嵌清单用作未读徽标） */
    is_read?: number;
    /** Grafana 监控面板 URL */
    monitor_url?: null | string;
    /** 告警级别 critical / warning / info */
    severity?: null | string;
    /** 告警类型 host / service / component / database */
    type?: null | string;
  }

  /** 列表查询参数（后端按参数名对同名字段做包含匹配过滤） */
  export interface ListExceptionParams {
    /** 排序方向：'1' 升序 / '0' 降序（与 ordering 搭配，非 DRF 约定） */
    asc?: null | string;
    instance_name?: null | string;
    ip?: null | string;
    ordering?: null | string;
    severity?: null | string;
    /** 告警类型过滤（host/service/component/database，旧首页跳转透传） */
    type?: null | string;
  }
}

/**
 * 异常清单列表。
 * 注意：该接口为 Prometheus 实时聚合结果，非 DRF 分页，
 * 直接返回全量数组，由前端分页。
 */
export function getExceptionList(params: ExceptionListApi.ListExceptionParams) {
  return requestClient.get<ExceptionListApi.ExceptionRecord[]>(
    '/api/promemonitor/grafanaurl/',
    { params },
  );
}
