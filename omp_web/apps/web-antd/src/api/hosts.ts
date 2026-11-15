import { requestClient } from '#/api/request';

/** 主机 IP 列表（筛选下拉，多页面共享） */
export function getIpList() {
  return requestClient.get<string[]>('/api/hosts/ips/');
}

export namespace HostApi {
  /** 主机列表项（使用率与监控 URL 由后端动态注入，可能为 null） */
  export interface HostRecord {
    alert_num: null | number;
    cpu: null | number;
    cpu_status?: 'critical' | 'normal' | 'warning' | null;
    cpu_usage?: null | number;
    created: string;
    data_disk_status?: 'critical' | 'normal' | 'warning' | null;
    data_disk_usage?: null | number;
    data_folder: string;
    disk: null | Record<string, number>;
    /** 0 正常 1 重启中 2 启动失败 3 部署中 4 部署失败 */
    host_agent: null | number;
    host_name: string;
    /** 密码（base64 编码，后端解密后编码返回） */
    password: string;
    id: number;
    /** 0 未执行 1 成功 2 执行中 3 失败 */
    init_status: null | number;
    ip: string;
    is_maintenance: boolean;
    mem_status?: 'critical' | 'normal' | 'warning' | null;
    mem_usage?: null | number;
    monitor_agent: null | number;
    log_url?: null | string;
    /** 内存（G，详情/列表均返回） */
    memory: null | number;
    monitor_url?: null | string;
    /** 时间同步服务器 */
    ntpd_server?: null | string;
    operate_system: string;
    port: number;
    root_disk_status?: 'critical' | 'normal' | 'warning' | null;
    root_disk_usage?: null | number;
    service_num: null | number;
    instance_name: string;
    /** 是否安装时间同步服务 */
    use_ntpd?: boolean;
    username: string;
  }

  /** 主机详情（历史记录 + 基础环境部署信息） */
  export interface HostDetail {
    created: string;
    deployment_information: {
      service__app_logo: string;
      service__app_name: string;
      service__app_version: string;
    }[];
    disk: null | Record<string, number>;
    history: {
      created: string;
      description: string;
      id: number;
      result: string;
      username: string;
    }[];
    id: number;
    init_status: number;
    instance_name: string;
    ip: string;
    is_maintenance: boolean;
    port: number;
    username: string;
  }

  /** 主机创建/更新载荷（ip/port 沿用旧前端提交形态：port 转字符串） */
  export interface HostFormPayload {
    data_folder: string;
    /** 是否安装时间同步服务 */
    use_ntpd: boolean;
    instance_name: string;
    ip: string;
    /** 时间同步服务器（use_ntpd 开启时必传） */
    ntpd_server?: string;
    operate_system: string;
    password: string;
    port: string;
    username: string;
  }

  /** 字段重复性校验载荷（更新态带 id 排除自身） */
  export interface HostCheckPayload {
    id?: number;
    instance_name?: string;
    ip?: string;
  }

  /** 批量导入校验/创建载荷（row 仅校验场景携带，标记 xlsx 行号） */
  export interface BatchHostItem {
    data_folder: string;
    instance_name: string;
    ip: string;
    ntpd_server?: string;
    operate_system: string;
    password: string;
    port: number | string;
    row?: number;
    use_ntpd: boolean;
    username: string;
  }

  /** 批量校验响应：error 非空时行级失败原因已标注 */
  export interface BatchValidateResult {
    correct: BatchHostItem[];
    error: Record<string, any>[];
  }
}

/** 主机列表（DRF 分页 {count, results}；ip 模糊匹配） */
export function listHosts(params: {
  ip?: null | string;
  ordering?: null | string;
  page: number;
  size: number;
}) {
  return requestClient.get<{ count: number; results: HostApi.HostRecord[] }>(
    '/api/hosts/hosts/',
    { params },
  );
}

/** 创建主机 */
export function createHost(data: HostApi.HostFormPayload) {
  return requestClient.post('/api/hosts/hosts/', data);
}

/** 更新主机（RequestClient 未封装 patch，走通用 request） */
export function updateHost(id: number, data: HostApi.HostFormPayload) {
  return requestClient.request(`/api/hosts/hosts/${id}/`, {
    data,
    method: 'PATCH',
  });
}

/** 主机详情（历史记录 + 基础环境部署信息） */
export function getHostDetail(id: number) {
  return requestClient.get<HostApi.HostDetail>(`/api/hosts/hostsDetail/${id}`);
}

/**
 * 实例名称/IP 重复性校验，data 为布尔（true 可用）。
 * 已存在时后端返回 code=1，requestClient 直接抛错并全局提示。
 */
export function checkHost(data: HostApi.HostCheckPayload) {
  return requestClient.post<boolean>('/api/hosts/fields/', data);
}

/** 以下均为 Salt 异步任务接口：成功仅代表任务下发 */

/** 重启主机 Agent */
export function restartHostAgent(hostIds: number[]) {
  return requestClient.post('/api/hosts/restartHostAgent/', {
    host_ids: hostIds,
  });
}

/** 重启监控 Agent（旧前端挂在 promemonitor 模块） */
export function restartMonitorAgent(hostIds: number[]) {
  return requestClient.post('/api/promemonitor/restartMonitorAgent/', {
    host_ids: hostIds,
  });
}

/** 重装主机 Agent */
export function reinstallHostAgent(hostIds: number[]) {
  return requestClient.post('/api/hosts/hostReinstall/', {
    host_ids: hostIds,
  });
}

/** 重装监控 Agent */
export function reinstallMonitorAgent(hostIds: number[]) {
  return requestClient.post('/api/hosts/monitorReinstall/', {
    host_ids: hostIds,
  });
}

/** 主机进入/退出维护模式 */
export function changeHostMaintain(
  isMaintenance: boolean,
  hostIds: number[],
) {
  return requestClient.post('/api/hosts/maintain/', {
    host_ids: hostIds,
    is_maintenance: isMaintenance,
  });
}

/** 删除主机 */
export function deleteHosts(hostIds: number[]) {
  return requestClient.post('/api/hosts/hostUninstall/', {
    host_ids: hostIds,
  });
}

/** 初始化主机（旧前端 UI 已下线入口，接口保留） */
export function initHosts(hostIds: number[]) {
  return requestClient.post('/api/hosts/hostInit/', { host_ids: hostIds });
}

/** 批量导入：行级校验 */
export function batchValidateHosts(hostList: HostApi.BatchHostItem[]) {
  return requestClient.post<HostApi.BatchValidateResult>(
    '/api/hosts/batchValidate/',
    { host_list: hostList },
  );
}

/** 批量导入：创建主机 */
export function batchImportHosts(hostList: HostApi.BatchHostItem[]) {
  return requestClient.post('/api/hosts/batchImport/', { host_list: hostList });
}
