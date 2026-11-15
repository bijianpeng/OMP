import { requestClient } from '#/api/request';

export namespace ExecutionRecordApi {
  /** 执行记录列表项（后端 ExecutionRecord + ExecutionRecordSerializer） */
  export interface ExecutionRecord {
    /** 开始时间（TimeStampMixin.created） */
    created: null | string;
    can_rollback: boolean;
    count: number;
    duration: string;
    end_time?: null | string;
    id: number;
    /** 记录类型：MainInstallHistory-安装 UpgradeHistory-升级 RollbackHistory-回滚 */
    module: string;
    /** 关联记录标识：安装为 operation_uuid，升级/回滚为对应 History.id */
    module_id: string;
    operator: string;
    /** 状态机值（StateChoices），展示文案用 state_display */
    state: string;
    state_display: string;
  }

  /** 可回滚服务实例（UpgradeDetail 序列化，树形 children 的叶子节点） */
  export interface RollbackChoice {
    after_rollback_v: string;
    app_name: string;
    before_rollback_v: string;
    id: number;
    instance_name: string;
    ip: string;
    service_id: number;
  }

  /** 可回滚服务分组项（按应用名聚合，children 为各主机实例） */
  export interface RollbackChoiceGroup {
    app_name: string;
    children: RollbackChoice[];
  }

  /** 可升目标安装包（应用中心发布记录摘要） */
  export interface UpgradeTarget {
    app_id: number;
    app_name: string;
    app_version: string;
  }

  /** 可升级服务实例（children 叶子；can_upgrade 仅含最高可升版本） */
  export interface UpgradeChoice {
    app_id: number;
    /** 可升目标（后端为单元素数组，仅最高版本） */
    can_upgrade: UpgradeTarget[];
    instance_name: string;
    ip: string;
    service_id: number;
    version: string;
  }

  /** 可升级服务分组项（父级 can_upgrade 为对象，前端展示时包成数组） */
  export interface UpgradeChoiceGroup {
    app_name: string;
    can_upgrade: UpgradeTarget;
    children: UpgradeChoice[];
  }

  // ── 升级/回滚进度页（history 详情，5s 轮询） ────────────────────────

  /** 升级进度明细行（UpgradeDetailSerializer，首组为「升级前置操作」id=0） */
  export interface UpgradeDetailItem {
    id: number;
    instance_name: string;
    ip: string;
    message: null | string;
    service_name: string;
    state_display: string;
    /** 0 等待 1 进行中 2 成功 3 失败（展示色同安装进度契约） */
    upgrade_state: number;
  }

  /** 升级进度分组项（后端按 BASIC_ORDER 服务顺序排序，首组为前置操作） */
  export interface UpgradeDetailGroup {
    service_name: string;
    upgrade_details: UpgradeDetailItem[];
  }

  /** 升级历史详情（GET/PUT /api/upgrade/history/<id>） */
  export interface UpgradeHistoryDetail {
    all_count: number;
    can_rollback: boolean;
    created: null | string;
    id: number;
    operator: string;
    success_count: number;
    upgrade_detail: UpgradeDetailGroup[];
    /** 0 等待 1 进行中 2 成功 3 失败 4 正在注册（0/1/4 时前端 5s 轮询） */
    upgrade_state: number;
  }

  /** 回滚进度明细行（RollbackDetailSerializer） */
  export interface RollbackDetailItem {
    id: number;
    instance_name: string;
    ip: string;
    message: null | string;
    rollback_state: number;
    service_name: string;
    state_display: string;
  }

  /** 回滚进度分组项 */
  export interface RollbackDetailGroup {
    rollback_details: RollbackDetailItem[];
    service_name: string;
  }

  /** 回滚历史详情（GET/PUT /api/rollback/history/<id>） */
  export interface RollbackHistoryDetail {
    all_count: number;
    created: null | string;
    id: number;
    operator: string;
    rollback_detail: RollbackDetailGroup[];
    /** 0 等待 1 进行中 2 成功 3 失败 4 正在注册（0/1/4 时前端 5s 轮询） */
    rollback_state: number;
    success_count: number;
  }
}

/** 执行记录列表（module 走 search 模糊过滤，ordering 仅支持 created） */
export function listExecutionRecords(params: {
  ordering?: null | string;
  page: number;
  search?: null | string;
  size: number;
}) {
  return requestClient.get<{
    count: number;
    results: ExecutionRecordApi.ExecutionRecord[];
  }>('/api/appStore/executionRecord/', { params });
}

/** 可回滚服务列表（history_id 限定某次升级记录，search 按应用名过滤；非分页） */
export function listCanRollback(params: {
  history_id: null | number | string;
  search?: null | string;
}) {
  return requestClient.get<{
    results: ExecutionRecordApi.RollbackChoiceGroup[];
  }>('/api/rollback/can-rollback', { params });
}

/** 执行服务回滚，返回新建的回滚历史 id */
export function doRollback(choices: number[]) {
  return requestClient.post<{ history: number }>('/api/rollback/do-rollback', {
    choices,
  });
}

/** 可升级服务列表（search 按应用名过滤；仅展示最高可升版本；非分页） */
export function listCanUpgrade(params: { search?: null | string }) {
  return requestClient.get<{
    results: ExecutionRecordApi.UpgradeChoiceGroup[];
  }>('/api/upgrade/can-upgrade', { params });
}

/** 执行服务升级，返回新建的升级历史 id */
export function doUpgrade(choices: { app_id: number; service_id: number }[]) {
  return requestClient.post<{ history: number }>('/api/upgrade/do-upgrade', {
    choices,
  });
}

/** 升级进度详情（upgrade_state 0/1/4 时前端 5s 轮询） */
export function queryUpgradeHistory(id: null | number | string) {
  return requestClient.get<ExecutionRecordApi.UpgradeHistoryDetail>(
    `/api/upgrade/history/${id}`,
  );
}

/** 升级重试（仅失败记录可重试，成功后重新轮询） */
export function retryUpgrade(id: null | number | string) {
  return requestClient.request(`/api/upgrade/history/${id}`, {
    method: 'PUT',
  });
}

/** 回滚进度详情（rollback_state 0/1/4 时前端 5s 轮询） */
export function queryRollbackHistory(id: null | number | string) {
  return requestClient.get<ExecutionRecordApi.RollbackHistoryDetail>(
    `/api/rollback/history/${id}`,
  );
}

/** 回滚重试（仅失败记录可重试，成功后重新轮询） */
export function retryRollback(id: null | number | string) {
  return requestClient.request(`/api/rollback/history/${id}`, {
    method: 'PUT',
  });
}
