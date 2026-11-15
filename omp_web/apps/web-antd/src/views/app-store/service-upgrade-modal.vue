<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { ExecutionRecordApi } from '#/api/execution-record';

import { computed, shallowRef, watch } from 'vue';

import { Input, Modal, Table, Tooltip } from 'ant-design-vue';

import { doUpgrade, listCanUpgrade } from '#/api/execution-record';

/**
 * 服务升级选择弹窗（商店更多菜单「服务升级」入口）。
 * 应用名分组树形展示可升级实例（仅最高可升版本），提交 doUpgrade 下发
 * 升级命令后跳服务升级页（父组件经 submitted 事件跳转）。
 * 旧实现 omp_web/src/pages/AppStore/config/ServiceUpgradeModal.js 迁移。
 *
 * 选择交互与批 C rollback-modal 同款（checkStrictly:false 父子级联）：
 * 旧版另有「同 IP 同应用批量扩选」双层逻辑，新版仅父子级联，
 * 该差异已记账待人工回归（见 task-M-report）。
 */
defineOptions({ name: 'ServiceUpgradeModal' });

const emit = defineEmits<{
  /** 升级下发成功，携带新建的升级历史 id（父组件跳转服务升级页） */
  submitted: [history: number];
}>();

/** 升级选择表行：分组行为应用名聚合，叶子行为可升级实例 */
interface UpgradeRow {
  /** 叶子：可升目标安装包 id（提交载荷） */
  appId?: number;
  canUpgradeText: string;
  children?: UpgradeRow[];
  id: number | string;
  instanceName: string;
  isParent: boolean;
  /** 叶子：服务实例 id（提交载荷） */
  serviceId?: number;
  version: string;
}

/** 弹窗开关（父组件 v-model:open 控制） */
const open = defineModel<boolean>('open', { default: false });

const columns: TableColumnsType = [
  {
    title: '名称',
    dataIndex: 'instanceName',
    key: 'instanceName',
    ellipsis: true,
    width: 150,
  },
  {
    title: '当前版本',
    dataIndex: 'version',
    key: 'version',
    align: 'center',
    ellipsis: true,
    width: 120,
  },
  {
    title: '升级版本',
    dataIndex: 'canUpgradeText',
    key: 'canUpgradeText',
    align: 'center',
    ellipsis: true,
    width: 120,
  },
];

const fetchLoading = shallowRef(false);
const submitting = shallowRef(false);
const searchValue = shallowRef('');

const rows = shallowRef<UpgradeRow[]>([]);
const selectedKeys = shallowRef<Array<number | string>>([]);

/** 全量叶子实例数（搜索过滤时保持不变，旧 allLength 契约） */
const allLength = shallowRef(0);
/** 已选叶子实例数 */
const selectedLeafCount = computed(
  () =>
    rows.value.filter(
      (row) => !row.isParent && selectedKeys.value.includes(row.id),
    ).length,
);

/** 分组行版本聚合：子实例当前版本全部一致才展示，否则显示 -（旧契约） */
function toRows(groups: ExecutionRecordApi.UpgradeChoiceGroup[]): UpgradeRow[] {
  return groups.map((group) => {
    const children = group.children ?? [];
    const versions = new Set(children.map((item) => item.version));
    return {
      id: group.app_name,
      instanceName: group.app_name,
      version: versions.size === 1 ? (children[0]?.version ?? '-') : '-',
      canUpgradeText: group.can_upgrade?.app_version ?? '-',
      isParent: true,
      children: children.map((item) => ({
        id: item.instance_name,
        instanceName: item.instance_name,
        version: item.version || '-',
        canUpgradeText: item.can_upgrade?.[0]?.app_version ?? '-',
        appId: item.can_upgrade?.[0]?.app_id,
        serviceId: item.service_id,
        isParent: false,
      })),
    };
  });
}

async function queryRows() {
  fetchLoading.value = true;
  try {
    const data = await listCanUpgrade({
      search: searchValue.value || null,
    });
    const result = toRows(data?.results ?? []);
    // 全量叶子数仅在无条件查询时刷新（旧契约）
    if (!searchValue.value) {
      allLength.value = result.reduce(
        (sum, group) => sum + (group.children?.length ?? 0),
        0,
      );
    }
    rows.value = result;
    selectedKeys.value = [];
  } catch {
    // requestClient 已统一提示错误
  } finally {
    fetchLoading.value = false;
  }
}

// 打开时拉取可升级列表；关闭时清空搜索与勾选（旧 afterClose 契约）
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

/** 级联勾选（checkStrictly=false）：onChange 返回含分组行，提交时取叶子 */
function handleSelectionChange(keys: Array<number | string>) {
  selectedKeys.value = keys;
}

async function handleOk() {
  const choices = rows.value
    .flatMap((group) => group.children ?? [])
    .filter((item) => selectedKeys.value.includes(item.id))
    .map((item) => ({ app_id: item.appId!, service_id: item.serviceId! }));
  submitting.value = true;
  try {
    const data = await doUpgrade(choices);
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
    ok-text="确认选择"
    title="服务升级-选择应用服务"
    :width="600"
    cancel-text="取消"
    destroy-on-close
    @ok="handleOk"
  >
    <div class="mb-3.5 flex justify-end">
      <span class="flex items-center text-sm">服务名称:</span>
      <Input
        v-model:value="searchValue"
        allow-clear
        class="ml-2"
        placeholder="请输入服务名称"
        style="width: 180px"
        @blur="queryRows"
        @change="handleSearchChange"
        @press-enter="queryRows"
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
      :scroll="{ y: 295 }"
      size="small"
      class="border border-[#ebeef2]"
    >
      <template #bodyCell="{ column, text }">
        <template v-if="column.key === 'instanceName'">
          <Tooltip :title="String(text ?? '')">
            <span>{{ text }}</span>
          </Tooltip>
        </template>
      </template>
    </Table>
    <div class="mt-5 flex justify-end gap-4 px-5">
      <span>已选择 {{ selectedLeafCount }} 个</span>
      <span>共 {{ allLength }} 个</span>
    </div>
  </Modal>
</template>
