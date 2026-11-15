<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue';

import { h, reactive, ref } from 'vue';

import { message, Button, Form, FormItem, Input, Modal, Table, Tooltip } from 'ant-design-vue';

import {
  createBackupCustom,
  deleteBackupCustom,
  queryBackupCustom,
  queryBackupRepeatCustom,
  updateBackupCustom,
} from '#/api/data-backup';
import type { DataBackupApi } from '#/api/data-backup';

defineOptions({ name: 'BackupCustomParamsModal' });

const emit = defineEmits<{ changed: [] }>();

const open = ref(false);
const loading = ref(false);

/** 表格行（带前端序号） */
type CustomRow = DataBackupApi.BackupCustomParam & { _idx: number };

/** 全量自定义参数（搜索为前端过滤，与旧页一致） */
const customList = ref<CustomRow[]>([]);
/** 搜索过滤后的列表 */
const filteredList = ref<CustomRow[]>([]);
const searchName = ref('');

const columns = [
  { title: '序号', dataIndex: '_idx', key: '_idx', width: 60 },
  { title: '名称', dataIndex: 'field_k', key: 'field_k', width: 100 },
  { title: '值', dataIndex: 'field_v', key: 'field_v' },
  { title: '备注', dataIndex: 'notes', key: 'notes', width: 120 },
  { title: '操作', dataIndex: 'action', key: 'action', width: 100 },
];

