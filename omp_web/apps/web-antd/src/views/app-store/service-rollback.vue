<script lang="ts" setup>
import type { ExecutionRecordApi } from '#/api/execution-record';

import { computed, onUnmounted, shallowRef } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Button, Progress, Spin, Tooltip } from 'ant-design-vue';

import { queryRollbackHistory, retryRollback } from '#/api/execution-record';

import HistoryProgressGroup from './history-progress-group.vue';

/**
 * 服务回滚进度页（/application_management/app_store/service_rollback，
 * query ?history=<RollbackHistory.id> 消费——跳转方为商店回滚弹窗、
 * 升级进度页失败定点回滚与执行记录页「查看」）。
 * rollback_state 0/1/4 时 5s 轮询；失败可重试（PUT）。
 * 旧实现 omp_web/src/pages/AppStore/config/Rollback/ 迁移。
 */
defineOptions({ name: 'ServiceRollback' });

const route = useRoute();
const router = useRouter();

/** 回滚历史 id（query 透传，旧 location.state.history 契约） */
const historyId = computed(() => {
  const value = route.query.history;
  return typeof value === 'string' && value ? value : '';
});

/** 主状态文案（与后端 RollbackStateChoices 一致） */
const STATUS_TEXT: Record<number, string> = {
  0: '等待回滚',
  1: '正在回滚',
  2: '回滚成功',
  3: '回滚失败',
  4: '正在注册',
};

const loading = shallowRef(true);
const retryLoading = shallowRef(false);

const detail = shallowRef<ExecutionRecordApi.RollbackHistoryDetail>();

const groups = computed(() =>
  (detail.value?.rollback_detail ?? []).map((group) => ({
    items: (group.rollback_details ?? []).map((item) => ({
      instance_name: item.instance_name,
      message: item.message,
      state: item.rollback_state,
    })),
    title: group.service_name,
  })),
);

/** 分组内存在失败项时右侧导航标红（旧契约） */
function groupHasError(items: { state: number }[]) {
  return items.some((item) => item.state === 3);
}

/** 总进度百分比（all_count 为 0 时按 0 处理，旧版除零 NaN 为既有缺陷） */
const percent = computed(() => {
  const all = detail.value?.all_count ?? 0;
  const success = detail.value?.success_count ?? 0;
  return all > 0 ? Number(((success / all) * 100).toFixed()) : 0;
});

let timer: null | ReturnType<typeof setTimeout> = null;

let firstQuery = true;

function queryProcess() {
  // 重入（重试后重新查询）先清掉待触发的轮询，避免双链路
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  // 仅首次查询转圈（与旧版一致）；轮询刷新不闪 Spin
  loading.value = firstQuery;
  firstQuery = false;
  queryRollbackHistory(historyId.value)
    .then((data) => {
      detail.value = data;
      const state = data?.rollback_state;
      if (state === 0 || state === 1 || state === 4) {
        timer = setTimeout(() => {
          timer = null;
          queryProcess();
        }, 5000);
      }
    })
    .catch(() => {
      // 全局拦截器已提示
    })
    .finally(() => {
      loading.value = false;
    });
}

/** 回滚重试（失败状态下发，成功后重新轮询） */
function handleRetry() {
  retryLoading.value = true;
  retryRollback(historyId.value)
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

function scrollToGroup(idx: number) {
  document
    .getElementById(`a${idx}`)
    ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function goRecord() {
  router.push('/application_management/install-record');
}

onUnmounted(() => {
  if (timer) clearTimeout(timer);
});

queryProcess();
</script>

<template>
  <!-- 满高纵向布局：顶条/内容/底部操作条分区，内容区内部滚动（页面无滚动条） -->
  <Page content-class="flex min-h-0 flex-col overflow-hidden">
    <!-- 顶部导航条：返回 + 标题 -->
    <div class="flex h-[50px] shrink-0 items-center bg-card pl-5 pr-[50px]">
      <Tooltip title="返回">
        <Button
          class="border-0 bg-transparent px-1 shadow-none"
          size="small"
          @click="goRecord"
        >
          <template #icon>
            <IconifyIcon class="text-base" icon="lucide:arrow-left" />
          </template>
        </Button>
      </Tooltip>
      <span class="whitespace-nowrap pl-3 text-base">服务回滚</span>
    </div>

    <!-- 满高布局：左明细内部滚动 + 右导航满高右对齐 + 底部操作条钉视口底 -->
    <div class="mt-5 flex min-h-0 flex-1 gap-5 overflow-hidden">
      <div class="min-h-0 min-w-0 flex-1 overflow-y-auto">
        <Spin :spinning="loading">
          <div class="min-w-0">
            <HistoryProgressGroup
              v-for="(group, idx) in groups"
              :key="group.title"
              :anchor-id="`a${idx}`"
              :items="group.items"
              kind="rollback"
              :title="group.title"
            />
            <div
              v-if="groups.length === 0 && !loading"
              class="bg-card p-10 text-center"
            >
              暂无回滚明细
            </div>
          </div>
        </Spin>
      </div>

      <!-- 右侧应用导航（旧 Anchor 契约，失败应用标红；条目左对齐） -->
      <div class="flex w-[200px] shrink-0 flex-col bg-card p-2.5 pt-2">
        <div class="min-h-0 flex-1 overflow-y-auto pr-1">
          <div v-for="(group, idx) in groups" :key="group.title" class="py-1">
            <a
              class="block py-0.5 pl-1 text-[13px]"
              :style="{
                color: groupHasError(group.items) ? 'rgb(218, 78, 72)' : undefined,
              }"
              @click.prevent="scrollToGroup(idx)"
            >
              {{ group.title }}
            </a>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部操作条：状态 + 总进度 + 操作（钉视口底） -->
    <div class="mt-5 flex shrink-0 items-center justify-between bg-card py-6 pl-6 pr-8">
      <span class="w-[100px]">
        {{ STATUS_TEXT[detail?.rollback_state ?? -1] ?? '-' }}
        <IconifyIcon
          v-if="detail && [0, 1, 4].includes(detail.rollback_state)"
          class="ml-2.5 inline animate-spin text-base align-[-2px]"
          icon="lucide:loader-circle"
        />
      </span>
      <div class="mx-10 min-w-0 flex-1">
        <Progress
          :percent="percent"
          :status="detail?.rollback_state === 3 ? 'exception' : 'normal'"
        />
      </div>
      <div class="shrink-0 pr-2.5">
        <Button
          v-if="detail?.rollback_state === 3"
          :loading="retryLoading"
          html-type="button"
          type="primary"
          @click="handleRetry"
        >
          重试
        </Button>
        <Button class="ml-2.5" html-type="button" type="primary" @click="goRecord">
          完成
        </Button>
      </div>
    </div>
  </Page>
</template>
