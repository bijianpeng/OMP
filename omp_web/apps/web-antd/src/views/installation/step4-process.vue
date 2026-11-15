<script lang="ts" setup>
import type { InstallationApi } from '#/api/installation';

import { computed, onUnmounted, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';

import { Button, Progress, Spin } from 'ant-design-vue';

import { getHostsAgentStatus, retryInstall } from '#/api/deployment-plan';
import {
  showInstallProcess,
  showSingleServiceInstallLog,
} from '#/api/installation';

import InstallInfoItem from './components/install-info-item.vue';

/**
 * Step4 开始安装：安装进度总览（按应用分组 + 右侧导航 + 总进度条），
 * 展开单服务查看安装日志。status 0/1/4（等待/安装中/注册中）时 5s 轮询。
 * status=0 需手动「开始」（轮询主机 agent 全部在线后下发安装），
 * status=3 可「重试」（retryInstall 重新下发）。
 */
defineOptions({ name: 'InstallationStep4Process' });

const props = defineProps<{
  /** 本次流程唯一键（query 直跳的安装记录 id 或入口交接键） */
  uniqueKey: string;
}>();

const router = useRouter();

/** 主状态文案（与后端 MainInstallHistory 枚举一致） */
const STATUS_TEXT: Record<number, string> = {
  0: '等待安装',
  1: '正在安装',
  2: '安装成功',
  3: '安装失败',
  4: '正在注册',
};

const loading = shallowRef(true);
const retryLoading = shallowRef(false);
/** 「开始」按钮 loading（等待 agent 就绪期间） */
const startLoading = shallowRef(false);

const process = shallowRef<InstallationApi.InstallProcess>();

/** 当前展开日志面板键：`${应用名}=${ip}` */
const openName = shallowRef('');
/** 展开面板的日志内容 */
const log = shallowRef('');

/** 进度轮询器（5s） */
let timer: null | ReturnType<typeof setTimeout> = null;
/** agent 就绪轮询器（1s，「开始」按钮等待期） */
let agentTimer: null | ReturnType<typeof setInterval> = null;

const detailGroups = computed(() => Object.entries(process.value?.detail ?? {}));

/** 应用组内存在失败项时导航标红（旧 Anchor title 标红契约） */
function groupHasError(items: InstallationApi.ProcessDetailItem[]) {
  return items.some((item) => item.status === 3);
}

/** 轮询期间同步刷新展开面板日志 */
function fetchOpenLog() {
  if (!openName.value) return;
  const [appName, ip] = openName.value.split('=');
  if (!appName || !ip) return;
  showSingleServiceInstallLog({
    app_name: appName,
    ip,
    unique_key: props.uniqueKey,
  })
    .then((result) => {
      log.value = result?.log ?? '';
    })
    .catch(() => {
      // 全局拦截器已提示
    });
}

let queried = false;

function queryProcess() {
  // 重入（重试后重新查询）先清掉待触发的轮询，避免双链路
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  // 仅首轮展示整页 loading（旧 !timer.current 契约）
  if (!queried) loading.value = true;
  queried = true;
  showInstallProcess(props.uniqueKey)
    .then((result) => {
      process.value = result;
      const status = result?.status;
      if (status === 0 || status === 1 || status === 4) {
        fetchOpenLog();
        timer = setTimeout(() => {
          timer = null;
          queryProcess();
        }, 5000);
      } else {
        fetchOpenLog();
      }
    })
    .catch(() => {
      // 全局拦截器已提示
    })
    .finally(() => {
      loading.value = false;
    });
}

function handleToggle(name: string) {
  if (openName.value === name) {
    openName.value = '';
    return;
  }
  log.value = '';
  openName.value = name;
  fetchOpenLog();
}

/** 重试安装（失败状态下发，成功后重新轮询进度） */
function handleRetry() {
  retryLoading.value = true;
  openName.value = '';
  log.value = '';
  retryInstall(props.uniqueKey)
    .then(() => {
      queryProcess();
    })
    .catch(() => {
      // 全局拦截器已提示
    })
    .finally(() => {
      retryLoading.value = false;
    });
}

/** 开始安装：轮询主机 agent 状态，全部在线即下发安装（旧 queryHostAgent 契约） */
function handleStart() {
  startLoading.value = true;
  agentTimer = setInterval(() => {
    const ipSet = new Set<string>();
    for (const items of detailGroups.value) {
      for (const item of items[1]) {
        // postAction 为安装后动作占位，不计入 agent 检查
        if (item.ip !== 'postAction') ipSet.add(item.ip);
      }
    }
    getHostsAgentStatus([...ipSet])
      .then((ready) => {
        if (ready) {
          if (agentTimer) {
            clearInterval(agentTimer);
            agentTimer = null;
          }
          startLoading.value = false;
          handleRetry();
        }
      })
      .catch(() => {
        // 全局拦截器已提示
      });
  }, 1000);
}

function scrollToGroup(key: string) {
  document
    .getElementById(`a${key}`)
    ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function handleFinish() {
  router.push('/application_management/install-record');
}

onUnmounted(() => {
  if (timer) clearTimeout(timer);
  if (agentTimer) clearInterval(agentTimer);
});

queryProcess();
</script>

<template>
  <!-- 满高布局：左明细内部滚动 + 右导航满高右对齐 + 底部操作条钉视口底 -->
  <div class="mt-5 flex min-h-0 flex-1 gap-5 overflow-hidden">
    <div class="min-h-0 min-w-0 flex-1 overflow-y-auto">
      <Spin :spinning="loading">
        <div>
          <InstallInfoItem
            v-for="[key, items] in detailGroups"
            :key="key"
            :items="items"
            :log="log"
            :open-name="openName"
            :title="key"
            @toggle-open="handleToggle"
          />
          <div
            v-if="detailGroups.length === 0 && !loading"
            class="bg-card p-10 text-center"
          >
            暂无安装明细
          </div>
        </div>
      </Spin>
    </div>

    <!-- 右侧应用导航（旧 Anchor 契约，失败应用标红；条目左对齐） -->
    <div class="flex w-[200px] shrink-0 flex-col bg-card p-2.5 pt-2">
      <div class="min-h-0 flex-1 overflow-y-auto pr-1">
        <div v-for="[key, items] in detailGroups" :key="key" class="py-1">
          <a
            class="block py-0.5 pl-1 text-[13px]"
            :style="{ color: groupHasError(items) ? 'rgb(218, 78, 72)' : undefined }"
            @click.prevent="scrollToGroup(key)"
          >
            {{ key }}
          </a>
        </div>
      </div>
    </div>
  </div>

  <!-- 底部操作条：状态 + 总进度 + 操作（钉视口底） -->
  <div class="mt-5 flex shrink-0 items-center justify-between bg-card py-6 pl-6 pr-8">
    <div class="flex items-center">
      <span class="w-[100px]">
        {{ STATUS_TEXT[process?.status ?? -1] ?? '-' }}
        <IconifyIcon
          v-if="process && [0, 1, 4].includes(process.status)"
          class="ml-2.5 inline animate-spin text-base align-[-2px]"
          icon="lucide:loader-circle"
        />
      </span>
    </div>
    <div class="mx-10 flex-1">
      <Progress
        :percent="process?.percentage ?? 0"
        :status="process?.status === 3 ? 'exception' : 'normal'"
      />
    </div>
    <div class="pr-2.5">
      <Button
        v-if="process?.status === 0"
        :loading="startLoading"
        html-type="button"
        type="primary"
        @click="handleStart"
      >
        开始
      </Button>
      <Button
        v-if="process?.status === 3"
        :loading="retryLoading"
        html-type="button"
        type="primary"
        @click="handleRetry"
      >
        重试
      </Button>
      <Button
        class="ml-2.5"
        html-type="button"
        type="primary"
        @click="handleFinish"
      >
        完成
      </Button>
    </div>
  </div>
</template>
