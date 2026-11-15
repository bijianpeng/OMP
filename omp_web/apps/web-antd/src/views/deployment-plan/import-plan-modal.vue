<script lang="ts" setup>
import type { UploadProps } from 'ant-design-vue';

import type {
  DeploymentPlanApi,
} from '#/api/deployment-plan';
import type { HostApi } from '#/api/hosts';

import { h, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  message,
  Modal,
  Steps,
  Table,
  Tooltip,
  Upload,
} from 'ant-design-vue';
import { read as xlsxRead, utils as xlsxUtils } from 'xlsx';

import {
  getHostsAgentStatus,
  importDeploymentPlan,
  retryInstall,
  validateDeploymentServices,
} from '#/api/deployment-plan';
import {
  batchImportHosts,
  batchValidateHosts,
} from '#/api/hosts';

defineOptions({ name: 'ImportPlanModal' });

const emit = defineEmits<{ success: [] }>();

const router = useRouter();

const open = ref(false);
/** 0 上传文件 1 导入结果 */
const stepNum = ref(0);
const loading = ref(false);

/** xlsx 解析出的主机原始行（「实例名[必填]」等中文表头键） */
const hostRows = ref<Record<string, any>[]>([]);
/** xlsx 解析出的服务分布原始行 */
const serviceRows = ref<Record<string, any>[]>([]);
/** 主机表头（过滤占位列后，仅用作「开始导入」按钮禁用判断） */
const columnHeaders = ref<string[]>([]);

/** 三阶段状态：null 进行中 / true 通过 / false 未通过 */
const hostStep = ref<boolean | null>(null);
const serviceStep = ref<boolean | null>(null);
const importStep = ref<boolean | null>(null);
/** 整体导入结果：null 链路进行中 / true 成功 / false 失败 */
const importResult = ref<boolean | null>(null);

const hostErrorData = ref<Record<string, any>[]>([]);
const serviceErrorData = ref<Record<string, any>[]>([]);

/** 数量汇总（导入成功后展示） */
const numInfo = ref<DeploymentPlanApi.ImportSummary>();

/** 校验/导入通过的数据（跨阶段链式传递，无渲染依赖） */
let hostCorrectData: null | Record<string, any>[] = null;
let serviceCorrectData: null | Record<string, any>[] = null;

/** agent 就绪轮询器（导入成功后每秒查询，全部在线即跳安装页） */
let hostAgentTimer: null | ReturnType<typeof setInterval> = null;

function resetState() {
  hostRows.value = [];
  serviceRows.value = [];
  columnHeaders.value = [];
  hostStep.value = null;
  serviceStep.value = null;
  importStep.value = null;
  importResult.value = null;
  hostErrorData.value = [];
  serviceErrorData.value = [];
  numInfo.value = undefined;
  hostCorrectData = null;
  serviceCorrectData = null;
  stopAgentTimer();
}

function openModal() {
  resetState();
  open.value = true;
}

defineExpose({ open: openModal });

function handleClose() {
  open.value = false;
  // 关闭即重置（照搬旧页 afterClose + destroyOnClose 契约）
  resetState();
  emit('success');
}

function stopAgentTimer() {
  if (hostAgentTimer) {
    clearInterval(hostAgentTimer);
    hostAgentTimer = null;
  }
}

onUnmounted(() => stopAgentTimer());

// ── xlsx 前端解析（主机/服务两个 sheet，照搬旧页 UploadExcelComponent 契约） ──

