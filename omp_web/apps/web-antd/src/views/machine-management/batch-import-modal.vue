<script lang="ts" setup>
import type { UploadProps } from 'ant-design-vue';

import type { HostApi } from '#/api/hosts';

import { h, ref } from 'vue';

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

import { batchImportHosts, batchValidateHosts } from '#/api/hosts';
import { useEnvStore } from '#/store';

import { IconifyIcon } from '@vben/icons';

defineOptions({ name: 'BatchImportModal' });

const emit = defineEmits<{ success: [] }>();

/** 当前环境上下文：导入不选环境，主机自动落在当前环境（后端按请求环境继承） */
const envStore = useEnvStore();

const open = ref(false);
/** 0 上传文件 1 数据校验 2 创建结果 */
const stepNum = ref(0);
const loading = ref(false);

/** xlsx 原始解析结果（校验请求体映射前） */
const dataSource = ref<Record<string, any>[]>([]);
/** 解析出的列头（过滤「请勿编辑/UNKNOWN」占位列后） */
const columnHeaders = ref<string[]>([]);

/** 校验结果（成功/失败两套数据源互斥展示；correct 行带前端下标 key） */
const tableCorrectData = ref<(HostApi.BatchHostItem & { key: number })[]>([]);
const tableErrorData = ref<Record<string, any>[]>([]);

function resetState() {
  dataSource.value = [];
  columnHeaders.value = [];
  tableCorrectData.value = [];
  tableErrorData.value = [];
  stepNum.value = 0;
}

function openModal() {
  resetState();
  open.value = true;
}

defineExpose({ open: openModal });

function handleClose() {
  open.value = false;
  // 关闭即刷新列表（照搬旧页 afterClose → refreshData 契约）
  emit('success');
}

// ── xlsx 前端解析（照搬旧页 UploadExcelComponent 契约） ─────────

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
      const workbook = xlsxRead(e.target?.result as ArrayBuffer, {
        type: 'array',
      });
      const worksheet = workbook.Sheets[workbook.SheetNames[0]!] as any;
      const header = getHeaderRow(worksheet);
      const results = xlsxUtils.sheet_to_json(worksheet) as Record<
        string,
        any
      >[];
      handleParsed(header, results);
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

function handleParsed(header: string[], results: Record<string, any>[]) {
  // 模板说明行（字段名称(请勿编辑)）与空实例名行不进数据源
  const rows = results
    .filter((item) => {
      if (String(item['字段名称(请勿编辑)'] ?? '').includes('请勿编辑')) {
        return false;
      }
      return Boolean(item['实例名[必填]']);
    })
    .map((item) => ({ ...item, key: (item.__rowNum__ ?? 0) + 1 }));
  const columns = header.filter(
    (item) =>
      !(item?.includes('请勿编辑') || item?.includes('UNKNOWN')),
  );
  dataSource.value = rows;
  columnHeaders.value = columns;
}

function handleRemove() {
  dataSource.value = [];
  columnHeaders.value = [];
  tableCorrectData.value = [];
  tableErrorData.value = [];
}

// ── 数据校验（中文列头 → 英文字段映射，照搬旧页契约） ───────────

const FIELD_MAP: Record<string, (item: Record<string, any>, row: any) => void> = {
  'IP[必填]': (item, row) => (item.ip = row),
  '实例名[必填]': (item, row) => (item.instance_name = row),
  '密码[必填]': (item, row) => (item.password = row),
  '操作系统[必填]': (item, row) => (item.operate_system = row),
  '数据分区[必填]': (item, row) => (item.data_folder = row),
  '用户名[必填]': (item, row) => (item.username = row),
  '端口[必填]': (item, row) => (item.port = row),
  '时间同步服务器': (item, row) => {
    item.use_ntpd = true;
    item.ntpd_server = row;
  },
};

function buildQueryBody() {
  return dataSource.value.map((item) => {
    const result: Record<string, any> = {};
    for (const key in item) {
      FIELD_MAP[key]?.(result, item[key]);
    }
    if (!result.use_ntpd) result.use_ntpd = false;
    return { ...result, row: item.key };
  });
}

