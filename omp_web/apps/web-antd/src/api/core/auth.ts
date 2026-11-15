import { rsaEncrypt } from '#/utils/rsa';

import { requestClient } from '#/api/request';

export namespace AuthApi {
  /** 登录接口参数（username/password 为 RSA 密文） */
  export interface LoginParams {
    code?: string;
    password?: string;
    remember?: boolean;
    username?: string;
  }

  /** OMP 登录返回 {token}（JWT 默认 payload），JWT 同时写入 cookie */
  export interface LoginResult {
    token: string;
  }

  /** OMP 用户记录（GET /api/users/users/ 列表项） */
  export interface OmpUserRecord {
    id?: number;
    role?: null | string;
    username: string;
  }
}

/**
 * 构造 OMP 登录请求体：username/password RSA 加密，remember 原样传递
 */
export function buildLoginParams(
  username: string,
  password: string,
  remember: boolean,
): AuthApi.LoginParams {
  return {
    username: rsaEncrypt(username),
    password: rsaEncrypt(password),
    remember,
  };
}

/**
 * 登录（OMP：POST /api/login/）— 明文入参，内部 RSA 加密；
 * 响应 data 字段为 {token, user}，JWT 同时由后端写入 cookie
 */
export async function loginApi(params: {
  password: string;
  username: string;
}) {
  const body = buildLoginParams(
    params.username,
    params.password,
    (params as { remember?: boolean }).remember ?? false,
  );
  return requestClient.post<AuthApi.LoginResult>('/api/login/', body);
}

/**
 * 从用户列表中精确匹配当前登录用户。
 * 后端 ?username= 是 icontains 模糊匹配且按 id 排序，
 * 用户名互为包含时（如 admin2 先建、admin 后建）首条不一定是本人，必须精确比对。
 */
export function pickCurrentUser(
  results: AuthApi.OmpUserRecord[],
  username: string,
): AuthApi.OmpUserRecord | undefined {
  return results.find((r) => r.username === username);
}

/**
 * 获取当前用户信息（OMP 无 /me 接口，用用户列表按用户名过滤）。
 * 返回映射为 vben UserInfo 的对象。
 */
export async function getUserInfoApi(username: string) {
  const page = await requestClient.get<{
    count: number;
    results: AuthApi.OmpUserRecord[];
  }>('/api/users/users/', { params: { username } });
  const record = pickCurrentUser(page.results ?? [], username);
  if (!record) {
    throw new Error(`当前用户 ${username} 信息获取失败`);
  }
  return {
    realName: record.username,
    roles: record.role ? [record.role] : [],
    userId: `${record.id ?? record.username}`,
    username: record.username,
  };
}

/**
 * 退出登录（OMP 后端无登出接口，JWT cookie 由浏览器清除）
 */
export async function logoutApi() {
  return Promise.resolve(null);
}

/**
 * 获取用户权限码（OMP 后端无此接口，返回空）
 */
export async function getAccessCodesApi() {
  return [] as string[];
}
