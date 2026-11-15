import type { InstallationApi } from '#/api/installation';

import { shallowRef } from 'vue';

import { defineStore } from 'pinia';

/**
 * 批量安装流程跨页状态（旧 redux installation + appStore.uniqueKey 契约迁移）。
 *
 * 交接契约（对齐旧实现 BatchInstallationModal → installation 页的 redux 交接）：
 * 应用商店「批量安装/组件安装」选择弹窗（批 K 维护）在确认选择后调用
 * `setInstallInfo(uniqueKey, data)` 写入入口返回的 unique_key 与
 * createInstallInfo/createComponentInstallInfo 产出的 Step1 基础数据，
 * 再跳转 `/application_management/app_store/installation`（不带 query，
 * 向导从 Step1 开始）；执行记录页等外部跳入则走
 * `installation?step=3&uniqueKey=` query 直落进度步，不经过本 store。
 */
export const useInstallationStore = defineStore('installation', () => {
  /** 本次安装流程唯一键（后端 Redis 流程追踪键） */
  const uniqueKey = shallowRef('');

  /** Step1 基础数据（产品/依赖树，由 createInstallInfo 产出） */
  const step1Data = shallowRef<InstallationApi.Step1Data>({
    basic: [],
    dependence: [],
    is_continue: false,
  });

  /**
   * 写入安装流程上下文（入口弹窗交接专用）。
   * @param key 入口返回的 unique_key（组件安装链路由 createComponentInstallInfo 生成）
   * @param data createInstallInfo / createComponentInstallInfo 响应 data
   */
  function setInstallInfo(
    key: string,
    data: InstallationApi.Step1Data,
  ): void {
    uniqueKey.value = key;
    step1Data.value = data;
  }

  /** Step1 校验失败后回写逐项 error_msg（旧 getStep1ChangeAction 契约） */
  function setStep1Data(data: InstallationApi.Step1Data): void {
    step1Data.value = data;
  }

  /** 离开流程时清空（取消安装后避免残留旧数据） */
  function $reset() {
    uniqueKey.value = '';
    step1Data.value = { basic: [], dependence: [], is_continue: false };
  }

  return {
    $reset,
    setInstallInfo,
    setStep1Data,
    step1Data,
    uniqueKey,
  };
});
