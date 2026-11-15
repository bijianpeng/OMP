import { requestClient } from '#/api/request';

export namespace InspectionApi {
  /** 巡检记录列表项（后端 InspectionHistory，序列化 fields=__all__） */
  export interface HistoryRecord {
    duration: null | number;
    end_time?: null | string;
    env: null | number;
    /** 执行方式：man-手动 auto-定时 */
    execute_type: string;
    hosts?: null | string[];
    id: number;
    inspection_name: string;
    inspection_operator: string;
    /** 巡检结果：1-进行中 2-成功 3-失败（0 为初始默认） */
    inspection_status: number;
    /** 报告类型：service-组件巡检 host-主机巡检 deep-深度分析 */
    inspection_type: string;
    /** 推送结果：1-成功 2-发送中 0-失败 3-未发送 */
    send_email_result: number;
    services?: null | number[];
    start_time: null | string;
  }

  /** 列表查询参数（InspectionHistoryFilter + ordering） */
  export interface ListHistoryParams {
    execute_type?: null | string;
    inspection_name?: null | string;
    inspection_status?: null | number;
    inspection_type?: null | string;
    ordering?: null | string;
    page: number;
    size: number;
  }

  /** 巡检组件下拉项（/api/inspection/services/） */
  export interface ServiceOption {
    service__app_name: string;
    service__id: number;
  }

  /** 巡检报告基础信息项（明细行 basic 数组元素） */
  export interface ReportBasicItem {
    name: string;
    name_cn: string;
    value: unknown;
  }

  /** 风险指标行（后端聚合 Prometheus 告警） */
  export interface ReportRiskRow {
    host_ip: string;
    resolve_info: string;
    risk_describe: string;
    risk_level: string;
    service_name?: string;
    service_port?: null | number | string;
    system?: string;
  }

  /** 服务平面图节点（仅深度巡检生成） */
  export interface ReportTopologyItem {
    host_ip: string;
    service_list: string[];
  }

  /** 巡检报告明细行（detail_dict.host/component/service/database） */
  export interface ReportDetailRow {
    basic: ReportBasicItem[];
    cpu_usage?: string;
    disk_usage_data?: string;
    disk_usage_root?: string;
    host_ip?: string;
    host_massage?: string;
    id: number;
    log_level?: string;
    mem_usage?: string;
    release_version?: string;
    run_time?: null | number | string;
    service_name?: string;
    service_port?: null | number | string;
    service_status?: null | number | string;
    sys_load?: string;
    /** 巡检特有数组字段：port_connectivity / memory_top / cpu_top / kernel_parameters / topic_partition / kafka_offsets / topic_size */
    [key: string]: unknown;
  }

  /** 巡检报告详情（后端 joint_json_data 组装，仅成功状态的报告生成） */
  export interface ReportDetail {
    detail_dict: {
      component?: ReportDetailRow[];
      database?: ReportDetailRow[];
      host?: ReportDetailRow[];
      service?: ReportDetailRow[];
    };
    file_name: string;
    risks: { host_list: ReportRiskRow[]; service_list: ReportRiskRow[] };
    service_topology?: ReportTopologyItem[];
    summary: {
      scan_info: { host?: number; service?: number };
      scan_result: { abnormal_target?: number; all_target_num?: number };
      task_info: { operator: string; task_name: string; task_status: number };
      time_info: { cost: null | number; end_time: string; start_time: string };
    };
  }

  /** 任务下发参数（deep-深度分析 host-主机巡检 service-组件巡检） */
  export interface TaskDistributionParams {
    /** 当前环境 id（取环境上下文） */
    env: number;
    execute_type: string;
    hosts?: string[];
    inspection_name: string;
    inspection_operator: null | string;
    inspection_status: string;
    inspection_type: string;
    services?: number[];
  }
}

/** 巡检记录列表（DRF 分页 {count, results}；start_time 为后端序列化后动态排序） */
export function listInspectionHistory(params: InspectionApi.ListHistoryParams) {
  return requestClient.get<{
    count: number;
    results: InspectionApi.HistoryRecord[];
  }>('/api/inspection/history/', { params });
}

/** 巡检任务下发（深度分析/主机巡检/组件巡检共用 POST） */
export function distributeInspectionTask(
  data: InspectionApi.TaskDistributionParams,
) {
  return requestClient.post('/api/inspection/history/', data);
}

/** 巡检报告详情（导出时取 file_name） */
export function getInspectionReport(id: number) {
  return requestClient.get<{ file_name?: null | string }>(
    `/api/inspection/report/${id}/`,
  );
}

/**
 * 巡检报告详情（summary/risks/service_topology/detail_dict/file_name，
 * 后端 joint_json_data 组装）。
 * 报告缺失时后端 data 为提示文案字符串（HTTP 200）。
 */
export function getInspectionReportDetail(id: null | number | string) {
  return requestClient.get<InspectionApi.ReportDetail | string>(
    `/api/inspection/report/${id}/`,
  );
}

/** 巡检组件列表（组件巡检勾选项，仅安装成功组件） */
export function listInspectionServices() {
  return requestClient.get<InspectionApi.ServiceOption[]>(
    '/api/inspection/services/',
  );
}

/** 查询巡检报告默认收件人配置 */
export function getPushEmailSetting() {
  return requestClient.get<{ send_email?: boolean; to_users?: null | string }>(
    '/api/inspection/inspectionSendEmailSetting/',
  );
}

/** 推送巡检报告邮件 */
export function pushInspectionEmail(data: {
  id: number;
  module: string;
  to_users: string;
}) {
  return requestClient.post('/api/inspection/inspectionSendEmail/', data);
}
