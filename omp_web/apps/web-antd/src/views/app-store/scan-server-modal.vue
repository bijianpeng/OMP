<script lang="ts" setup>
import type { AppStoreApi } from '#/api/app-store';

import { ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Button, Modal, Steps, Table } from 'ant-design-vue';

import {
  executeLocalPackageScan,
  queryLocalPackageScanResult,
} from '#/api/app-store';

/**
 * 扫描服务端安装包：打开即下发扫描命令，有包则轮询校验/发布进度。
 * stage_status 值域：scanning / checking / check_all_failed / publishing / published，
 * 含 "check" 进入校验步、含 "publish" 进入发布步、含 "ing" 继续轮询（旧契约）。
 */
defineOptions({ name: 'ScanServerModal' });

const emit = defineEmits<{ refresh: [] }>();

const open = ref(false);
const stepNum = ref(0);
/** 步骤 0 的「正在扫描服务端」文案态 */
const loading = ref(false);
const dataSource = ref<AppStoreApi.ScanResult>();

/** 弹窗关闭后不再续轮询（旧 isOpen 契约） */
const isRun = ref(false);
let timer: null | ReturnType<typeof setTimeout> = null;
/** 轮询连续失败计数（超过 3 次全部标记网络错误） */
const retryCount = ref(0);

function resetState() {
  stepNum.value = 0;
  loading.value = false;
  dataSource.value = undefined;
  retryCount.value = 0;
  stopPolling();
}

function stopPolling() {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
}

function openModal() {
  resetState();
  open.value = true;
  isRun.value = true;
  executeScan();
}

defineExpose({ open: openModal });

function closeModal() {
  open.value = false;
  isRun.value = false;
  resetState();
  emit('refresh');
}

/** 下发扫描命令：无包展示提示文案，有包进入状态轮询 */
async function executeScan() {
  stepNum.value = 0;
  loading.value = true;
  try {
    const data = await executeLocalPackageScan();
    if ((data?.package_names ?? []).filter((i) => i).length > 0) {
      pollScanResult(data!);
    }
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

function pollScanResult(scan: AppStoreApi.ScanResult) {
  if (!isRun.value) return;
  queryLocalPackageScanResult({
    package_names: (scan.package_names ?? []).join(','),
    uuid: scan.uuid ?? '',
  })
    .then((data) => {
      if (data.stage_status.includes('check')) {
        stepNum.value = 1;
      }
      if (data.stage_status.includes('publish')) {
        stepNum.value = 2;
      }
      dataSource.value = data;
      if (data.stage_status.includes('ing')) {
        timer = setTimeout(() => pollScanResult(scan), 2000);
      }
    })
    .catch(() => {
      retryCount.value += 1;
      if (retryCount.value < 3) {
        timer = setTimeout(() => pollScanResult(scan), 5000);
      } else if (dataSource.value) {
        dataSource.value = {
          ...dataSource.value,
          package_detail: (dataSource.value.package_detail ?? []).map(
            (item) => ({ ...item, status: 9 }),
          ),
        };
      }
    });
}

/** 校验/发布明细行名称（与 package_names_lst 下标对应，旧契约） */
function packageNameOf(index: number) {
  return dataSource.value?.package_names_lst?.[index] ?? '';
}

function scanStatusText(status: number) {
  switch (status) {
    // 校验阶段
    case 0: {
      return '校验成功';
    }
    case 1: {
      return '校验失败';
    }
    case 2: {
      return '校验中';
    }
    // 发布阶段
    case 3: {
      return '发布成功';
    }
    case 4: {
      return '发布失败';
    }
    case 5: {
      return '发布中';
    }
    case 9: {
      return '网络错误';
    }
    default: {
      return '';
    }
  }
}

const detailColumns = [
  {
    title: '安装包名称',
    dataIndex: 'name',
    key: 'name',
    align: 'center' as const,
    customRender: ({ index }: { index: number }) => packageNameOf(index),
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    align: 'center' as const,
    customRender: ({ text }: { text: number }) => scanStatusText(text),
  },
  {
    title: '说明',
    dataIndex: 'message',
    key: 'message',
    align: 'center' as const,
    // ellipsis 开启后 antd 自动以原生 title 提示全文
    ellipsis: true,
  },
];
</script>

<template>
  <Modal
    :open="open"
    title="扫描服务端安装包"
    :width="1000"
    :footer="null"
    destroy-on-close
    @cancel="closeModal"
  >
    <Steps
      :current="stepNum"
      size="small"
      type="navigation"
    >
      <Steps.Step title="扫描服务端安装包" />
      <Steps.Step title="安装包数据校验" />
      <Steps.Step title="发布" />
    </Steps>

    <!-- 步骤 0：扫描 -->
    <div v-if="stepNum === 0" class="px-7 pt-7 pb-5">
      <p v-if="loading" class="text-center">正在扫描服务端...</p>
      <div v-else class="text-center">
        <p>扫描结束，服务端暂无安装包！</p>
        <p class="pt-1">
          请将安装包上传至
          <span class="font-medium text-foreground">
            omp/package_hub/back_end_verified/
          </span>
          目录后重新扫描
        </p>
      </div>
    </div>

    <!-- 步骤 1：校验进度 -->
    <div v-else-if="stepNum === 1" class="px-7 pt-7 pb-5">
      <p class="pb-5 text-center">{{ dataSource?.message }}</p>
      <Table
        :columns="detailColumns"
        :data-source="dataSource?.package_detail ?? []"
        :pagination="false"
        class="border border-[#e3e3e3]"
        size="middle"
      />
      <div v-if="dataSource?.stage_status === 'check_all_failed'" class="mt-14 text-center">
        <Button type="primary" @click="closeModal">完成</Button>
      </div>
    </div>

    <!-- 步骤 2：发布结果 -->
    <div v-else class="px-7 pt-7 pb-5">
      <p
        v-if="dataSource?.stage_status === 'published'"
        class="flex items-center justify-center gap-2.5 text-xl"
      >
        <IconifyIcon
          icon="lucide:circle-check"
          class="text-2xl text-[#3cbd35]"
        />
        发布完成
      </p>
      <p class="pt-1 text-center">{{ dataSource?.message }}</p>
      <p class="pt-1 text-center">
        发布完成的安装包存放路径:
        <span class="font-medium text-foreground">omp/package_hub/verified/</span>
      </p>
      <Table
        :columns="detailColumns"
        :data-source="dataSource?.package_detail ?? []"
        :pagination="false"
        class="mt-3 border border-[#e3e3e3]"
        size="middle"
      />
      <div class="mt-14 text-center">
        <Button
          type="primary"
          :disabled="dataSource?.stage_status !== 'published'"
          @click="closeModal"
        >
          完成
        </Button>
      </div>
    </div>
  </Modal>
</template>
