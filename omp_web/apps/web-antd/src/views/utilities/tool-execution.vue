<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue';
import type { UploadFile } from 'ant-design-vue';

import { computed, onMounted, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Checkbox,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Select,
  Spin,
  Table,
  Tooltip,
  Upload,
} from 'ant-design-vue';
import { useRoute, useRouter } from 'vue-router';

import { executeToolForm, queryToolForm, queryToolTargetObject } from '#/api/utilities';
import type { UtilitiesApi } from '#/api/utilities';

defineOptions({ name: 'ToolExecution' });

const route = useRoute();
const router = useRouter();

const loading = ref(false);
const executing = ref(false);
const conf = ref<UtilitiesApi.ToolForm>();

const formRef = ref<FormInstance>();
const formState = reactive<Record<string, any>>({
  runuser: undefined,
  task_name: undefined,
  timeout: undefined,
});

/** 是否使用纳管用户（勾选后执行用户输入禁用） */
const isUseManagement = ref(true);
/** 执行对象校验错误提示 */
const showTargetError = ref(false);
/** 已选执行对象 */
const targetRows = ref<UtilitiesApi.TargetObject[]>([]);

/** 表单初始化（任务标题/超时/执行用户默认值 + 脚本参数默认值） */
function applyFormDefaults(data: UtilitiesApi.ToolForm) {
  isUseManagement.value = !data.default_form?.runuser;
  formState.task_name = data.default_form?.task_name ?? undefined;
  formState.timeout = data.default_form?.timeout ?? undefined;
  formState.runuser = data.default_form?.runuser ?? undefined;
  for (const arg of data.script_args ?? []) {
    formState[arg.key] = arg.type === 'file' ? [] : arg.default ?? undefined;
  }
}

