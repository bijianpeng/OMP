import { requestClient } from '#/api/request';

export namespace DataBackupApi {
  /** 备份记录项 */
  export interface BackupRecord {
    /** 备份任务名称 */
    backup_name: string;
    /** 备份实例 */
    content?: string;
    create_time?: string;
    /** 过期时间 */
    expire_time?: null | string;
    /** 备份文件是否已被删除 */
    file_deleted?: boolean;
    /** 备份文件名 */
    file_name?: string;
    /** 备份文件大小（MB） */
    file_size?: string;
    id: number;
    /** 备份返回信息 */
    message?: string;
    /** 远端备份路径 */
    remote_path?: null | string;
    /** 备份结果：0 失败 / 1 成功 / 2 执行中 */
    result: number;
    /** 文件保存路径 */
    retain_path?: null | string;
  }

  /** 列表查询参数 */
  export interface ListBackupParams {
    ordering?: null | string;
    page: number;
    size: number;
  }

  /** 备份自定义参数（后端 BackupCustom） */
  export interface BackupCustomParam {
    field_k: string;
    field_v: string;
    id: number;
    notes?: null | string;
  }

  /** 备份策略（后端 BackupSetting） */
  export interface BackupSetting {
    /** 关联的自定义参数 */
    backup_custom: BackupCustomParam[];
    /** 备份实例名称列表 */
    backup_instances: string[];
    /** 定时任务详情（celery crontab 字段） */
    crontab_detail: {
      day_of_month: string;
      day_of_week: string;
      hour: string;
      minute: string;
      month_of_year: string;
    };
    id: number;
    /** 是否开启定时备份 */
    is_on: boolean;
    /** 文件保留天数，-1 表示永久保留 */
    retain_day: number;
    /** 备份文件保存路径 */
    retain_path: string;
  }

  /** 策略创建/更新请求体（与旧前端 makeRequestBody 契约一致） */
  export interface StrategyPayload {
    backup_custom: { field_k: string; id: number; field_v: string }[];
    backup_instances: string[];
    crontab_detail: {
      day_of_month: string;
      day_of_week: string;
      hour: string;
      minute: string;
      month_of_year: string;
    };
    is_on: boolean;
    retain_day: number;
    retain_path: string;
  }
}

/** 备份记录列表（DRF 分页 {count, results}） */
export function queryBackupHistory(params: DataBackupApi.ListBackupParams) {
  return requestClient.get<{
    count: number;
    results: DataBackupApi.BackupRecord[];
  }>('/api/backups/backupHistory/', { params });
}

/**
 * 删除备份记录（支持批量）。
 * 部分文件不存在时后端返回 {code: 0, message: '删除xx可能已不存在！'}，
 * 全部成功时 data 为字符串。
 */
export function deleteBackupHistory(ids: number[]) {
  return requestClient.post<unknown>('/api/backups/backupHistory/', { ids });
}

// ── 备份策略 ──────────────────────────────────────────────────

/** 备份策略列表（后端不分页，返回全量数组） */
export function queryBackupSettings() {
  return requestClient.get<DataBackupApi.BackupSetting[]>(
    '/api/backups/backupSettings/',
  );
}

/** 添加备份策略 */
export function createBackupStrategy(payload: DataBackupApi.StrategyPayload) {
  return requestClient.post<unknown>('/api/backups/backupSettings/', payload);
}

/** 修改备份策略 */
export function updateBackupStrategy(
  id: number,
  payload: DataBackupApi.StrategyPayload,
) {
  return requestClient.put<unknown>(
    `/api/backups/backupSettings/${id}/`,
    payload,
  );
}

/** 删除备份策略 */
export function deleteBackupStrategy(id: number) {
  return requestClient.delete<unknown>(`/api/backups/backupSettings/${id}/`);
}

/**
 * 立即执行备份策略。
 * 后端 BackupSettingView.create 以「请求体仅含 id」区分执行与创建。
 */
export function executeBackupStrategy(id: number) {
  return requestClient.post<unknown>('/api/backups/backupSettings/', { id });
}

// ── 备份自定义参数 ────────────────────────────────────────────

/** 自定义参数列表（后端不分页，返回全量数组） */
export function queryBackupCustom() {
  return requestClient.get<DataBackupApi.BackupCustomParam[]>(
    '/api/backups/backupCustom/',
  );
}

/** 添加自定义参数 */
export function createBackupCustom(
  payload: { field_k: string; field_v: string; notes?: string },
) {
  return requestClient.post<unknown>('/api/backups/backupCustom/', payload);
}

/** 修改自定义参数 */
export function updateBackupCustom(
  id: number,
  payload: { field_k: string; field_v: string; notes?: string },
) {
  return requestClient.put<unknown>(`/api/backups/backupCustom/${id}/`, payload);
}

/** 删除自定义参数 */
export function deleteBackupCustom(id: number) {
  return requestClient.delete<unknown>(`/api/backups/backupCustom/${id}/`);
}

/**
 * 查询自定义参数被哪些备份实例使用（用于删除/修改前的二次确认文案）。
 * 后端返回 [{name}]，name 为去重后的实例名逗号串，无关联时为空串。
 */
export async function queryBackupRepeatCustom(id: number) {
  const list = await requestClient.get<{ name: string }[]>(
    '/api/backups/backupRepeatCustom/',
    { params: { id } },
  );
  return list[0]?.name ?? '';
}

// ── 可备份实例 ────────────────────────────────────────────────

/** 可备份实例名称列表（状态正常的可备份服务实例） */
export function queryCanBackupInstances() {
  return requestClient.get<string[]>('/api/backups/canBackupInstances/');
}
