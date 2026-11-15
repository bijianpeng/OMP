import { requestClient } from '#/api/request';

export namespace EnvApi {
  /** 环境记录（GET /api/env/ 列表项，含资源统计 annotate） */
  export interface EnvRecord {
    /** 环境编码（slug；监控链路规则/targets 文件名使用，创建后不可改） */
    code: string;
    /** 创建时间 */
    created: string;
    /** 描述 */
    description: string;
    /** 主机数（统计） */
    host_count: number;
    /** 环境 id */
    id: number;
    /** 环境名称 */
    name: string;
    /** 服务数（统计） */
    service_count: number;
  }

  /** 创建环境提交体（superuser） */
  export interface EnvCreatePayload {
    /** 配置来源环境 id；null/不传表示空白创建 */
    config_source?: null | number;
    /** 环境编码（slug，后端正则校验） */
    code: string;
    /** 描述 */
    description?: string;
    /** 环境名称 */
    name: string;
  }

  /** 编辑环境提交体（code 不可改，后端 read_only） */
  export interface EnvUpdatePayload {
    /** 描述 */
    description?: string;
    /** 环境名称 */
    name: string;
  }

  /** 环境-用户授权读写体（全量覆盖式） */
  export interface EnvUsersPayload {
    user_ids: number[];
  }
}

/** 环境列表（当前用户可见环境；superuser 全量。无分页契约） */
export function listEnvs() {
  return requestClient.get<EnvApi.EnvRecord[]>('/api/env/');
}

/** 创建环境（superuser） */
export function createEnv(payload: EnvApi.EnvCreatePayload) {
  return requestClient.post('/api/env/', payload);
}

/** 编辑环境名称/描述（RequestClient 未封装 patch，走通用 request） */
export function updateEnv(id: number, payload: EnvApi.EnvUpdatePayload) {
  return requestClient.request(`/api/env/${id}/`, {
    data: payload,
    method: 'PATCH',
  });
}

/** 删除环境（默认环境 id=1 与有资源/有进行中任务的环境由后端拒绝） */
export function deleteEnv(id: number) {
  return requestClient.delete(`/api/env/${id}/`);
}

/** 环境已授权用户 id 列表（superuser） */
export function listEnvUsers(id: number) {
  return requestClient.get<EnvApi.EnvUsersPayload>(`/api/env/${id}/users/`);
}

/** 全量覆盖环境授权用户（superuser；RequestClient 未封装 patch，走通用 request） */
export function updateEnvUsers(id: number, userIds: number[]) {
  return requestClient.request(`/api/env/${id}/users/`, {
    data: { user_ids: userIds } satisfies EnvApi.EnvUsersPayload,
    method: 'PATCH',
  });
}