/** 首行表头（空单元格记为 UNKNOWN N，后续列过滤剔除） */
function getHeaderRow(sheet: any) {
  const headers: string[] = [];
  const range = xlsxUtils.decode_range(sheet['!ref']);
  for (let c = range.s.c; c <= range.e.c; ++c) {
    const cell = sheet[xlsxUtils.encode_cell({ c, r: range.s.r })];
    let hdr = `UNKNOWN ${c}`;
    if (cell && cell.t) hdr = xlsxUtils.format_cell(cell);
    headers.push(hdr);
  }
  return headers;
}

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  // 仅支持 10M 以内 .xlsx
  if (Math.ceil(file.size / 1024 / 1024) > 10) {
    message.error('仅支持传入10M以内文件');
    return Upload.LIST_IGNORE;
  }
  if (!/\.xlsx$/.test(file.name)) {
    message.error('仅支持传入.xlsx文件');
    return Upload.LIST_IGNORE;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const workbook = xlsxRead(e.target?.result, { type: 'array' });
      // sheet1 主机数据 / sheet2 服务分布
      const hostSheet = workbook.Sheets[workbook.SheetNames[0] ?? ''] as any;
      const serviceSheet = workbook.Sheets[
        workbook.SheetNames[1] ?? ''
      ] as any;
      const hostHeader = getHeaderRow(hostSheet);
      const serviceHeader = getHeaderRow(serviceSheet);
      const hostResults = xlsxUtils.sheet_to_json(hostSheet) as Record<
        string,
        any
      >[];
      const serviceResults = xlsxUtils.sheet_to_json(serviceSheet) as Record<
        string,
        any
      >[];
      handleParsed(
        { header: hostHeader, results: hostResults },
        { serviceHeader, serviceResults },
      );
      message.success(`${file.name} 文件解析成功`);
    } catch {
      message.error(
        `${file.name} 文件解析失败, 请确保文件内容格式符合规范后重新上传`,
      );
    }
  };
  reader.readAsArrayBuffer(file);
  // 阻断 antdv 默认上传，文件仅前端解析
  return false;
};

/** 模板说明行（字段名称(请勿编辑)）与关键列缺失的行不进数据源 */
function handleParsed(
  {
    header,
    results,
  }: { header: string[]; results: Record<string, any>[] },
  _service: { serviceHeader: string[]; serviceResults: Record<string, any>[] },
) {
  hostRows.value = results
    .filter((item) => {
      if (String(item['字段名称(请勿编辑)'] ?? '').includes('请勿编辑')) {
        return false;
      }
      return Boolean(item['实例名[必填]']);
    })
    .map((item) => ({ ...item, key: (item.__rowNum__ ?? 0) + 1 }));
  serviceRows.value = _service.serviceResults
    .filter((item) => {
      if (String(item['字段名称(请勿编辑)'] ?? '').includes('请勿编辑')) {
        return false;
      }
      return Boolean(item['主机实例名[必填]']);
    })
    .map((item) => ({ ...item, key: (item.__rowNum__ ?? 0) + 1 }));
  columnHeaders.value = header.filter(
    (item) =>
      !(item?.includes('请勿编辑') || item?.includes('UNKNOWN')),
  );
}

function handleRemove() {
  hostRows.value = [];
  serviceRows.value = [];
  columnHeaders.value = [];
  hostErrorData.value = [];
  serviceErrorData.value = [];
}

// ── 阶段一：主机数据校验（中文列头 → 英文字段映射，照搬旧页契约） ────

const HOST_FIELD_MAP: Record<
  string,
  (item: Record<string, any>, row: any) => void
> = {
  'IP[必填]': (item, row) => (item.ip = row),
  '实例名[必填]': (item, row) => (item.instance_name = row),
  '密码[必填]': (item, row) => (item.password = row),
  '操作系统[必填]': (item, row) => (item.operate_system = row),
  '数据分区[必填]': (item, row) => (item.data_folder = row),
  '用户名[必填]': (item, row) => (item.username = row),
  '端口[必填]': (item, row) => (item.port = row),
  '运行用户': (item, row) => (item.run_user = row),
  '时间同步服务器': (item, row) => {
    item.use_ntpd = true;
    item.ntpd_server = row;
  },
};

function buildHostQueryBody() {
  return hostRows.value.map((item) => {
    const result: Record<string, any> = {};
    for (const key in item) {
      HOST_FIELD_MAP[key]?.(result, item[key]);
    }
    if (!result.use_ntpd) result.use_ntpd = false;
    return { ...result, row: item.key };
  });
}

/** 服务分布映射（虚拟IP/角色/模式为高可用部署可选列） */
const SERVICE_FIELD_MAP: Record<
  string,
  (item: Record<string, any>, row: any) => void
> = {
  '主机实例名[必填]': (item, row) => (item.instance_name = row),
  '服务名[必填]': (item, row) => (item.service_name = row),
  '运行内存': (item, row) => (item.memory = row),
  '虚拟IP': (item, row) => (item.vip = row),
  '角色': (item, row) => (item.role = row),
  '模式': (item, row) => (item.mode = row),
};

