<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { ServiceApi } from '#/api/services';

import { computed, reactive, ref, shallowRef, watch } from 'vue';
import { useRouter } from 'vue-router';

import { IconifyIcon } from '@vben/icons';

import { Input, Modal, Select, Table } from 'ant-design-vue';

import { checkManagedAppList, queryManagedAppList } from '#/api/services';
import { useGetServiceStore } from '#/store/get-service';

/**
 * 服务纳管选择弹窗（商店更多菜单「服务纳管」入口）。
 * 选择待纳管服务（产品按版本展开子服务，父子级联勾选），提交 appList
 * 校验通过后经 useGetServiceStore 交接跳转纳管页（旧 location.state 契约）。
 * 旧实现 omp_web/src/pages/AppStore/config/GetServiceModal.js 迁移。
 */
defineOptions({ name: 'GetServiceModal' });

const router = useRouter();
const getServiceStore = useGetServiceStore();

const open = defineModel<boolean>('open', { default: false });

/** 表格行：产品项附加树形 children（随所选版本切换） */
type AppRow = ServiceApi.ManagedAppItem & {
  children?: { name: string; version: string }[];
};

const loading = shallowRef(false);
const searchName = ref('');
/** 全量数据（搜索过滤的数据源） */
const initData = ref<AppRow[]>([]);
/** 展示数据（产品项 children 随所选版本切换） */
const dataSource = ref<AppRow[]>([]);
/** 选中 keys（顶层行名 + 子服务名，antdv 树形父子级联） */
const selectedKeys = shallowRef<string[]>([]);
/** 手动切换过的版本（应用名 → 版本） */
const versionInfo = reactive<Record<string, string>>({});

const columns: TableColumnsType = [
  {
    title: '名称',
    dataIndex: 'name',
    key: 'name',
    align: 'center' as const,
    ellipsis: true,
    width: 80,
  },
  {
    title: '版本',
    dataIndex: 'version',
    key: 'version',
    align: 'center' as const,
    ellipsis: true,
    width: 120,
  },
];

/** 已选择数（旧契约：只统计顶层行——产品与单体服务） */
const selectedCount = computed(() => {
  let count = 0;
  for (const item of initData.value) {
    if (item.child) {
      const children = item.children ?? [];
      count +=
        children.length === 0
          ? selectedKeys.value.includes(item.name)
            ? 1
            : 0
          : children.some((c) => selectedKeys.value.includes(c.name))
            ? 1
            : 0;
    } else if (selectedKeys.value.includes(item.name)) {
      count += 1;
    }
  }
  return count;
});

async function queryList() {
  loading.value = true;
  try {
    const data = await queryManagedAppList();
    // 产品项以默认版本（首版本）的子服务列表作为树形 children（旧契约）
    for (const item of data as AppRow[]) {
      if (item.child) {
        item.children = item.child[item.version[0]!] ?? [];
      }
    }
    initData.value = data as AppRow[];
    dataSource.value = data as AppRow[];
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

watch(open, (value) => {
  if (value) {
    queryList();
  } else {
    // 关闭后重置（旧 afterClose 契约：清空选中与版本记录）
    searchName.value = '';
    initData.value = [];
    dataSource.value = [];
    selectedKeys.value = [];
    for (const key of Object.keys(versionInfo)) {
      delete versionInfo[key];
    }
  }
});

/** 搜索（回车生效；清空恢复全量，旧契约） */
function handleSearch() {
  dataSource.value = initData.value.filter((item) =>
    item.name.includes(searchName.value),
  );
}

function handleSearchChange(value: string) {
  searchName.value = value;
  if (!value) {
    dataSource.value = initData.value;
  }
}

/** 切换版本：产品换 children 并清理相关选中；单体仅记录版本（旧契约） */
function handleVersionChange(record: AppRow, newVersion: string) {
  const oldVersion = versionInfo[record.name] ?? record.version[0]!;
  versionInfo[record.name] = newVersion;
  if (oldVersion === newVersion) return;
  if (record.child) {
    record.children = record.child[newVersion] ?? [];
    // 版本变化清空该服务的子项选中与自身选中（旧契约）
    const removed = new Set([
      ...(record.child[oldVersion] ?? []).map((i) => i.name),
      record.name,
    ]);
    selectedKeys.value = selectedKeys.value.filter((key) => !removed.has(key));
  }
}

/** 组装提交载荷：顶层项 → {name, version: [所选版本], child?: {版本: 选中子项}} */
function buildPayload() {
  const selected = new Set(selectedKeys.value);
  const resData: ServiceApi.ManagedAppItem[] = [];
  for (const item of initData.value) {
    const version = versionInfo[item.name] ?? item.version[0]!;
    if (item.child) {
      const children = item.child[version] ?? [];
      const checked = children.filter((c) => selected.has(c.name));
      if (selected.has(item.name) || checked.length > 0) {
        resData.push({
          child: { [version]: checked },
          name: item.name,
          version: [version],
        });
      }
    } else if (selected.has(item.name)) {
      resData.push({ name: item.name, version: [version] });
    }
  }
  return resData;
}

const submitting = shallowRef(false);

async function handleOk() {
  submitting.value = true;
  try {
    const data = await checkManagedAppList(buildPayload());
    if (data) {
      getServiceStore.setServiceData(data);
      router.push('/application_management/get-service');
    }
  } catch {
    // 全局拦截器已提示
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Modal
    v-model:open="open"
    :confirm-loading="submitting"
    :ok-button-props="{ disabled: selectedCount === 0 }"
    ok-text="确认选择"
    title="选择纳管服务"
    :width="520"
    cancel-text="取消"
    destroy-on-close
    @ok="handleOk"
  >
    <div class="mb-2.5 flex items-center justify-between">
      <Input
        v-model:value="searchName"
        placeholder="请输入名称"
        :style="{ width: '220px' }"
        @change="(e: any) => handleSearchChange(e.target.value)"
        @press-enter="handleSearch"
      >
        <template #suffix>
          <IconifyIcon class="text-[#b6b6b6]" icon="lucide:search" />
        </template>
      </Input>
      <div>已选择 {{ selectedCount }} 个</div>
    </div>
    <Table
      :columns="columns"
      :data-source="dataSource"
      :loading="loading || submitting"
      :pagination="false"
      :row-key="(record: any) => record.name"
      :row-selection="{
        checkStrictly: false,
        selectedRowKeys: selectedKeys,
        onChange: (keys: any) => (selectedKeys = keys as string[]),
      }"
      :scroll="{ y: 270 }"
      size="small"
      class="border border-[#ebeef2]"
    >
      <template #bodyCell="{ column, record, text }">
        <template v-if="column.key === 'version'">
          <span v-if="typeof text === 'string'">{{ text }}</span>
          <span v-else-if="text.length === 1">{{ text[0] }}</span>
          <Select
            v-else
            :bordered="false"
            :options="text.map((item: string) => ({ label: item, value: item }))"
            :value="versionInfo[record.name] ?? text[0]"
            :style="{ width: '120px', textAlign: 'left' }"
            @select="(value: any) => handleVersionChange(record as AppRow, String(value))"
          />
        </template>
      </template>
    </Table>
  </Modal>
</template>
