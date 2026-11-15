<script lang="ts" setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';

import { Modal } from 'ant-design-vue';

import { getServiceInstallLog } from '#/api/services';

defineOptions({ name: 'ServiceInstallLogModal' });

/**
 * 安装记录弹窗：黑底实时日志。
 * Salt 异步任务 —— install_step_status 处于 等待(0)/安装中(1) 时
 * 每 2s 轮询一次（照搬旧页 queryServiceInstallHistoryDetail 语义）。
 */
const POLL_INTERVAL = 2_000;

const open = ref(false);
const log = ref('');
const logContainer = ref<HTMLElement>();

let pollTimer: null | ReturnType<typeof setTimeout> = null;
/** 轮询目标服务 id（跨轮询闭包引用） */
let serviceId: null | number = null;

function stopPolling() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

async function fetchLog() {
  if (serviceId === null) return;
  try {
    const data = await getServiceInstallLog(serviceId);
    const latest = data?.[0];
    if (latest) {
      log.value = latest.log ?? '';
      // 等待/安装中继续轮询
      if (latest.install_step_status === 0 || latest.install_step_status === 1) {
        pollTimer = setTimeout(fetchLog, POLL_INTERVAL);
      }
    }
  } catch {
    // 全局拦截器已提示错误信息；不打断会话，等待下一次打开重新拉取
  }
}

async function openModal(id: number) {
  stopPolling();
  serviceId = id;
  log.value = '';
  open.value = true;
  await fetchLog();
}

defineExpose({ open: openModal });

function handleClose() {
  open.value = false;
  stopPolling();
  serviceId = null;
}

/** 日志更新后滚动到底部（照搬旧页 containerRef.scrollTop 行为） */
watch(log, async () => {
  await nextTick();
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight;
  }
});

onBeforeUnmount(stopPolling);
</script>

<template>
  <Modal
    :footer="null"
    :open="open"
    :style="{ top: '200px' }"
    :width="640"
    title="安装记录"
    @cancel="handleClose"
  >
    <div
      ref="logContainer"
      class="h-[300px] overflow-y-auto overflow-x-hidden break-all whitespace-pre-line bg-black p-2.5 text-white"
    >
      {{ log || '正在安装...' }}
    </div>
  </Modal>
</template>