function buildServiceQueryBody() {
  return serviceRows.value.map((item) => {
    const result: Record<string, any> = {};
    for (const key in item) {
      SERVICE_FIELD_MAP[key]?.(result, item[key]);
    }
    return { ...result, row: item.key };
  });
}

/** 点击「开始导入」：重置三阶段状态后进入链式校验 */
function clickImport() {
  hostStep.value = null;
  serviceStep.value = null;
  importStep.value = null;
  importResult.value = null;
  hostErrorData.value = [];
  serviceErrorData.value = [];
  stepNum.value = 1;
  fetchBatchValidate();
}

/** 阶段一：校验主机数据（复用主机管理批量校验接口） */
async function fetchBatchValidate() {
  loading.value = true;
  try {
    if (hostRows.value.length === 0) {
      message.warning('节点信息中无有效数据，请补充后重新上传');
      hostStep.value = false;
      importResult.value = false;
      return;
    }
    const data = await batchValidateHosts(
      buildHostQueryBody() as HostApi.BatchHostItem[],
    );
    if (data?.error?.length && data.error.length > 0) {
      hostErrorData.value = data.error.map((item, idx) => ({
        key: idx,
        ...item,
      }));
      hostStep.value = false;
      importResult.value = false;
    } else {
      hostCorrectData = data?.correct ?? [];
      hostStep.value = true;
      await serviceDataValidate();
    }
  } catch {
    // 全局拦截器已提示；链路中断按失败态展示
    hostStep.value = false;
    importResult.value = false;
  } finally {
    loading.value = false;
  }
}

/** 阶段二：校验服务分布（实例名数组取自 xlsx 主机原始行） */
async function serviceDataValidate() {
  loading.value = true;
  try {
    if (serviceRows.value.length === 0) {
      message.warning('服务分布中无有效数据，请补充后重新上传');
      serviceStep.value = false;
      importResult.value = false;
      return;
    }
    const instanceNameArr = hostRows.value.map(
      (item) => item['实例名[必填]'] ?? '',
    );
    const data = await validateDeploymentServices({
      instance_name_ls: instanceNameArr,
      service_data_ls: buildServiceQueryBody() as DeploymentPlanApi.ServiceDataItem[],
    });
    if (data?.error?.length && data.error.length > 0) {
      serviceErrorData.value = data.error.map((item, idx) => ({
        key: idx,
        ...item,
      }));
      serviceStep.value = false;
      importResult.value = false;
    } else {
      serviceCorrectData = data?.correct ?? [];
      serviceStep.value = true;
      await startDeployment();
    }
  } catch {
    serviceStep.value = false;
    importResult.value = false;
  } finally {
    loading.value = false;
  }
}

/** 阶段三：纳管主机 → 导入部署模板 → 等待 agent 就绪 → 进入安装 */
async function startDeployment() {
  loading.value = true;
  try {
    const hostList = (hostCorrectData ?? []).map(({ key: _key, ...rest }) => rest);
    await batchImportHosts(hostList as HostApi.BatchHostItem[]);
    await serviceImport();
  } catch {
    importStep.value = false;
    importResult.value = false;
  } finally {
    loading.value = false;
  }
}

async function serviceImport() {
  const instanceInfoLs = (hostCorrectData ?? []).map((item) => ({
    instance_name: item.instance_name,
    run_user: item.run_user,
  }));
  const serviceDataLs = (serviceCorrectData ?? []).map(
    ({ key: _key, ...rest }) => rest,
  );
  const data = await importDeploymentPlan({
    instance_info_ls: instanceInfoLs,
    service_data_ls: serviceDataLs as DeploymentPlanApi.ServiceDataItem[],
  });
  numInfo.value = data;
  importStep.value = true;
  importResult.value = true;
  // 导入成功即开始安装流程
  startInstall(data?.operation_uuid ?? '');
}