async function queryList() {
  loading.value = true;
  try {
    const list = await queryBackupCustom();
    customList.value = list.map((item, idx) => ({ ...item, _idx: idx + 1 }));
    applySearch();
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

/** 按名称前端过滤（旧页为回车触发，这里回车与输入即时同步） */
function applySearch() {
  filteredList.value = searchName.value
    ? customList.value.filter((item) => item.field_k.includes(searchName.value))
    : customList.value;
}

function handleSearchChange(value: string) {
  searchName.value = value;
  if (!value) applySearch();
}

/** 打开弹窗并刷新列表 */
async function openModal() {
  open.value = true;
  searchName.value = '';
  await queryList();
}

defineExpose({ open: openModal });

// ── 添加 / 编辑参数 ────────────────────────────────────────────

const editOpen = ref(false);
const editType = ref<'add' | 'update'>('add');
const editingRow = ref<DataBackupApi.BackupCustomParam | null>(null);
const editSaving = ref(false);
const editFormRef = ref<FormInstance>();
const editFormState = reactive({
  field_k: '',
  field_v: '',
  notes: '',
});

function openEdit(type: 'add' | 'update', row?: CustomRow) {
  editType.value = type;
  editingRow.value = row ?? null;
  Object.assign(editFormState, {
    field_k: row?.field_k ?? '',
    field_v: row?.field_v ?? '',
    notes: row?.notes ?? '',
  });
  editOpen.value = true;
}

/** 组装请求体（空备注传空串，与后端 allow_blank 契约一致） */
function makeEditPayload() {
  return {
    field_k: editFormState.field_k,
    field_v: editFormState.field_v,
    notes: editFormState.notes ?? '',
  };
}

async function handleEditSubmit() {
  try {
    await editFormRef.value?.validate();
  } catch {
    return;
  }
  editSaving.value = true;
  try {
    if (editType.value === 'add') {
      await createBackupCustom(makeEditPayload());
      message.success('添加自定义参数成功');
      editOpen.value = false;
      await queryList();
      emit('changed');
    } else {
      await submitUpdate(makeEditPayload());
    }
  } catch {
    // 全局拦截器已提示（如「自定义参数不可重复」）
  } finally {
    editSaving.value = false;
  }
}

/** 修改参数：存在实例使用时先二次确认（与旧页 updateCustomInfo 一致） */
async function submitUpdate(payload: {
  field_k: string;
  field_v: string;
  notes: string;
}) {
  const row = editingRow.value;
  if (!row) return;
  const repeatName = await queryBackupRepeatCustom(row.id);
  if (repeatName) {
    Modal.confirm({
      content: () =>
        h('div', [
          h('span', '该参数 '),
          h('span', { class: 'font-medium text-red-500' }, repeatName),
          h('span', ' 实例正在使用'),
          h('br'),
          h('span', '确认'),
          h('span', { class: 'font-medium' }, '修改'),
          h('span', '该参数吗？'),
        ]),
      okText: '确定',
      cancelText: '取消',
      onOk: async () => {
        await doUpdate(payload);
      },
      title: '提示',
    });
    return;
  }
  await doUpdate(payload);
}

async function doUpdate(payload: {
  field_k: string;
  field_v: string;
  notes: string;
}) {
  const row = editingRow.value;
  if (!row) return;
  await updateBackupCustom(row.id, payload);
  message.success('修改自定义参数成功');
  editOpen.value = false;
  await queryList();
  // 自定义参数变更影响策略展示，通知父页面刷新策略列表（旧页同步刷新）
  emit('changed');
}

// ── 删除参数 ──────────────────────────────────────────────────

/** 删除参数：展示占用实例名后二次确认（与旧页 deleteCustomInfo 一致） */
async function confirmDelete(row: CustomRow) {
  const repeatName = await queryBackupRepeatCustom(row.id);
  Modal.confirm({
    content: () => [
      ...(repeatName
        ? [
            h('span', '该参数 '),
            h('span', { class: 'font-medium text-red-500' }, repeatName),
            h('span', ' 实例正在使用'),
            h('br'),
          ]
        : []),
      h('span', '确认'),
      h('span', { class: 'font-medium' }, '删除'),
      h('span', '该参数吗？'),
    ],
    okText: '确定',
    cancelText: '取消',
    onOk: async () => {
      await deleteBackupCustom(row.id);
      message.success('删除成功');
      await queryList();
      emit('changed');
    },
    title: '提示',
  });
}
</script>

<template>
  <Modal
    :footer="null"
    :open="open"
    :width="860"
    title="自定义参数"
    @cancel="open = false"
  >
    <div class="mb-2.5 flex items-center justify-between">
      <Input
        :value="searchName"
        allow-clear
        placeholder="请输入名称"
        :style="{ width: '220px' }"
        @change="(e: any) => handleSearchChange(e.target.value)"
        @press-enter="applySearch"
      />
      <Button type="primary" @click="openEdit('add')">添加参数</Button>
    </div>
    <Table
      :columns="columns"
      :data-source="filteredList"
      :loading="loading"
      :pagination="false"
      :scroll="{ y: 270 }"
      size="small"
      row-key="id"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'field_k'">
          <Tooltip :title="record.field_k">
            <span>{{ record.field_k || '-' }}</span>
          </Tooltip>
        </template>
        <template v-else-if="column.key === 'field_v'">
          {{ record.field_v }}
        </template>
        <template v-else-if="column.key === 'notes'">
          <Tooltip :title="record.notes">
            <span>{{ record.notes || '-' }}</span>
          </Tooltip>
        </template>
        <template v-else-if="column.key === 'action'">
          <a @click="openEdit('update', record)">编辑</a>
          <a class="ml-2.5" @click="confirmDelete(record)">删除</a>
        </template>
      </template>
    </Table>
    <div class="mt-5 flex justify-center">
      <Button @click="open = false">返回</Button>
    </div>
  </Modal>

  <Modal
    :confirm-loading="editSaving"
    :open="editOpen"
    :title="editType === 'add' ? '添加自定义参数' : '编辑自定义参数'"
    :width="580"
    cancel-text="取消"
    destroy-on-close
    ok-text="确定"
    @cancel="editOpen = false"
    @ok="handleEditSubmit"
  >
    <Form ref="editFormRef" :model="editFormState" layout="vertical">
      <FormItem
        label="参数名称"
        :rules="[{ message: '请输入参数名称', required: true }]"
        name="field_k"
      >
        <Input
          v-model:value="editFormState.field_k"
          :disabled="editType === 'update'"
          :maxlength="64"
          placeholder="请输入参数名称"
        />
      </FormItem>
      <FormItem
        label="参数值"
        :rules="[{ message: '请输入参数值', required: true }]"
        name="field_v"
      >
        <Input.TextArea
          v-model:value="editFormState.field_v"
          :maxlength="256"
          :rows="4"
          placeholder="请输入参数值"
        />
      </FormItem>
      <FormItem label="备注" name="notes">
        <Input
          v-model:value="editFormState.notes"
          :maxlength="32"
          placeholder="请输入备注"
        />
      </FormItem>
    </Form>
  </Modal>
</template>
