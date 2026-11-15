import { requestClient } from '#/api/request';

export namespace OperationRecordApi {
  /** 登录日志 */
  export interface LoginLogRecord {
    id: number;
    ip?: null | string;
    login_time?: null | string;
    role?: null | string;
    username?: null | string;
  }

  /** 系统操作日志（后端 OperateLog 模型） */
  export interface SystemLogRecord {
    create_time?: null | string;
    description?: null | string;
    id: number;
    request_ip?: null | string;
    request_method?: null | string;
    request_result?: null | string;
    request_url?: null | string;
    response_code?: null | number;
    username?: null | string;
  }
}

/** 登录日志列表 */
export function queryLoginLog(params: {
  ordering?: null | string;
  page: number;
  size: number;
  username?: null | string;
}) {
  return requestClient.get<{
    count: number;
    results: OperationRecordApi.LoginLogRecord[];
  }>('/api/users/UserLoginLog/', { params });
}

/** 系统操作日志列表 */
export function querySystemLog(params: {
  ordering?: null | string;
  page: number;
  size: number;
  username?: null | string;
}) {
  return requestClient.get<{
    count: number;
    results: OperationRecordApi.SystemLogRecord[];
  }>('/api/users/operateLog/', { params });
}
