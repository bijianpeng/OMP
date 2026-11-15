<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { RuleCenterApi } from '#/api/rule-center';

import { computed, reactive, ref } from 'vue';

import { Badge, Button, Modal, Table, Tooltip } from 'ant-design-vue';

import type { HostApi } from '#/api/hosts';

import { listHosts } from '#/api/hosts';

defineOptions({ name: 'RuleExtendHostSelectModal' });

const emit = defineEmits<{
  confirm: [hosts: HostApi.HostRecord[]];
}>();

/** 主机 Agent 状态（与旧前端 renderStatus 一致） */
const AGENT_STATUS: Record<
  number,
  { color: 'default' | 'error' | 'processing' | 'success' | 'warning'; text: string }
> = {
  0: { color: 'success', text: '正常' },
  1: { color: 'warning', text: '重启中' },
  2: { color: 'error', text: '启动失败' },
  3: { color: 'warning', text: '部署中' },
  4: { color: 'error', text: '部署失败' },
};

const open = ref(false);
const loading = ref(false);
const hostList = ref<HostApi.HostRecord[]>([]);
const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
});

/** 跨页勾选状态（preserveSelectedRowKeys 保留非当前页选中行） */
const selectedKeys = ref<(number | string)[]>([]);
const selectedRows = ref<HostApi.HostRecord[]>([]);

const columns: TableColumnsType = [
  {
    dataIndex: 'instance_name',
    ellipsis: true,
    key: 'instance_name',
    title: '实例名称',
    width: 180,
  },
  { dataIndex: 'ip', ellipsis: true, key: 'ip', title: 'IP地址', width: 140 },
  { dataIndex: 'host_agent', key: 'host_agent', title: '主机Agent', width: 120 },
];

async function queryHostList(
  page: { current: number; pageSize: number } = {
    current: pagination.current,
    pageSize: pagination.pageSize,
  },
) {
  loading.value = true;
  try {
    const data = await listHosts({
      page: page.current,
      size: page.pageSize,
    });
    hostList.value = data.results ?? [];
    pagination.total = data.count ?? 0;
    pagination.current = page.current;
    pagination.pageSize = page.pageSize;
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

/**
 * 打开弹窗：initialHostIps 为已绑定主机 IP（打开时预选中，跨页保留）。
 */
function openModal(initialHostIps: string[] = []) {
  const initial = new Set(initialHostIps);
  open.value = true;
  selectedKeys.value = [];
  selectedRows.value = [];
  loading.value = true;
  queryHostList({ current: 1, pageSize: pagination.pageSize }).finally(() => {
    // 数据到达后回显已绑定主机
    const matched = hostList.value.filter((item) => initial.has(item.ip ?? ''));
    selectedKeys.value = matched.map((item) => item.id);
    selectedRows.value = matched;
  });
}

defineExpose({ open: openModal });

function handleSelectionChange(
  keys: (number | string)[],
  rows: HostApi.HostRecord[],
) {
  selectedKeys.value = [...keys];
  selectedRows.value = rows;
}

/** 分页/翻页回调（模板表达式不支持 TS 标注，收敛到 script） */
const paginationConfig = computed(() => ({
  current: pagination.current,
  onChange: (page: number, pageSize: number) =>
    queryHostList({ current: page, pageSize }),
  pageSize: pagination.pageSize,
  pageSizes: [10, 20, 50, 100] as number[],
  showSizeChanger: true,
  showTotal: (total: number, range: [number, number]) =>
    `已选中 ${selectedRows.value.length} 条，第 ${range[0]}-${range[1]} 条 / 共计 ${total} 条`,
  total: pagination.total,
}));

const rowKey = (record: HostApi.HostRecord) => record.id;

const rowSelection = computed(() => ({
  onChange: handleSelectionChange,
  preserveSelectedRowKeys: true,
  selectedRowKeys: selectedKeys.value,
}));

function handleConfirm() {
  emit('confirm', [...selectedRows.value]);
  open.value = false;
}
</script>

<template>
  <Modal
    :footer="null"
    :open="open"
    :width="800"
    title="选择绑定主机"
    @cancel="open = false"
  >
    <Table
      :columns="columns"
      :data-source="hostList"
      :loading="loading"
      :pagination="paginationConfig"
      :row-key="rowKey"
      :row-selection="rowSelection"
      size="small"
    >
      <template #bodyCell="{ column, text }">
        <template v-if="column.key === 'instance_name' || column.key === 'ip'">
          <Tooltip :title="text || '-'" placement="topLeft">
            <span>{{ text || '-' }}</span>
          </Tooltip>
        </template>
        <template v-else-if="column.key === 'host_agent'">
          <Badge
            :status="AGENT_STATUS[text as number]?.color ?? 'default'"
            :text="AGENT_STATUS[text as number]?.text ?? '-'"
          />
        </template>
      </template>
    </Table>
    <div class="mt-4 flex justify-center gap-4">
      <Button @click="open = false">取消</Button>
      <Button type="primary" @click="handleConfirm">确认</Button>
    </div>
  </Modal>
</template>
