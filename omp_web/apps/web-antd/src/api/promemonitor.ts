import { requestClient } from '#/api/request';

export namespace PromemonitorApi {
  /** 监控平台地址配置（后端 MonitorUrl） */
  export interface MonitorUrlItem {
    id: number;
    monitor_url: null | string;
    name: string;
  }

  /** 告警推送通道配置（后端 AlertSendWaySetting，当前仅 email 通道） */
  export interface AlertPushSetting {
    server_url: null | string;
    used: boolean;
  }

  /** 邮件 SMTP 全局配置（后端 EmailSMTPSetting.get_dict） */
  export interface EmailSmtpConfig {
    host: null | string;
    password: null | string;
    port: null | number;
    username: null | string;
  }

  /** 全局维护模式记录（后端 Maintain，存在记录即处于维护模式） */
  export interface MaintainRecord {
    id: number;
    matcher_name: string;
    matcher_value: string;
  }

}

/** 查询监控平台地址配置列表 */
export function queryMonitorUrls() {
  return requestClient.get<PromemonitorApi.MonitorUrlItem[]>(
    '/api/promemonitor/monitorurl/',
  );
}

/**
 * 批量更新监控平台地址配置。
 * 后端为 PATCH @action，RequestClient 未封装 patch，走通用 request。
 */
export function updateMonitorUrls(items: {id: number; monitor_url: string}[]) {
  return requestClient.request<PromemonitorApi.MonitorUrlItem[]>(
    '/api/promemonitor/monitorurl/multiple_update/',
    { data: { data: items }, method: 'PATCH' },
  );
}

/** 查询告警邮件推送配置（data.email 为邮件通道） */
export function queryAlertPushSetting() {
  return requestClient.get<{ email: PromemonitorApi.AlertPushSetting }>(
    '/api/promemonitor/getSendAlertSetting/',
  );
}

/** 更新告警邮件推送配置（way_name 固定 email，env_id 取当前环境上下文） */
export function updateAlertPushSetting(params: {
  /** 当前环境 id（取环境上下文） */
  env_id: number;
  server_url: string;
  used: boolean;
  way_name: string;
}) {
  return requestClient.post('/api/promemonitor/updateSendAlertSetting/', params);
}

/** 查询邮件 SMTP 全局配置（未配置时 data 为空对象） */
export function queryEmailSmtpConfig() {
  return requestClient.get<PromemonitorApi.EmailSmtpConfig>(
    '/api/promemonitor/getSendEmailConfig/',
  );
}

/** 更新邮件 SMTP 全局配置 */
export function updateEmailSmtpConfig(params: {
  host: string;
  password: string;
  port: number;
  username: string;
}) {
  return requestClient.post('/api/promemonitor/updateSendEmailConfig/', params);
}

/** 查询全局维护模式状态（data 非空数组即维护中） */
export function queryMaintainState() {
  return requestClient.get<PromemonitorApi.MaintainRecord[]>(
    '/api/promemonitor/globalMaintain/',
  );
}

/**
 * 进入/退出全局维护模式。
 * 服务端按「是否存在维护记录」自动翻转，无需传目标状态。
 */
export function toggleMaintainMode() {
  return requestClient.post('/api/promemonitor/globalMaintain/', {
    matcher_name: 'env',
    matcher_value: 'default',
  });
}
