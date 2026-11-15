import { requestClient } from '#/api/request';

export namespace AlarmLogApi {
  /** 告警记录列表项 */
  export interface AlertRecord {
    alert_describe?: null | string;
    alert_host_ip?: null | string;
    alert_instance_name?: null | string;
    alert_level?: null | string;
    alert_time?: null | string;
    alert_type?: null | string;
    create_time?: null | string;
    id: number;
    is_read: number;
    monitor_log?: null | string;
    monitor_path?: null | string;
  }

  /** 列表查询参数 */
  export interface ListAlertParams {
    alert_host_ip?: null | string;
    alert_instance_name?: null | string;
    alert_level?: null | string;
    alert_type?: null | string;
    end_alert_time?: null | string;
    ordering?: null | string;
    page: number;
    size: number;
    start_alert_time?: null | string;
  }
}

/** 告警记录列表（DRF 分页 {count, results}） */
export function listAlert(params: AlarmLogApi.ListAlertParams) {
  return requestClient.get<{ count: number; results: AlarmLogApi.AlertRecord[] }>(
    '/api/promemonitor/listAlert/',
    { params },
  );
}

/** 告警记录批量标记已读 */
export function updateAlertRead(ids: number[]) {
  return requestClient.post('/api/promemonitor/updateAlert/', {
    ids,
    is_read: 1,
  });
}
