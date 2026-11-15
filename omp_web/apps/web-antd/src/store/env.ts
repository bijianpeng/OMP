import type { EnvApi } from '#/api/env';

import { computed, ref } from 'vue';

import { defineStore } from 'pinia';

import { listEnvs } from '#/api/env';

/**
 * 登录用户名 localStorage key。
 * 与 store/auth.ts 的 USERNAME_KEY 为同一约定（authStore 登录成功时写入、
 * 登出时清除），用于校验持久化环境选择的归属，避免换账号串环境。
 */
const USERNAME_KEY = `${import.meta.env.VITE_APP_NAMESPACE}-omp-username`;

function readUsername(): string {
  return localStorage.getItem(USERNAME_KEY) ?? '';
}

/**
 * EnvContextMiddleware 拒绝环境上下文时的响应体 message（HTTP 403）：
 * 环境标识不存在 / 当前用户无该环境授权。命中即说明 currentEnvId 已失效。
 */
const ENV_CONTEXT_REJECTED_MESSAGES = ['环境不存在', '无该环境访问权限'];

/** 判断请求错误是否为「环境上下文被拒」（用于失效选择的自我愈合） */
export function isEnvContextRejected(
  error: unknown,
): boolean {
  const response = (error as null | { response?: { data?: unknown; status?: number } })
    ?.response;
  if (!response || response.status !== 403) {
    return false;
  }
  const message = (response.data as null | { message?: unknown })?.message;
  return (
    typeof message === 'string' &&
    ENV_CONTEXT_REJECTED_MESSAGES.includes(message)
  );
}

/**
 * 多环境上下文 store。
 *
 * 登录成功后由 authStore.authLogin 调用 fetchEnvList + ensureValid 初始化；
 * envList 不持久化（刷新后由首个消费者重新拉取）。
 *
 * 换账号串环境防护（spec §7.2）：pinia-plugin-persistedstate 的 storage key
 * 在 store 首次实例化时求值后固定——同会话内 A 登出、B 登录（SPA 导航非硬重载）
 * 时 store 不重建，B 的写入仍落在 A 的 key 下。因此除 key 外，持久化值本身
 * 携带归属标记 persistedUsername：fetchEnvList 与 hydrate 后（afterHydrate）
 * 都会校验，标记与当前用户名不符（换账号 / 他人残留）即丢弃 currentEnvId，
 * 由 ensureValid 走正常回落，A 的选择不会被 B 污染。
 */
export const useEnvStore = defineStore(
  'omp-env',
  () => {
    /** 当前用户可见环境列表（superuser 全量；登录后拉取） */
    const envList = ref<EnvApi.EnvRecord[]>([]);

    /** 当前环境 id（null 表示尚未选定，如未登录或列表为空） */
    const currentEnvId = ref<null | number>(null);

    /** currentEnvId 写入时的归属用户名（与 currentEnvId 一同持久化，仅作串环境防护） */
    const persistedUsername = ref('');

    /** 当前环境记录（列表未加载或 id 失效时为 undefined） */
    const currentEnv = computed(() =>
      envList.value.find((env) => env.id === currentEnvId.value),
    );

    /**
     * 校验持久化选择的归属：persistedUsername 与当前登录用户名不符时
     * 丢弃 currentEnvId（置 null，后续 ensureValid 回落第一项），
     * 并把归属标记刷新为当前用户名。调用点：fetchEnvList 开头（每次登录
     * 必经，覆盖同会话换账号——此时 store 已实例化、不会重新 hydrate）、
     * persist afterHydrate（store 创建即校验，早于任何消费者读取）。
     */
    function validateOwner(): void {
      const username = readUsername();
      if (persistedUsername.value !== username) {
        currentEnvId.value = null;
        persistedUsername.value = username;
      }
    }

    /**
     * 拉取当前用户可见环境列表。
     *
     * 防死锁：currentEnvId 指向的环境已失效（被删除/授权被回收）时，
     * 本请求携带的 X-Env-Id 会被 EnvContextMiddleware 403 拒绝，
     * 调用方永远拿不到列表、ensureValid 无从回落，整个应用会锁死在
     * 失效环境上（所有请求全量 403 白屏）。此处命中环境上下文 403 时
     * 清空选择后无头重试一次，保证列表可得并交由 ensureValid 回落。
     */
    async function fetchEnvList(): Promise<EnvApi.EnvRecord[]> {
      validateOwner();
      try {
        envList.value = await listEnvs();
      } catch (error) {
        if (!isEnvContextRejected(error) || currentEnvId.value === null) {
          throw error;
        }
        currentEnvId.value = null;
        envList.value = await listEnvs();
      }
      return envList.value;
    }

    /**
     * 切换当前环境。
     * @param id 目标环境 id，必须在当前列表内（未授权环境）才生效
     * @returns 是否切换成功
     */
    function setEnv(id: number): boolean {
      if (!envList.value.some((env) => env.id === id)) {
        return false;
      }
      currentEnvId.value = id;
      return true;
    }

    /**
     * 校正 currentEnvId：不在列表内（换账号串环境 / 环境被删除 / 授权被回收）
     * 时回落到第一项；列表为空时不改动（无环境场景由登录流程跳转提示页）。
     */
    function ensureValid(): void {
      if (envList.value.length === 0) {
        return;
      }
      if (!currentEnv.value) {
        currentEnvId.value = envList.value[0]!.id;
      }
    }

    /** 登出时由 resetAllStores 调用（同时触发 persist 写回空值） */
    function $reset() {
      envList.value = [];
      currentEnvId.value = null;
      persistedUsername.value = '';
    }

    return {
      $reset,
      currentEnv,
      currentEnvId,
      ensureValid,
      envList,
      fetchEnvList,
      persistedUsername,
      setEnv,
      validateOwner,
    };
  },
  {
    persist: {
      // storage key 在 store 首次实例化时求值一次：本 store 首次使用发生在
      // authLogin 的 rememberUsername 之后，key 即绑定当前登录用户。
      // 全局 createPersistedState（packages/stores/src/setup.ts）会在外层再拼
      // namespace 前缀，最终 storage key = `${namespace}-${username}-env`。
      // 注意：key 求值后固定，同会话换账号或登录前实例化（如请求拦截器）时
      // key 可能与当前用户不符——串环境由 persistedUsername 归属校验兜底。
      key: () => `${readUsername()}-env`,
      pick: ['currentEnvId', 'persistedUsername'],
      afterHydrate: ({ store }) => {
        // hydrate 后立即校验归属（store 创建即触发，早于任何消费者读取）
        (store as unknown as { validateOwner: () => void }).validateOwner();
      },
    },
  },
);

/**
 * 请求层注入 X-Env-Id 用：返回当前环境 id（未登录/未选定返回 null）。
 *
 * 惰性实例化守卫：loginApi 请求早于 authLogin 的 rememberUsername 执行，
 * 若请求拦截器在每次请求时无条件 useEnvStore()，登录请求本身就会在用户名
 * 写入 localStorage 之前首次实例化本 store，persist key 被固化为空用户名的
 * 共用 key——归属正确性由 persistedUsername 校验兜底，但按用户记忆环境的
 * 特性退化为「所有人共用一个 key、各自回落第一项」。故无用户名（未登录）
 * 时不实例化、直接返回 null——此时 currentEnvId 必为 null，与「不注入
 * header」语义一致；登录后的首个请求（fetchUserInfo 等）才首次实例化，
 * key 即绑定当次登录用户。
 */
export function getRequestEnvId(): null | number {
  if (!readUsername()) {
    return null;
  }
  return useEnvStore().currentEnvId;
}
