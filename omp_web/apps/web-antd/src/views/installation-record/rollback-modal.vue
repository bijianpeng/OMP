<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import { computed, shallowRef, watch } from 'vue';

import { Input, message, Modal, Table, Tooltip } from 'ant-design-vue';

import type { ExecutionRecordApi } from '#/api/execution-record';

import { doRollback, listCanRollback } from '#/api/execution-record';

defineOptions({ name: 'ServiceRollbackModal' });

/** 回滚选择表行：分组行为应用名聚合，叶子行为可回滚实例 */
interface RollbackRow {
  afterVersion: string;
  beforeVersion: string;
  children?: RollbackRow[];
  id: number | string;
  instanceName: string;
  isParent: boolean;
}

const props = defineProps<{
  /** 来源升级记录 id（ExecutionRecord.module_id，限定可回滚范围） */
  historyId: null | number | string;
}>();

const emit = defineEmits<{
  /** 回滚下发成功，携带新建的回滚历史 id（父组件跳转服务回滚页） */
  submitted: [history: number];
}>();

/** 弹窗开关（父组件 v-model:open 控制） */
const open = defineModel<boolean>('open', { default: false });

const columns: TableColumnsType = [
  {
    title: '名称',
    dataIndex: 'instanceName',
    key: 'instanceName',
    ellipsis: true,
  },
  {
    title: '当前版本',
    dataIndex: 'beforeVersion',
    key: 'beforeVersion',
    align: 'center',
    width: 130,
  },
  {
    title: '回滚版本',
    dataIndex: 'afterVersion',
    key: 'afterVersion',
    align: 'center',
    width: 130,
  },
];

const fetchLoading = shallowRef(false);
const submitting = shallowRef(false);
const searchValue = shallowRef('');

const rows = shallowRef<RollbackRow[]>([]);
const selectedKeys = shallowRef<Array<number | string>>([]);

/** 叶子实例总数（分组行不计） */
const totalLeafCount = computed(() =>
  rows.value.reduce((sum, group) => sum + (group.children?.length ?? 0), 0),
);
/** 已选叶子实例数 */
const selectedLeafCount = computed(
  () => rows.value.filter((row) => !row.isParent && selectedKeys.value.includes(row.id))
    .length,
);

/** 分组行版本聚合：子实例版本全部一致才展示，否则显示 - */
function toRows(groups: ExecutionRecordApi.RollbackChoiceGroup[]): RollbackRow[] {
  return groups.map((group) => {
    const children = group.children ?? [];
    const beforeVersions = new Set(children.map((item) => item.before_rollback_v));
    const afterVersions = new Set(children.map((item) => item.after_rollback_v));
    return {
      id: group.app_name,
      instanceName: group.app_name,
      beforeVersion:
        beforeVersions.size === 1 ? children[0]?.before_rollback_v ?? '-' : '-',
      afterVersion:
        afterVersions.size === 1 ? children[0]?.after_rollback_v ?? '-' : '-',
      isParent: true,
      children: children.map((item) => ({
        id: item.id,
        instanceName: item.instance_name,
        beforeVersion: item.before_rollback_v || '-',
        afterVersion: item.after_rollback_v || '-',
        isParent: false,
      })),
    };
  });
}

async function queryRows() {
  fetchLoading.value = true;
  try {
    const data = await listCanRollback({
      history_id: props.historyId,
      search: searchValue.value || null,
    });
    rows.value = toRows(data?.results ?? []);
    selectedKeys.value = [];
  } catch {
    // requestClient 已统一提示错误
  } finally {
    fetchLoading.value = false;
  }
}

// 打开时拉取可回滚列表；关闭时清空搜索与勾选
watch(open, (value) => {
  if (value) {
    searchValue.value = '';
    queryRows();
  } else {
    rows.value = [];
    selectedKeys.value = [];
  }
});

/** 清空搜索词时自动重查（对齐旧弹窗 allowClear 行为） */
function handleSearchChange(event: { target: { value?: string } }) {
  if (!event.target.value) {
    queryRows();
  }
}

/** 级联勾选（checkStrictly=false）：onChange 返回含分组行，需过滤出叶子实例 */
function handleSelectionChange(keys: Array<number | string>) {
  selectedKeys.value = keys;
}

async function handleOk() {
  const choices = rows.value
    .flatMap((group) => group.children ?? [])
    .filter((item) => selectedKeys.value.includes(item.id))
    .map((item) => Number(item.id));
  submitting.value = true;
  try {
    const data = await doRollback(choices);
    message.success('回滚任务已下发');
    open.value = false;
    if (data?.history) {
      emit('submitted', data.history);
    }
  } catch {
    // requestClient 已统一提示错误
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Modal
    v-model:open="open"
    :confirm-loading="submitting"
    :ok-button-props="{ disabled: selectedLeafCount === 0 }"
    :ok-text="'确认选择'"
    :title="'服务回滚-选择应用服务'"
    :width="600"
    @ok="handleOk"
  >
    <div class="flex justify-end mb-3.5">
      <Input
        v-model:value="searchValue"
        allow-clear
        placeholder="请输入服务名称"
        style="width: 180px"
        @press-enter="queryRows"
        @change="handleSearchChange"
      />
    </div>
    <Table
      :columns="columns"
      :data-source="rows"
      :loading="fetchLoading || submitting"
      :pagination="false"
      :row-key="(row) => row.id"
      :row-selection="{
        checkStrictly: false,
        selectedRowKeys: selectedKeys,
        onChange: handleSelectionChange,
      }"
      :scroll="{ y: 300 }"
      size="small"
    >
      <template #bodyCell="{ column, text }">
        <template v-if="column.key === 'instanceName'">
          <Tooltip :title="String(text ?? '')">
            <span>{{ text }}</span>
          </Tooltip>
        </template>
      </template>
    </Table>
    <div class="flex justify-end mt-5 px-5 gap-4">
      <span>已选择 {{ selectedLeafCount }} 个</span>
      <span>共 {{ totalLeafCount }} 个</span>
    </div>
  </Modal>
</template>