/** 校验按钮：解析结果为空直接提示 */
async function handleValidate() {
  if (dataSource.value.length === 0) {
    message.warning('解析结果中无有效数据，请确保文件内容格式符合规范后重新上传');
    return;
  }
  loading.value = true;
  tableCorrectData.value = [];
  tableErrorData.value = [];
  try {
    const data = await batchValidateHosts(
      buildQueryBody() as HostApi.BatchHostItem[],
    );
    if (data?.error?.length && data.error.length > 0) {
      tableErrorData.value = data.error.map((item, idx) => ({
        key: idx,
        ...item,
      }));
    } else {
      tableCorrectData.value = (data?.correct ?? []).map((item, idx) => ({
        ...item,
        key: idx,
      }));
    }
    stepNum.value = 1;
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

/** 校验通过后创建主机 */
async function handleImport() {
  const queryBody = tableCorrectData.value.map((item) => {
    const { key: _key, ...rest } = item;
    return rest;
  });
  loading.value = true;
  try {
    await batchImportHosts(queryBody);
    stepNum.value = 2;
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

// ── 校验结果表格列（照搬旧页 correct/error 两套 columns） ────────

const tooltipCell = ({ text }: any) =>
  h(Tooltip, { title: text }, { default: () => (text ? text : '-') });

const errorColumns = [
  { title: '行数', dataIndex: 'row', key: 'row', width: 60, fixed: 'left' as const },
  {
    title: '实例名称',
    dataIndex: 'instance_name',
    key: 'instance_name',
    width: 140,
    customRender: tooltipCell,
  },
  {
    title: 'IP地址',
    dataIndex: 'ip',
    key: 'ip',
    width: 140,
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
    title: '是否安装时间同步',
    dataIndex: 'use_ntpd',
    key: 'use_ntpd',
    width: 120,
    customRender: ({ text }: any) =>
      text === false ? '否' : text === true ? '是' : '-',
  },
  {
    title: '时间同步服务器',
    dataIndex: 'ntpd_server',
    key: 'ntpd_server',
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

const correctColumns = [
  {
    title: '实例名称',
    dataIndex: 'instance_name',
    key: 'instance_name',
    width: 140,
    fixed: 'left' as const,
    customRender: tooltipCell,
  },
  {
    title: 'IP地址',
    dataIndex: 'ip',
    key: 'ip',
    width: 140,
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
    title: '密码',
    dataIndex: 'password',
    key: 'password',
    width: 130,
    customRender: tooltipCell,
  },
  {
    title: '是否安装时间同步',
    dataIndex: 'use_ntpd',
    key: 'use_ntpd',
    width: 120,
    customRender: ({ text }: any) =>
      text === false ? '否' : text === true ? '是' : '-',
  },
  {
    title: '时间同步服务器',
    dataIndex: 'ntpd_server',
    key: 'ntpd_server',
    width: 120,
    customRender: tooltipCell,
  },
  {
    title: '系统',
    dataIndex: 'operate_system',
    key: 'operate_system',
    width: 120,
    fixed: 'right' as const,
    customRender: tooltipCell,
  },
];
</script>

<template>
  <Modal
    :open="open"
    title="批量创建主机"
    :width="800"
    :footer="null"
    destroy-on-close
    @cancel="handleClose"
  >
    <Steps :current="stepNum" class="!mb-8" size="small">
      <Steps.Step title="上传文件" />
      <Steps.Step title="数据校验" />
      <Steps.Step title="创建结果" />
    </Steps>

    <!-- 多环境：批量导入落在当前环境，无需（也无法）在弹窗内选择环境 -->
    <p class="-mt-4 pb-1 text-center text-[13px] text-muted-foreground">
      导入至当前环境：{{ envStore.currentEnv?.name ?? '-' }}
    </p>

    <!-- 步骤一：下载模板 + 上传解析 -->
    <div v-if="stepNum === 0">
      <div class="flex items-center">
        <div class="w-24 font-medium">下载模版:</div>
        <div class="flex-1 pl-4">
          <!-- 模板与初始化脚本同为 GET 文件流，浏览器直下（携带 JWT cookie） -->
          <a
            href="/api/hosts/batchValidate/"
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
            <p class="flex justify-center text-3xl text-primary">
              <IconifyIcon icon="lucide:cloud-upload" />
            </p>
            <p class="text-foreground">点击或将文件拖拽到这里上传</p>
            <p class="pt-2 text-[13px] text-muted-foreground">支持扩展名: .xlsx</p>
          </Upload.Dragger>
          <div class="mt-8 text-center">
            <Button
              :disabled="columnHeaders.length === 0"
              :loading="loading"
              type="primary"
              @click="handleValidate"
            >
              校验
            </Button>
          </div>
        </div>
      </div>
    </div>

    <!-- 步骤二：校验结果（失败表格优先展示） -->
    <div v-else-if="stepNum === 1">
      <div
        v-if="tableErrorData.length > 0"
        class="flex flex-col items-center pb-2"
      >
        <p class="flex items-center text-xl text-red-500">
          <span class="mr-2 text-3xl">✕</span>
          数据校验失败 !
        </p>
        <p class="text-[13px]">请核对并修改信息后，再重新提交</p>
      </div>
      <div v-else class="flex items-center justify-center pb-2">
        <p class="flex items-center text-xl">
          <span class="mr-2 text-3xl text-green-500">✓</span>
          数据校验成功 !
        </p>
      </div>

      <Table
        :columns="tableErrorData.length > 0 ? errorColumns : correctColumns"
        :data-source="tableErrorData.length > 0 ? tableErrorData : tableCorrectData"
        :pagination="{ pageSize: 5 }"
        :scroll="{ x: 700 }"
        bordered
        row-key="key"
        size="small"
      />
      <div class="mt-8 text-center">
        <Button class="mr-4" @click="stepNum = 0">上一步</Button>
        <Button
          :disabled="tableErrorData.length > 0"
          :loading="loading"
          type="primary"
          @click="handleImport"
        >
          创建
        </Button>
      </div>
    </div>

    <!-- 步骤三：创建结果 -->
    <div v-else>
      <div class="flex items-center justify-center pb-4 pt-6">
        <p class="flex items-center text-xl">
          <span class="mr-2 text-3xl text-green-500">✓</span>
          主机创建完成 !
        </p>
      </div>
      <p class="text-center">本次共创建 {{ tableCorrectData.length }} 台主机</p>
      <div class="mt-8 text-center">
        <Button :loading="loading" type="primary" @click="handleClose">
          完成
        </Button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
/* antdv 的 upload wrapper 是 span（inline），嵌进 flex 布局会因
   block-in-inline 拆分导致内容溢出容器（校验按钮被顶到弹框外）；
   class 已块级化 wrapper，这里补回拖拽区的舒适高度（对齐旧版 176px 观感） */
:deep(.ant-upload-drag) {
  padding: 32px 0;
}
</style>