/** 每秒查询导入主机 agent 状态，全部在线即触发安装跳转 */
function startInstall(operationUuid: string) {
  const ipArr = (hostCorrectData ?? []).map((item) => item.ip);
  stopAgentTimer();
  hostAgentTimer = setInterval(() => {
    getHostsAgentStatus(ipArr)
      .then((ready) => {
        if (ready) {
          stopAgentTimer();
          doRetryInstall(operationUuid);
        }
      })
      .catch(() => {});
  }, 1000);
}

async function doRetryInstall(operationUuid: string) {
  try {
    await retryInstall(operationUuid);
    // 跳转安装流程页（目标页属安装编排批次，query 契约照旧前端 state 透传）
    router.push({
      path: '/application_management/app_store/installation',
      query: { step: '3', uniqueKey: operationUuid },
    });
  } catch {
    // 全局拦截器已提示
  }
}

// ── 校验失败表格列（照搬旧页 errorColumns / serviceErrorColumns） ────

const tooltipCell = ({ text }: any) =>
  h(Tooltip, { title: text }, { default: () => (text ? text : '-') });

const hostErrorColumns = [
  { title: '行数', dataIndex: 'row', key: 'row', width: 60, fixed: 'left' as const },
  {
    title: '实例名称',
    dataIndex: 'instance_name',
    key: 'instance_name',
    width: 120,
    customRender: tooltipCell,
  },
  {
    title: 'IP地址',
    dataIndex: 'ip',
    key: 'ip',
    width: 120,
    customRender: tooltipCell,
  },
  {
    title: '端口',
    dataIndex: 'port',
    key: 'port',
    width: 80,
    customRender: tooltipCell,
  },
  {
    title: '数据分区',
    dataIndex: 'data_folder',
    key: 'data_folder',
    width: 180,
    customRender: tooltipCell,
  },
  {
    title: '用户名',
    dataIndex: 'username',
    key: 'username',
    width: 120,
    customRender: tooltipCell,
  },
  {
    title: '运行用户',
    dataIndex: 'run_user',
    key: 'run_user',
    width: 120,
    customRender: tooltipCell,
  },
  {
    title: '失败原因',
    dataIndex: 'validate_error',
    key: 'validate_error',
    width: 240,
    fixed: 'right' as const,
    customRender: tooltipCell,
  },
];

const serviceErrorColumns = [
  {
    title: '行数',
    dataIndex: 'row',
    key: 'row',
    width: 60,
    fixed: 'left' as const,
    customRender: ({ text }: any) => (text < 1 ? '-' : text),
  },
  {
    title: '实例名称',
    dataIndex: 'instance_name',
    key: 'instance_name',
    width: 120,
    customRender: tooltipCell,
  },
  {
    title: '服务名称',
    dataIndex: 'service_name',
    key: 'service_name',
    width: 140,
    customRender: tooltipCell,
  },
  {
    title: '运行内存',
    dataIndex: 'memory',
    key: 'memory',
    width: 80,
    customRender: tooltipCell,
  },
  {
    title: '失败原因',
    dataIndex: 'validate_error',
    key: 'validate_error',
    width: 260,
    fixed: 'right' as const,
    customRender: tooltipCell,
  },
];

</script>

