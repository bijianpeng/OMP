import type { Recordable, UserInfo } from '@vben/types';

import { ref } from 'vue';
import { useRouter } from 'vue-router';

import { LOGIN_PATH } from '@vben/constants';
import { preferences } from '@vben/preferences';
import { resetAllStores, useAccessStore, useUserStore } from '@vben/stores';

import { message, notification } from 'ant-design-vue';
import { defineStore } from 'pinia';

import { getAccessCodesApi, getUserInfoApi, loginApi, logoutApi } from '#/api';
import { $t } from '#/locales';

import { isEnvContextRejected, useEnvStore } from './env';

export const useAuthStore = defineStore('auth', () => {
  const accessStore = useAccessStore();
  const userStore = useUserStore();
  const router = useRouter();

  const loginLoading = ref(false);

  // OMP 无 /me 接口，fetchUserInfo 需要用户名过滤用户列表。
  // userStore 不持久化，刷新后从 localStorage 恢复（登出时清除）
  const USERNAME_KEY = `${import.meta.env.VITE_APP_NAMESPACE}-omp-username`;

  function rememberUsername(username: string) {
    localStorage.setItem(USERNAME_KEY, username);
  }

  function restoreUsername(): string {
    return localStorage.getItem(USERNAME_KEY) ?? '';
  }

  /**
   * 异步处理登录操作
   * Asynchronously handle the login process
   * @param params 登录表单数据
   */
  async function authLogin(
    params: Recordable<any>,
    onSuccess?: () => Promise<void> | void,
  ) {
    // 异步处理用户登录操作并获取 accessToken
    let userInfo: null | UserInfo = null;
    try {
      loginLoading.value = true;
      // OMP 登录返回 {token, user}；JWT 会话在 cookie，
      // token 同时存入 accessStore 以维持 vben 登录态状态机
      const loginResult = await loginApi(params);

      if (loginResult?.token) {
        accessStore.setAccessToken(loginResult.token);
        // OMP 登录响应仅 {token}（JWT 默认 payload），
        // 用户名取登录表单值，供 fetchUserInfo 过滤用户列表
        const username = String(params.username ?? '');
        if (!username) {
          throw new Error('登录表单缺少用户名');
        }
        rememberUsername(username);

        // 获取用户信息并存储到 accessStore 中。
        // 失败时清掉已写入的 token/用户名并中止登录，避免残留半登录态：
        // token 残留会让路由守卫误判已登录，登录页/空白页反复横跳
        let accessCodes: string[] = [];
        try {
          const [fetchUserInfoResult, codes] = await Promise.all([
            fetchUserInfo(),
            getAccessCodesApi(),
          ]);
          userInfo = fetchUserInfoResult;
          accessCodes = codes;
        } catch {
          accessStore.setAccessToken(null);
          localStorage.removeItem(USERNAME_KEY);
          message.error('获取用户信息失败，请重新登录');
          return { userInfo: null };
        }

        userStore.setUserInfo(userInfo);
        accessStore.setAccessCodes(accessCodes);

        // 多环境：初始化环境上下文。useEnvStore 必须在 rememberUsername 之后
        // 首次调用（persist key 按当时 localStorage 用户名求值，见 store/env.ts）。
        // 列表拉取失败按无环境处理（错误提示由请求层统一弹出）。
        const envStore = useEnvStore();
        try {
          await envStore.fetchEnvList();
        } catch {
          // envList 保持为空，走无环境分支
        }
        envStore.ensureValid();

        if (accessStore.loginExpired) {
          accessStore.setLoginExpired(false);
        } else if (envStore.envList.length === 0) {
          // 当前账号未授权任何环境：进提示页而非首页（首页所有请求都依赖环境上下文）
          await router.push('/no-env');
        } else {
          onSuccess
            ? await onSuccess?.()
            : await router.push(
                userInfo.homePath || preferences.app.defaultHomePath,
              );
        }

        if (userInfo?.realName) {
          notification.success({
            description: `${$t('authentication.loginSuccessDesc')}:${userInfo?.realName}`,
            duration: 3,
            message: $t('authentication.loginSuccess'),
          });
        }
      }
    } finally {
      loginLoading.value = false;
    }

    return {
      userInfo,
    };
  }

  async function logout(redirect: boolean = true) {
    try {
      await logoutApi();
    } catch {
      // 不做任何处理
    }
    resetAllStores();
    accessStore.setLoginExpired(false);
    localStorage.removeItem(USERNAME_KEY);
    // 与旧前端一致：主动清除 jwtToken cookie（后端无登出接口）
    document.cookie = 'jwtToken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';

    // 已经在登录页时不能再带 redirect：此时 currentRoute.fullPath 就是登录页本身，
    // 再编码一层会得到「登录页?redirect=编码后的登录页」，下一次又在这个基础上再包一层，
    // 反复登出会让 URL 逐跳变长，且没有上限。
    // On the login page the current route is the login page itself, so carrying it as
    // `redirect` would nest one more encoded layer on every repeat.
    const currentRoute = router.currentRoute.value;
    const alreadyOnLogin = currentRoute.path === LOGIN_PATH;

    // 回登录页带上当前路由地址
    await router.replace({
      path: LOGIN_PATH,
      query:
        redirect && !alreadyOnLogin
          ? { redirect: encodeURIComponent(currentRoute.fullPath) }
          : {},
    });
  }

  async function fetchUserInfo() {
    const username = restoreUsername();
    if (!username) {
      throw new Error('登录用户名缺失，请重新登录');
    }
    try {
      const userInfo = await getUserInfoApi(username);
      userStore.setUserInfo(userInfo);
      return userInfo;
    } catch (error) {
      // 防死锁：持久化的环境选择已失效（环境被删除/授权被回收）时，本请求
      // 携带的 X-Env-Id 会被 403 拒绝（硬刷新后路由守卫的首次请求即命中），
      // 清空选择后无头重试一次，避免应用锁死在失效环境上全量 403 白屏；
      // 后续由 env-switcher 的 onMounted 回落并整页刷新
      const envStore = useEnvStore();
      if (!isEnvContextRejected(error) || envStore.currentEnvId === null) {
        throw error;
      }
      envStore.currentEnvId = null;
      const userInfo = await getUserInfoApi(username);
      userStore.setUserInfo(userInfo);
      return userInfo;
    }
  }

  function $reset() {
    loginLoading.value = false;
  }

  return {
    $reset,
    authLogin,
    fetchUserInfo,
    loginLoading,
    logout,
  };
});
