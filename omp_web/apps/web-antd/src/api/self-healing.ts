import { requestClient } from '#/api/request';

export namespace SelfHealingApi {
  /** 自愈记录项 */
  export interface SelfHealingRecord {
    /** 故障描述 */
    alert_content?: null | string;
    /** 故障时间 */
    alert_time?: null | string;
    /** 结束时间 */
    end_time?: null | string;
    /** 已运行自愈次数 */
    healing_count?: number;
    /** 自愈日志 */
    healing_log?: null | string;
    /** 主机 IP */
    host_ip?: null | string;
    id: number;
    /** 实例名称 */
    instance_name?: null | string;
    /** 是否已读：0 未读 / 1 已读 */
    is_read: number;
    /** Grafana 日志面板 URL */
    monitor_log?: null | string;
    /** 自愈状态：0 失败 / 1 成功 / 2 自愈中 */
    state?: number;
  }

  /** 列表查询参数 */
  export interface ListSelfHealingParams {
    /** 故障时间范围结束（YYYY-MM-DD HH:mm:ss） */
    query_end_time?: null | string;
    /** 故障时间范围开始（YYYY-MM-DD HH:mm:ss） */
    query_start_time?: null | string;
    host_ip?: null | string;
    instance_name?: null | string;
    ordering?: null | string;
    page: number;
    size: number;
    state?: null | string;
  }
}

/** 自愈记录列表（DRF 分页 {count, results}） */
export function listSelfHealingHistory(
  params: SelfHealingApi.ListSelfHealingParams,
) {
  return requestClient.get<{
    count: number;
    results: SelfHealingApi.SelfHealingRecord[];
  }>('/api/services/ListSelfHealingHistory/', { params });
}

/** 自愈记录批量标记已读 */
export function updateSelfHealingHistoryRead(ids: number[]) {
  return requestClient.post('/api/services/UpdateSelfHealingHistory/', {
    ids,
    is_read: 1,
  });
}
