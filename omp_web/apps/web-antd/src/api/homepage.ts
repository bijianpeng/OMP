import { requestClient } from '#/api/request';

export namespace HomepageApi {
  /**
   * 仪表盘状态块条目（instrumentPanel 各 *_info_list 项）。
   * severity：critical / warning / normal，其余视同未监控
   */
  export interface InstrumentItem {
    alertname?: null | string;
    /** 告警描述 */
    describe?: null | string;
    /** 告警时间 */
    date?: null | string;
    /** 实例名称（主机块可能为空，以 ip 为主键） */
    instance_name?: null | string;
    /** 主机 IP */
    ip?: null | string;
    /** Grafana 日志面板 URL */
    log_url?: null | string;
    /** Grafana 监控面板 URL */
    monitor_url?: null | string;
    severity?: null | string;
  }

  /** 单一维度（服务/组件/数据库/主机）的统计与明细 */
  export interface InstrumentSection {
    [key: string]: unknown;
    database_info_all_count?: number;
    database_info_exc_count?: number;
    database_info_list?: InstrumentItem[];
    database_info_no_monitor_count?: number;
    component_info_all_count?: number;
    component_info_exc_count?: number;
    component_info_list?: InstrumentItem[];
    component_info_no_monitor_count?: number;
    host_info_all_count?: number;
    host_info_exc_count?: number;
    host_info_list?: InstrumentItem[];
    host_info_no_monitor_count?: number;
    service_info_all_count?: number;
    service_info_exc_count?: number;
    service_info_list?: InstrumentItem[];
    service_info_no_monitor_count?: number;
  }

  /** GET /api/promemonitor/instrumentPanel/ 响应 data */
  export interface InstrumentPanel {
    component?: InstrumentSection;
    database?: InstrumentSection;
    host?: InstrumentSection;
    /** 三方组件（后端返回但旧前端未启用） */
    third?: InstrumentSection;
    service?: InstrumentSection;
  }
}

/** 查询仪表盘状态概览（各维度计数 + 异常明细列表） */
export function getInstrumentPanel() {
  return requestClient.get<HomepageApi.InstrumentPanel>(
    '/api/promemonitor/instrumentPanel/',
  );
}
