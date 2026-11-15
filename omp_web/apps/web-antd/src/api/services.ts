import { requestClient } from '#/api/request';

export namespace ServiceApi {
  /** 服务实例列表项（cpu/mem 与监控/日志 URL 由后端动态注入，可能为 null） */
  export interface ServiceRecord {
    alert_count: string;
    app_name: string;
    /** 0-基础组件 1-应用服务 */
    app_type: number;
    app_version: string;
    cluster_type: string;
    cpu_status?: 'critical' | 'normal' | 'warning' | null;
    cpu_usage?: null | number;
    env: string;
    id: number;
    ip: string;
    is_base_env: boolean;
    is_web: boolean;
    label_name: string;
    log_url?: null | string;
    mem_status?: 'critical' | 'normal' | 'warning' | null;
    mem_usage?: null | number;
    monitor_url?: null | string;
    operable: boolean;
    port: string;
    service_instance_name: string;
    service_status: string;
  }

  /** 服务详情（含安装信息与操作历史） */
  export interface ServiceDetail {
    app_name: string;
    app_version: string;
    cluster_type: string;
    created: string;
    history: {
      created: string;
      description: string;
      result: string;
      username: string;
    }[];
    id: number;
    install_info: {
      base_dir: string;
      data_dir: string;
      log_dir: string;
      password: string;
      service_port: string;
      username: string;
    };
    ip: string;
    label_name: string;
    service_instance_name: string;
  }

  /** 服务操作提交体：1-启动 2-停止 3-重启 4-删除（删除） */
  export interface ActionPayload {
    action: number;
    /** 同时卸载服务（仅删除操作生效） */
    del_file: boolean | null;
    id: number;
    operation_user: string;
  }

  /** 删除依赖校验提交体（后端仅消费 id；action/operation_user 照旧契约携带） */
  export interface DeleteMsgPayload {
    action: string;
    id: number;
    operation_user: string;
  }

  /** 列表查询参数（ip/实例名称模糊匹配，label_name 模糊、app_type 精确） */
  export interface ListParams {
    app_type?: null | number | string;
    ip?: null | string;
    label_name?: null | string;
    ordering?: null | string;
    page: number;
    service_instance_name?: null | string;
    size: number;
  }

  /** 安装记录项（install_step_status: 0 等待 1 进行中 2 成功 3 失败） */
  export interface InstallLog {
    install_step_status: null | number;
    log: string;
  }

  // ── 服务纳管（旧 GetService 页 + GetServiceModal，路径 /api/services/appList|appConfCheck） ──

  /** 可纳管应用项：单体服务 version 为多版本数组；产品项带 child 按版本分组的服务列表 */
  export interface ManagedAppItem {
    child?: Record<string, { name: string; version: string }[]>;
    name: string;
    version: string[];
  }

  /** 纳管选择校验响应：服务树（逐项可带 error）+ 可选主机（ip → agent 目录） */
  export interface ManagedAppCheckResult {
    ips: Record<string, string>;
    is_continue: boolean;
    service: (ManagedAppItem & { error?: string })[];
  }

  /** 纳管扫描响应行（ser_info） */
  export interface ConfCheckItem {
    error?: string;
    exist_instance: string[];
    ip: string[];
    is_use_exist: boolean;
    name: string;
  }

  /** 纳管扫描响应（无 uuid 分支） */
  export interface ConfCheckResult {
    is_continue: boolean;
    ser_info: ConfCheckItem[];
    uuid: string;
  }

  /** 纳管执行响应（带 uuid 分支） */
  export interface ManageServiceResult {
    is_error: boolean;
    message: string;
  }
}

/** 服务实例列表（DRF 分页 {count, results}） */
export function listServices(params: ServiceApi.ListParams) {
  return requestClient.get<{
    count: number;
    results: ServiceApi.ServiceRecord[];
  }>('/api/services/services/', { params });
}

/** 服务详情（安装信息 + 操作历史） */
export function getServiceDetail(id: number) {
  return requestClient.get<ServiceApi.ServiceDetail>(
    `/api/services/services/${id}/`,
  );
}

/**
 * 服务操作下发（启动/停止/重启/删除）。
 * Salt 异步任务：接口成功仅代表任务下发，状态流转经列表轮询体现。
 */
export function submitServiceAction(data: ServiceApi.ActionPayload[]) {
  return requestClient.post('/api/services/action/', { data });
}

/** 删除依赖校验，data 为 "标题:项1,项2" 或 "无依赖信息" 纯文本 */
export function queryServiceDeleteMsg(data: ServiceApi.DeleteMsgPayload[]) {
  return requestClient.post<string>('/api/services/delete/', { data });
}

/** 单服务安装记录（含实时日志） */
export function getServiceInstallLog(id: number) {
  return requestClient.get<ServiceApi.InstallLog[]>(
    '/api/appStore/serviceInstallHistoryDetail/',
    { params: { id } },
  );
}

/** 功能模块（标签）列表，用于列筛选下拉 */
export function getServiceLabels() {
  return requestClient.get<string[]>('/api/appStore/labels/');
}

// ── 服务纳管 ────────────────────────────────────────────────────────

/** 可纳管应用列表（产品项 child 按版本分组；排除 hadoop/doim，按 BASIC_ORDER 排序） */
export function queryManagedAppList() {
  return requestClient.get<ServiceApi.ManagedAppItem[]>('/api/services/appList/');
}

/**
 * 纳管选择校验（版本重复/依赖缺失检查）：通过时返回服务树 + 可选主机，
 * 逐项携带默认安装参数；失败项以 error 字段标注（is_continue=false）。
 */
export function checkManagedAppList(data: ServiceApi.ManagedAppItem[]) {
  return requestClient.post<ServiceApi.ManagedAppCheckResult>(
    '/api/services/appList/',
    { data },
  );
}

/**
 * 纳管扫描（appConfCheck 无 uuid 分支）：对所选主机逐服务校验目录/用户/端口，
 * 返回扫描结果行（exist_instance 非空时 is_use_exist=true 可关联已有集群）。
 */
export function scanManagedServices(data: {
  ips: Record<string, string>;
  is_continue: boolean;
  service: Record<string, any>[];
}) {
  return requestClient.post<ServiceApi.ConfCheckResult>(
    '/api/services/appConfCheck/',
    { data },
  );
}

/** 纳管执行（appConfCheck 带 uuid 分支）：is_error=true 时 message 为失败原因 */
export function executeManagedServices(data: {
  ser_info: Record<string, any>[];
  uuid: string;
}) {
  return requestClient.post<ServiceApi.ManageServiceResult>(
    '/api/services/appConfCheck/',
    { data },
  );
}
