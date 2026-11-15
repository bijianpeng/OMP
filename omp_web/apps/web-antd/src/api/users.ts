import { requestClient } from '#/api/request';

export namespace UsersApi {
  /** 用户记录（后端 UserProfile 列表序列化） */
  export interface UserRecord {
    /** 创建时间 */
    date_joined?: null | string;
    /** 邮箱 */
    email?: null | string;
    /**
     * 可访问环境 id 列表（UserEnv 行全量；superuser 不落 UserEnv 行，为空数组）
     */
    envs?: null | number[];
    /** 可访问环境名称列表（与 envs 同序） */
    env_names?: null | string[];
    id: number;
    is_active?: boolean;
    is_superuser?: boolean;
    username: string;
  }

  /** 列表查询参数 */
  export interface ListUsersParams {
    ordering?: null | string;
    page: number;
    size: number;
    /** 用户名过滤（icontains 模糊匹配） */
    username?: null | string;
  }

  /** 创建用户提交体（密码明文提交，后端 make_password 入库） */
  export interface CreateUserPayload {
    email: string;
    /** 可访问环境 id 列表（全量覆盖式；创建默认提交 default 环境） */
    envs: number[];
    password: string;
    re_password: string;
    username: string;
  }

  /** 编辑用户提交体（PATCH 局部更新，不修改密码） */
  export interface UpdateUserPayload {
    email?: string;
    /** 可访问环境 id 列表（全量覆盖式更新 UserEnv） */
    envs?: number[];
  }
}

/** 用户列表（DRF 分页 {count, results}） */
export function queryUsers(params: UsersApi.ListUsersParams) {
  return requestClient.get<{
    count: number;
    results: UsersApi.UserRecord[];
  }>('/api/users/users/', { params });
}

/**
 * 修改用户密码。
 * 三个字段均需 RSA 公钥加密（后端按 344 位密文长度校验），
 * 调用方先用 utils/rsa 的 rsaEncrypt 加密再传入。
 */
export function updateUserPassword(payload: {
  new_password: string;
  old_password: string;
  username: string;
}) {
  return requestClient.post<unknown>('/api/users/updatePassword/', payload);
}

/** 创建用户（含可访问环境授权，后端全量覆盖式写入 UserEnv） */
export function createUser(payload: UsersApi.CreateUserPayload) {
  return requestClient.post<unknown>('/api/users/users/', payload);
}

/**
 * 编辑用户（局部更新邮箱 / 可访问环境授权）。
 * RequestClient 未封装 patch，走通用 request。
 */
export function updateUser(id: number, payload: UsersApi.UpdateUserPayload) {
  return requestClient.request<unknown>(`/api/users/users/${id}/`, {
    data: payload,
    method: 'PATCH',
  });
}
