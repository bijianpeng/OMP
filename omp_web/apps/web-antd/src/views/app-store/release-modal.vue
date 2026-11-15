<script lang="ts" setup>
import type { UploadFile, UploadProps } from 'ant-design-vue';

import type { AppStoreApi } from '#/api/app-store';

import { ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  message,
  Modal,
  Steps,
  Tooltip,
  Upload,
} from 'ant-design-vue';

import {
  publishPackages,
  queryPackVerificationResults,
  queryPublishResults,
  removePackages,
} from '#/api/app-store';

/**
 * 发布向导：上传安装包 → 数据校验（轮询）→ 发布结果（轮询）。
 * 交互契约照搬旧 ReleaseModal.js：uuid 由列表页打开时生成传入；
 * 关闭时若仍有已上传文件需确认中断（后端删除已传包）。
 */
defineOptions({ name: 'ReleaseModal' });

const emit = defineEmits<{ refresh: [] }>();

const open = ref(false);
/** 发布操作唯一键（毫秒时间戳，列表页生成） */
const uuid = ref<number | string>('');
/** 0 上传文件 1 数据校验 2 发布结果 */
const stepNum = ref(0);
const loading = ref(false);
const filesList = ref<UploadFile[]>([]);
/** 校验/发布结果行（package_status：0 校验通过 1 校验失败 2 校验中 3 发布成功 4 发布失败 5 发布中 9 网络错误） */
const dataSource = ref<AppStoreApi.PackageResult[]>([]);

/** 弹窗关闭后不再续轮询（旧 isRun 契约） */
const isRun = ref(false);
let timer: null | ReturnType<typeof setTimeout> = null;
/** 轮询连续失败计数（超过 3 次全部标记网络错误） */
const retryCount = ref(0);

/** 上传附加参数中的操作人（登录时持久化的用户名） */
const operationUser = localStorage.getItem(
  `${import.meta.env.VITE_APP_NAMESPACE}-omp-username`,
) ?? '';

function resetState() {
  filesList.value = [];
  stepNum.value = 0;
  dataSource.value = [];
  retryCount.value = 0;
  stopPolling();
}

function stopPolling() {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
}

function openModal(uuidValue: number | string) {
  resetState();
  uuid.value = uuidValue;
  open.value = true;
  isRun.value = true;
}

defineExpose({ open: openModal });

function closeModal() {
  open.value = false;
  isRun.value = false;
  resetState();
  emit('refresh');
}

// ── 步骤 0：上传 ────────────────────────────────────────────────

const beforeUpload: UploadProps['beforeUpload'] = (file, batchFiles) => {
  const fileSize = file.size / 1024 / 1024 / 1024;
  if (Math.ceil(fileSize) > 4) {
    message.error('仅支持传入4G以内文件');
    return Upload.LIST_IGNORE;
  }
  if (batchFiles.length > 5) {
    if (file === batchFiles[0]) {
      message.error('单次发布操作，最多支持上传5个文件');
    }
    return Upload.LIST_IGNORE;
  }
  if (filesList.value.length + batchFiles.length > 5) {
    if (file === batchFiles[0]) {
      message.error('单次发布操作，最多支持上传5个文件');
    }
    return Upload.LIST_IGNORE;
  }
  if (filesList.value.length >= 5) {
    if (file === batchFiles[0]) {
      message.error('单次发布操作，最多支持上传5个文件');
    }
    return Upload.LIST_IGNORE;
  }
  if (/[^a-zA-Z0-9_.-]/.test(file.name)) {
    message.error(`文件名仅支持字母、数字、"_"、"-"和"."`);
    return Upload.LIST_IGNORE;
  }
  // 与已有文件 + 本批文件比对重名
  const fileNameArr =
    batchFiles.length === 1
      ? [...filesList.value, file].map((i) => i.name)
      : [...filesList.value, ...batchFiles].map((i) => i.name);
  if (new Set(fileNameArr).size !== fileNameArr.length) {
    if (batchFiles[0]?.uid === file.uid) {
      message.error('上传文件存在同名');
    }
    return Upload.LIST_IGNORE;
  }
};

const uploadData: UploadProps['data'] = (file) => ({
  // md5 传 antd 内部 uid（旧前端同款契约，仅作占位标识）
  md5: file.uid,
  operation_user: operationUser,
  uuid: uuid.value,
});

function handleRemove(file: UploadFile) {
  // 仅已上传成功的文件需要通知后端删除
  if ((file.response as null | { code?: number })?.code === 0) {
    removePackages({ package_names: [file.name], uuid: uuid.value }).catch(
      () => {},
    );
  }
}