async function queryConf() {
  loading.value = true;
  try {
    conf.value = await queryToolForm(route.params.id as string);
    applyFormDefaults(conf.value);
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

/** 超时时间校验：必填 + 正整数（与旧前端 validator 一致） */
const timeoutRules = [
  { message: '请输入超时时间', required: true },
  {
    validator: (_rule: unknown, value: number) =>
      !value || /^[1-9]\d*$/.test(String(value))
        ? Promise.resolve()
        : Promise.reject('请输入正整数'),
  },
];

function handleManagedUserChange(checked: boolean) {
  isUseManagement.value = checked;
  if (checked) {
    formState.runuser = undefined;
  }
}

// ── 扩展表单项（input / select / file） ───────────────────────

const UPLOAD_ACTION = '/api/common/upload_file/';

function beforeUpload(file: File) {
  const fileSize = file.size / 1024 / 1024;
  if (Math.ceil(fileSize) > 20) {
    message.error('仅支持传入20MB以内文件');
    return Upload.LIST_IGNORE;
  }
  return true;
}

// ── 执行对象选择弹窗 ──────────────────────────────────────────

const targetModalOpen = ref(false);
const targetLoading = ref(false);
const targetList = ref<UtilitiesApi.TargetObject[]>([]);
const targetPagination = reactive({ current: 1, pageSize: 10, total: 0 });
/** 弹窗内勾选（跨页保留，与旧页 checkedState 行为一致） */
const checkedRows = ref<UtilitiesApi.TargetObject[]>([]);

/** 扩展列：服务类工具的第一个对象带 modifiable_kwargs 时生成连接参数列 */
const targetColumns = computed(() => {
  const base = [
    { title: '实例名称', dataIndex: 'instance_name', key: 'instance_name', width: 150 },
    { title: 'IP地址', dataIndex: 'ip', key: 'ip', width: 120 },
    {
      title: 'Agent状态',
      dataIndex: 'host_agent_state',
      key: 'host_agent_state',
      width: 120,
    },
  ];
  const first = targetList.value[0];
  if (!first?.modifiable_kwargs) return base;
  const extend = Object.keys(first.modifiable_kwargs).map((key) => ({
    title: key,
    dataIndex: key,
    key,
    width: 150,
  }));
  return [...base, ...extend];
});

/** 行数据展开 modifiable_kwargs 供列渲染 */
function flattenTarget(row: UtilitiesApi.TargetObject) {
  return { ...row, ...row.modifiable_kwargs };
}

const rowSelection = computed(() => ({
  preserveSelectedRowKeys: true,
  selectedRowKeys: checkedRows.value.map((row) => row.id),
  onChange: (_keys: (number | string)[], rows: UtilitiesApi.TargetObject[]) => {
    // antd 只回传当前页行数据，跨页勾选需与既有选择合并
    const pageIds = new Set(targetList.value.map((row) => row.id));
    const kept = checkedRows.value.filter((row) => !pageIds.has(row.id));
    checkedRows.value = [...kept, ...rows];
  },
}));

const targetPaginationConfig = computed(() => ({
  current: targetPagination.current,
  defaultPageSize: targetPagination.pageSize,
  pageSize: targetPagination.pageSize,
  showSizeChanger: true,
  showTotal: (total: number) =>
    `已选中 ${checkedRows.value.length} 条 / 共计 ${total} 条`,
  total: targetPagination.total,
}));

async function queryTargetList(page = 1, pageSize?: number) {
  targetLoading.value = true;
  try {
    const res = await queryToolTargetObject(route.params.id as string, {
      page,
      size: pageSize ?? targetPagination.pageSize,
    });
    targetList.value = res.results;
    targetPagination.current = page;
    if (pageSize) targetPagination.pageSize = pageSize;
    targetPagination.total = res.count;
  } catch {
    // 全局拦截器已提示
  } finally {
    targetLoading.value = false;
    targetModalOpen.value = true;
  }
}

function openTargetModal() {
  checkedRows.value = [...targetRows.value];
  showTargetError.value = false;
  queryTargetList(1);
}

function handleTargetTableChange(pager: { current?: number; pageSize?: number }) {
  queryTargetList(
    pager.current ?? 1,
    pager.pageSize ?? targetPagination.pageSize,
  );
}

function confirmTargets() {
  targetRows.value = checkedRows.value;
  if (targetRows.value.length > 0) {
    showTargetError.value = false;
  }
  targetModalOpen.value = false;
}

function clearTargets() {
  targetRows.value = [];
  showTargetError.value = true;
}

function removeTarget(row: UtilitiesApi.TargetObject) {
  targetRows.value = targetRows.value.filter((item) => item.id !== row.id);
  if (targetRows.value.length === 0) showTargetError.value = true;
}

// ── 任务下发 ──────────────────────────────────────────────────

/** 从上传完成文件提取 {file_name, file_url, union_id}（后端响应包 data 字段） */
function extractUploadDefault(fileList: UploadFile[]) {
  const file = fileList?.[0];
  if (file && file.status === 'done') {
    const response = file.response as {
      code: number;
      data?: { file_name: string; file_url: string; union_id: string };
    };
    if (response?.code === 0 && response.data) {
      return {
        file_name: response.data.file_name,
        file_url: response.data.file_url,
        union_id: response.data.union_id,
      };
    }
  }
  return {};
}

function makePayload(): UtilitiesApi.FormAnswerPayload | null {
  const data = conf.value;
  if (!data) return null;
  return {
    default_form: {
      runuser: isUseManagement.value ? null : formState.runuser ?? null,
      target_objs: targetRows.value,
      task_name: formState.task_name,
      timeout: formState.timeout,
    },
    script_args: (data.script_args ?? []).map((item) => ({
      ...item,
      default:
        item.type === 'file'
          ? extractUploadDefault(formState[item.key])
          : formState[item.key],
    })),
  };
}

async function handleSubmit() {
  if (targetRows.value.length === 0) {
    showTargetError.value = true;
    return;
  }
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  const payload = makePayload();
  if (!payload) return;
  executing.value = true;
  try {
    const result = await executeToolForm(route.params.id as string, payload);
    message.success('执行命令下发成功');
    setTimeout(() => {
      router.push(
        `/utilitie/tool-management/tool-execution-results/${result.id}`,
      );
    }, 300);
  } catch {
    // 全局拦截器已提示（如必填参数缺失、对象数据异常）
  } finally {
    executing.value = false;
  }
}

onMounted(() => {
  queryConf();
});
</script>

<template>
  <Page>
    <div class="mb-3 flex items-center justify-between border-b border-border pb-3">
      <div class="text-base text-foreground">
        创建任务: {{ conf?.name || '-' }}
      </div>
      <Button @click="router.back()">返回</Button>
    </div>
    <Spin :spinning="loading">
      <Form
        ref="formRef"
        :label-col="{ style: { width: '110px' } }"
        :model="formState"
        class="max-w-[900px]"
        layout="horizontal"
        @finish="handleSubmit"
      >
        <FormItem
          label="任务标题"
          :rules="[{ message: '请输入任务标题', required: true }]"
          name="task_name"
        >
          <div class="max-w-[460px]">
            <Input v-model:value="formState.task_name" placeholder="请输入任务标题" />
          </div>
        </FormItem>

        <FormItem label="执行对象" required>
          <div class="w-full max-w-[800px]">
            <div
              class="relative flex min-h-[80px] flex-wrap gap-2.5 bg-muted p-2.5 pb-10"
              :class="showTargetError ? 'border border-red-400' : ''"
            >
              <span
                v-for="item in targetRows"
                :key="item.id"
                class="flex h-7 max-w-[220px] items-center overflow-hidden whitespace-nowrap rounded border border-border bg-card pl-4 text-sm"
              >
                <span class="truncate" :title="item.instance_name">
                  {{ item.instance_name }}
                </span>
                <IconifyIcon
                  class="ml-2 cursor-pointer px-1 text-muted-foreground hover:text-foreground"
                  icon="lucide:x"
                  @click="removeTarget(item)"
                />
              </span>
              <div class="absolute bottom-2.5 left-1/2 flex -translate-x-1/2 gap-4">
                <Button size="small" @click="clearTargets">清除</Button>
                <Button size="small" @click="openTargetModal">添加</Button>
              </div>
            </div>
            <div
              class="overflow-hidden text-red-400 transition-all"
              :class="showTargetError ? 'h-5' : 'h-0'"
            >
              请选择执行对象
            </div>
          </div>
        </FormItem>

        <FormItem
          label="超时时间"
          :rules="timeoutRules"
          name="timeout"
        >
          <div class="flex items-center">
            <InputNumber v-model:value="formState.timeout" :min="1" />
            <span class="pl-1.5">秒</span>
            <Tooltip
              title="工具在目标主机执行的超时时间，超过该时间后，任务将退出"
            >
              <IconifyIcon
                class="ml-5 align-middle text-gray-400"
                icon="lucide:circle-help"
              />
            </Tooltip>
          </div>
        </FormItem>

        <FormItem
          label="执行用户"
          :rules="
            isUseManagement
              ? []
              : [{ message: '请输入执行用户', required: true }]
          "
          name="runuser"
        >
          <div class="flex items-center">
            <Input
              v-model:value="formState.runuser"
              :disabled="isUseManagement"
              :style="{ width: '140px' }"
              placeholder="请输入执行用户"
            />
            <span class="pl-4">
              <Checkbox
                :checked="isUseManagement"
                @change="(e: any) => handleManagedUserChange(e.target.checked)"
              >
                使用纳管用户
              </Checkbox>
              <Tooltip
                title="工具在目标主机执行的用户名，请确保具有相应用户权限"
              >
                <IconifyIcon
                  class="ml-4 align-middle text-gray-400"
                  icon="lucide:circle-help"
                />
              </Tooltip>
            </span>
          </div>
        </FormItem>

        <template v-for="item in conf?.script_args ?? []" :key="item.key">
          <FormItem
            :label="item.name"
            :name="item.key"
            :rules="[
              {
                message:
                  item.type === 'file'
                    ? `请将文件传入${item.name}`
                    : `请输入${item.name}`,
                required: item.required,
              },
            ]"
          >
            <div v-if="item.type === 'input'" class="max-w-[460px]">
              <Input
                v-model:value="formState[item.key]"
                :placeholder="`请输入${item.name}`"
              />
            </div>
            <Select
              v-else-if="item.type === 'select'"
              v-model:value="formState[item.key]"
              :options="(item.options ?? []).map((option) => ({ label: option, value: option }))"
              :placeholder="`请选择${item.name}`"
              allow-clear
              :style="{ width: '460px' }"
            />
            <Upload
              v-else-if="item.type === 'file'"
              v-model:file-list="formState[item.key]"
              :action="UPLOAD_ACTION"
              :before-upload="beforeUpload"
              :data="{ module: 'ToolInfo', module_id: route.params.id }"
              :max-count="1"
              name="file"
            >
              <Button>点击上传</Button>
            </Upload>
          </FormItem>
        </template>

        <div class="flex justify-center pt-6">
          <Button
            html-type="submit"
            :loading="executing"
            type="primary"
          >
            执行
          </Button>
        </div>
      </Form>
    </Spin>

    <Modal
      :footer="null"
      :open="targetModalOpen"
      :width="800"
      title="选择执行对象"
      @cancel="targetModalOpen = false"
    >
      <Table
        :columns="targetColumns"
        :data-source="targetList.map(flattenTarget)"
        :loading="targetLoading"
        :pagination="targetPaginationConfig"
        :row-key="(record: any) => record.id"
        :row-selection="rowSelection"
        size="small"
        @change="handleTargetTableChange"
      />
      <div class="mt-6 flex justify-center gap-5">
        <Button @click="targetModalOpen = false">取消</Button>
        <Button type="primary" @click="confirmTargets">确认</Button>
      </div>
    </Modal>
  </Page>
</template>
