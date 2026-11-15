/**
 * 该文件可自行根据业务逻辑进行调整
 */
import type { RequestClientOptions } from '@vben/request';

import { useAppConfig } from '@vben/hooks';
import { preferences } from '@vben/preferences';
import {
  authenticateResponseInterceptor,
  defaultResponseInterceptor,
  errorMessageResponseInterceptor,
  RequestClient,
} from '@vben/request';
import { useAccessStore } from '@vben/stores';

import { message } from 'ant-design-vue';

import { getRequestEnvId, useAuthStore } from '#/store';

import { isOmpUnauthorized } from './omp-response';

const { apiURL } = useAppConfig(import.meta.env, import.meta.env.PROD);

function createRequestClient(baseURL: string, options?: RequestClientOptions) {
  const client = new RequestClient({
    ...options,
    // OMP JWT 会话在 cookie，跨源请求必须携带
    withCredentials: true,
    baseURL,
    // 对齐旧前端 150s 超时（安装编排等长请求）
    timeout: 150_000,
  });

  /**
   * 重新认证逻辑
   */
  async function doReAuthenticate() {
    console.warn('Access token or refresh token is invalid or expired. ');
    const accessStore = useAccessStore();
    const authStore = useAuthStore();
    accessStore.setAccessToken(null);
    if (
      preferences.app.loginExpiredMode === 'modal' &&
      accessStore.isAccessChecked
    ) {
      accessStore.setLoginExpired(true);
    } else {
      await authStore.logout();
    }
  }

  /**
   * 刷新token逻辑（OMP 无 refresh token，恒走重新认证）
   */
  async function doRefreshToken() {
    return '';
  }

  function formatToken(token: null | string) {
    return token ? `Bearer ${token}` : null;
  }

  // 请求头处理
  client.addRequestInterceptor({
    fulfilled: async (config) => {
      // OMP 认证走 jwtToken cookie：不加 Authorization 头。
      // 后端 djangorestframework-jwt 仅识别 "JWT <token>" 前缀，
      // 发 "Bearer <token>" 反而触发认证失败（未认证）
      config.headers['Accept-Language'] = preferences.app.locale;
      // 多环境上下文：登录后的业务请求携带 X-Env-Id，后端按环境隔离数据。
      // getRequestEnvId 惰性实例化 env store（登录前不实例化，避免 persist
      // key 固化为空用户名共用 key，见 store/env.ts）；currentEnvId 为 null
      // （未登录/未选定环境）时不注入
      const envId = getRequestEnvId();
      if (envId !== null) {
        config.headers['X-Env-Id'] = String(envId);
      }
      return config;
    },
  });

  // OMP 未认证响应：HTTP 200 + {code:1, message:'未认证'}，需识别并登出。
  // 必须挂在 defaultResponseInterceptor 之前（它会把 code!==0 抛成普通错误）
  client.addResponseInterceptor({
    fulfilled: async (response) => {
      if (isOmpUnauthorized(response.data)) {
        await doReAuthenticate();
      }
      return response;
    },
  });

  // 处理返回的响应数据格式
  client.addResponseInterceptor(
    defaultResponseInterceptor({
      codeField: 'code',
      dataField: 'data',
      successCode: 0,
    }),
  );

  // token过期的处理
  client.addResponseInterceptor(
    authenticateResponseInterceptor({
      client,
      doReAuthenticate,
      doRefreshToken,
      enableRefreshToken: preferences.app.enableRefreshToken,
      formatToken,
    }),
  );

  // 通用的错误处理,如果没有进入上面的错误处理逻辑，就会进入这里
  client.addResponseInterceptor(
    errorMessageResponseInterceptor((msg: string, error) => {
      // 这里可以根据业务进行定制,你可以拿到 error 内的信息进行定制化处理，根据不同的 code 做不同的提示，而不是直接使用 message.error 提示 msg
      // 当前mock接口返回的错误字段是 error 或者 message
      const responseData = error?.response?.data ?? {};
      const errorMessage = responseData?.error ?? responseData?.message ?? '';
      // 如果没有错误信息，则会根据状态码进行提示
      message.error(errorMessage || msg);
    }),
  );

  return client;
}

export const requestClient = createRequestClient(apiURL, {
  responseReturn: 'data',
});

export const baseRequestClient = new RequestClient({
  baseURL: apiURL,
  // 与 requestClient 一致：下载等同源场景也需携带 JWT cookie
  withCredentials: true,
});