/** 「校验」：全部上传完成且至少一个文件才可点 */
function clickCheck() {
  stepNum.value = 1;
  retryCount.value = 0;
  pollResults(() => queryPackVerificationResults(uuid.value));
}

// ── 通用结果轮询（校验/发布共用，2s 间隔直到无 2/5 状态） ──────

function pollResults(fetcher: () => Promise<AppStoreApi.PackageResult[]>) {
  if (!isRun.value) return;
  fetcher()
    .then((data) => {
      dataSource.value = data ?? [];
      const running = dataSource.value.some((i) =>
        [2, 5].includes(i.package_status),
      );
      if (running) {
        timer = setTimeout(() => pollResults(fetcher), 2000);
      }
    })
    .catch(() => {
      retryCount.value += 1;
      if (retryCount.value < 3) {
        timer = setTimeout(() => pollResults(fetcher), 5000);
      } else {
        dataSource.value = dataSource.value.map((i) => ({
          ...i,
          package_status: 9,
        }));
      }
    });
}

// ── 步骤 1 → 2：发布 ────────────────────────────────────────────

async function clickPublish() {
  loading.value = true;
  try {
    await publishPackages(uuid.value);
    stepNum.value = 2;
    retryCount.value = 0;
    pollResults(() => queryPublishResults(uuid.value));
  } catch {
    // 全局拦截器已提示，停留在校验结果页
  } finally {
    loading.value = false;
  }
}

// ── 关闭（含中断确认） ──────────────────────────────────────────

function handleCancel() {
  // 发布结果页且无发布中的包，直接关闭
  if (
    stepNum.value === 2 &&
    !dataSource.value.some((i) => i.package_status === 5)
  ) {
    closeModal();
    return;
  }
  if (filesList.value.length === 0) {
    closeModal();
    return;
  }
  Modal.confirm({
    content:
      '正在进行发布操作，关闭窗口将会中断，此操作不可逆。已上传的安装包将被删除。',
    okText: '确定',
    cancelText: '取消',
    title: '确认要中断发布操作吗？',
    async onOk() {
      const uploaded = filesList.value.filter(
        (i) => (i.response as null | { code?: number })?.code === 0,
      );
      if (uploaded.length === 0) {
        closeModal();
        return;
      }
      try {
        await removePackages({
          package_names: uploaded.map((i) => i.name),
          uuid: uuid.value,
        });
      } catch {
        // 全局拦截器已提示，删除失败也照常关闭（旧前端 finally 契约）
      }
      closeModal();
    },
  });
}

/** 状态行渲染所需的分状态文案 */
function statusView(status: number) {
  switch (status) {
    case 0: {
      return { icon: 'lucide:circle-check', text: '校验通过', type: 'success' };
    }
    case 1: {
      return { icon: 'lucide:circle-x', text: '校验失败', type: 'error' };
    }
    case 2: {
      return { icon: 'lucide:loader-circle', text: '校验中...', type: 'running' };
    }
    case 3: {
      return { icon: 'lucide:circle-check', text: '发布成功', type: 'success' };
    }
    case 4: {
      return { icon: 'lucide:circle-x', text: '发布失败', type: 'error' };
    }
    case 5: {
      return { icon: 'lucide:loader-circle', text: '发布中...', type: 'running' };
    }
    case 9: {
      return { icon: 'lucide:circle-x', text: '网络错误', type: 'error' };
    }
    default: {
      return null;
    }
  }
}

const publishingCount = () =>
  dataSource.value.filter((i) => i.package_status === 5).length;
const passCount = () =>
  dataSource.value.filter((i) => i.package_status === 0).length;
const checkingCount = () =>
  dataSource.value.filter((i) => i.package_status === 2).length;
const successCount = () =>
  dataSource.value.filter((i) => i.package_status === 3).length;
</script>