<template>
  <Modal
    :open="open"
    title="导入部署模板"
    :width="800"
    :footer="null"
    destroy-on-close
    @cancel="handleClose"
  >
    <Steps :current="stepNum" class="mb-8" size="small">
      <Steps.Step title="上传文件" />
      <Steps.Step title="导入结果" />
    </Steps>

    <!-- 步骤一：下载模板 + 上传解析 -->
    <div v-if="stepNum === 0">
      <div class="flex items-center">
        <div class="w-24 font-medium">下载模版:</div>
        <div class="flex-1 pl-4">
          <!-- 模板为 GET 文件流，浏览器直下（携带 JWT cookie） -->
          <a
            href="/api/appStore/deploymentTemplate/"
            class="inline-flex items-center gap-1"
            target="_blank"
          >
            <Button>点击下载</Button>
          </a>
        </div>
      </div>
      <div class="mt-8 flex">
        <div class="w-24 font-medium">上传文件:</div>
        <div class="flex-1 pl-4">
          <Upload.Dragger
            accept=".xlsx"
            class="block w-full"
            :before-upload="beforeUpload"
            :max-count="1"
            :multiple="false"
            @remove="handleRemove"
          >
            <p class="text-lg">☁</p>
            <p class="text-foreground">点击或将文件拖拽到这里上传</p>
            <p class="pt-2 text-[13px] text-muted-foreground">支持扩展名: .xlsx</p>
          </Upload.Dragger>
          <div class="mt-8 text-center">
            <Button
              :disabled="columnHeaders.length === 0"
              :loading="loading"
              type="primary"
              @click="clickImport"
            >
              开始导入
            </Button>
          </div>
        </div>
      </div>
    </div>

    <!-- 步骤二：三阶段链式导入状态 + 失败明细（照搬旧页三态：进行中/通过/未通过） -->
    <div v-else class="flex flex-col items-center pb-2">
      <p v-if="hostStep === null" class="flex items-center text-xl">
        <IconifyIcon
          icon="lucide:loader-circle"
          class="mr-2 text-2xl animate-spin"
        />
        正在校验主机数据 ...
      </p>
      <p v-else-if="hostStep === true" class="flex items-center text-xl">
        <IconifyIcon
          icon="lucide:circle-check"
          class="mr-2 text-3xl text-green-500"
        />
        主机数据校验通过
      </p>
      <p v-else class="flex items-center text-xl">
        <IconifyIcon
          icon="lucide:circle-x"
          class="mr-2 text-3xl text-red-500"
        />
        主机数据校验未通过
      </p>

      <template v-if="hostStep === true">
        <p v-if="serviceStep === null" class="flex items-center text-xl">
          <IconifyIcon
            icon="lucide:loader-circle"
            class="mr-2 text-2xl animate-spin"
          />
          正在校验服务数据 ...
        </p>
        <p v-else-if="serviceStep === true" class="flex items-center text-xl">
          <IconifyIcon
            icon="lucide:circle-check"
            class="mr-2 text-3xl text-green-500"
          />
          服务数据校验通过
        </p>
        <p v-else class="flex items-center text-xl">
          <IconifyIcon
            icon="lucide:circle-x"
            class="mr-2 text-3xl text-red-500"
          />
          服务数据校验未通过
        </p>
      </template>

      <template v-if="serviceStep === true">
        <p v-if="importStep === null" class="flex items-center text-xl">
          <IconifyIcon
            icon="lucide:loader-circle"
            class="mr-2 text-2xl animate-spin"
          />
          正在导入模板 ...
        </p>
        <p v-else-if="importStep === true" class="flex items-center text-xl">
          <IconifyIcon
            icon="lucide:circle-check"
            class="mr-2 text-3xl text-green-500"
          />
          部署模板导入成功
        </p>
        <p v-else class="flex items-center text-xl">
          <IconifyIcon
            icon="lucide:circle-x"
            class="mr-2 text-3xl text-red-500"
          />
          部署模板导入失败
        </p>
      </template>

      <Table
        v-if="hostErrorData.length > 0"
        :columns="hostErrorColumns"
        :data-source="hostErrorData"
        :pagination="{ pageSize: 5 }"
        :scroll="{ x: 700 }"
        bordered
        row-key="key"
        size="small"
      />

      <Table
        v-if="serviceErrorData.length > 0"
        :columns="serviceErrorColumns"
        :data-source="serviceErrorData"
        :pagination="{ pageSize: 5 }"
        :scroll="{ x: 700 }"
        bordered
        row-key="key"
        size="small"
      />

      <template v-if="importStep === true && numInfo">
        <p class="text-center">成功创建 {{ numInfo.host_num }} 台主机</p>
        <p class="text-center">
          本次共导入 {{ numInfo.product_num }} 个产品，{{
            numInfo.service_num
          }}
          个服务
        </p>
      </template>

      <!-- 导入成功：等待 agent 就绪自动进入安装 -->
      <p v-if="importResult === true" class="flex items-center text-base">
        <IconifyIcon
          icon="lucide:loader-circle"
          class="mr-2 animate-spin"
        />
        即将进入安装，请稍后 ...
      </p>

      <!-- 导入失败：回到上传步骤重新上传 -->
      <Button
        v-if="importResult === false"
        class="mt-6"
        @click="stepNum = 0"
      >
        重新上传
      </Button>
    </div>
  </Modal>
</template>
