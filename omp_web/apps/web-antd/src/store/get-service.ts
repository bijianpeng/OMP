import type { ServiceApi } from '#/api/services';

import { shallowRef } from 'vue';

import { defineStore } from 'pinia';

/**
 * 服务纳管流程跨页状态（旧 react-router location.state.getServiceData 契约迁移）。
 *
 * 交接契约（对齐旧实现 GetServiceModal → GetService 页的 state 交接）：
 * 应用商店「服务纳管」选择弹窗在确认选择后调用 `setServiceData(data)` 写入
 * appList 校验返回的纳管初始数据（服务树 + 可选主机 + is_continue），
 * 再跳转 `/application_management/get-service`（Step1 消费，本 store 只读）。
 * 纳管页离开（返回/完成）时调用 `$reset` 清空，避免残留旧流程数据。
 */
export const useGetServiceStore = defineStore('getService', () => {
  /** 纳管初始数据（GET/POST appList 校验产出） */
  const serviceData = shallowRef<null | ServiceApi.ManagedAppCheckResult>(null);

  /** 写入纳管流程上下文（入口弹窗交接专用） */
  function setServiceData(data: ServiceApi.ManagedAppCheckResult): void {
    serviceData.value = data;
  }

  /** 离开流程时清空 */
  function $reset() {
    serviceData.value = null;
  }

  return { $reset, serviceData, setServiceData };
});