<template>
  <Modal
    :open="open"
    title="发布"
    :width="1000"
    :footer="null"
    destroy-on-close
    @cancel="handleCancel"
  >
    <Steps :current="stepNum" size="small">
      <Steps.Step title="上传文件" />
      <Steps.Step title="数据校验" />
      <Steps.Step title="发布结果" />
    </Steps>

    <!-- 步骤 0：上传安装包 -->
    <div v-if="stepNum === 0" class="px-7 pt-7 pb-5">
      <Upload.Dragger
        accept=".tar,.gz"
        class="block w-full"
        action="/api/appStore/upload/"
        :data="uploadData"
        :max-count="5"
        multiple
        :before-upload="beforeUpload"
        @remove="handleRemove"
        v-model:file-list="filesList"
      >
        <p class="text-lg">☁</p>
        <p class="text-foreground">点击或将文件拖拽到这里上传</p>
        <p class="pt-2 text-[13px] text-muted-foreground">
          支持扩展名: .tar 或 .tar.gz 文件大小不超过4G
        </p>
        <p class="pt-2 text-[13px] text-muted-foreground">最多上传5个文件</p>
      </Upload.Dragger>
      <div class="mt-5 text-center">
        <Button
          type="primary"
          :disabled="
            filesList.length === 0 ||
            filesList.some((i) => i.status !== 'done')
          "
          @click="clickCheck"
        >
          校验
        </Button>
      </div>
    </div>

    <!-- 步骤 1：数据校验结果 -->
    <div v-else-if="stepNum === 1" class="px-7 pt-7 pb-5">
      <p class="mb-7">
        校验失败的安装包不会在应用商店创建，如相同名称应用已存在，发布后会替换原有安装包
      </p>
      <div
        v-for="(item, idx) in dataSource"
        :key="idx"
        class="mb-2.5 flex justify-around pr-20"
      >
        <div class="basis-2/5 truncate">{{ item.package_name }}</div>
        <div class="basis-1/5 shrink-0 text-right">
          <span
            v-if="statusView(item.package_status)"
            class="inline-flex items-center gap-2"
            :class="
              statusView(item.package_status)?.type === 'error'
                ? 'text-[#fe1937]'
                : ''
            "
          >
            {{ statusView(item.package_status)?.text }}
            <IconifyIcon
              :icon="statusView(item.package_status)?.icon ?? ''"
              :class="
                statusView(item.package_status)?.type === 'running'
                  ? 'animate-spin text-base'
                  : 'text-lg'
              "
            />
          </span>
        </div>
        <Tooltip placement="right" :title="item.error_msg">
          <div
            class="basis-2/5 truncate pl-5 text-right"
            :title="item.error_msg ?? ''"
          >
            {{ item.error_msg || '' }}
          </div>
        </Tooltip>
      </div>
      <div class="mt-14 text-center">
        <Button
          type="primary"
          :loading="loading"
          :disabled="passCount() === 0 || checkingCount() !== 0"
          @click="clickPublish"
        >
          发布
        </Button>
      </div>
    </div>

    <!-- 步骤 2：发布结果 -->
    <div v-else class="px-7 pt-7 pb-5">
      <div v-if="publishingCount() > 0" class="pb-5">
        <p class="flex items-center justify-center gap-2.5 text-xl">
          <IconifyIcon
            icon="lucide:clock-3"
            class="text-2xl text-[#ffb436]"
          />
          发布中
        </p>
      </div>
      <div v-else class="mb-5">
        <p class="flex items-center justify-center gap-2.5 text-xl">
          <IconifyIcon
            icon="lucide:circle-check"
            class="text-2xl text-[#3cbd35]"
          />
          发布完成
        </p>
        <p class="pt-1 text-center">
          本次成功发布 {{ successCount() }} 个 服务
        </p>
        <p class="pt-1 text-center">
          发布完成的安装包存放路径:
          <span class="font-medium text-foreground">omp/package_hub/verified/</span>
        </p>
      </div>

      <div
        v-for="(item, idx) in dataSource"
        :key="idx"
        class="mb-2.5 flex justify-around pr-20"
      >
        <div class="basis-2/5 truncate">{{ item.package_name }}</div>
        <div class="basis-1/5 shrink-0 text-right">
          <span
            v-if="statusView(item.package_status)"
            class="inline-flex items-center gap-2"
            :class="
              statusView(item.package_status)?.type === 'error'
                ? 'text-[#fe1937]'
                : ''
            "
          >
            {{ statusView(item.package_status)?.text }}
            <IconifyIcon
              :icon="statusView(item.package_status)?.icon ?? ''"
              :class="
                statusView(item.package_status)?.type === 'running'
                  ? 'animate-spin text-base'
                  : 'text-lg'
              "
            />
          </span>
        </div>
        <Tooltip placement="right" :title="item.error_msg">
          <div
            class="basis-2/5 truncate pl-5 text-right"
            :title="item.error_msg ?? ''"
          >
            {{ item.error_msg || '' }}
          </div>
        </Tooltip>
      </div>
      <div class="mt-14 text-center">
        <Button
          type="primary"
          :disabled="publishingCount() > 0"
          @click="closeModal"
        >
          完成
        </Button>
      </div>
    </div>
  </Modal>
</template>
