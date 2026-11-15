<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { InstallationApi } from '#/api/installation';

import { reactive, ref, shallowRef, watch } from 'vue';
import { useRouter } from 'vue-router';

import { Modal, Select, Switch, Table } from 'ant-design-vue';

import {
  createInstallInfo,
} from '#/api/installation';
import { useInstallationStore } from '#/store/installation';

/**
 * 批量安装-选择应用服务弹窗（商店「批量安装」按钮入口）。
 * 列出可批量安装的应用（is_continue=false 已安装过禁选），逐行选版本
 * 与高可用开关后提交 createInstallInfo，经 useInstallationStore 交接
 * （uniqueKey + Step1 基础数据）跳转批量安装向导页。
 * 旧实现 omp_web/src/pages/AppStore/config/BatchInstallationModal.js 迁移
 * （卡片单应用安装流已由批 K 独立向导页替代，本弹窗仅保留批量入口）。
 */
defineOptions({ name: 'BatchInstallModal' });

const props = defineProps<{
  /** 入口列表数据（父页 batchInstallEntrance 拉取） */
  dataSource: InstallationApi.EntranceItem[];
  /** 父页查询 loading（弹窗表格共用，旧 initLoading 契约） */
  initLoading: boolean;
  /** 入口下发唯一键（createInstallInfo 回传） */
  uniqueKey: string;
}>();

const open = defineModel<boolean>('open', { default: false });

const router = useRouter();
const installationStore = useInstallationStore();

const submitting = shallowRef(false);

/** 选中应用名集合（默认全选可装项，旧 useEffect [dataSource] 契约） */
const selectedKeys = ref<string[]>([]);
/** 手动切换过的版本（应用名 → 版本） */
const versionInfo = reactive<Record<string, string>>({});
/** 高可用开关 */
const highAvailability = ref(false);

watch(
  () => props.dataSource,
  (data) => {
    selectedKeys.value = data
      .filter((item) => item.is_continue)
      .map((item) => item.name);
  },
);

// 关闭后重置（旧 afterClose 契约：清空选中与高可用）
watch(open, (value) => {
  if (!value) {
    selectedKeys.value = [];
    highAvailability.value = false;
    for (const key of Object.keys(versionInfo)) {
      delete versionInfo[key];
    }
  }
});

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

/** 已选应用（按 dataSource 顺序，版本取手动选择或首版本） */
async function handleOk() {
  submitting.value = true;
  try {
    const installProduct = props.dataSource
      .filter((item) => selectedKeys.value.includes(item.name))
      .map((item) => ({
        name: item.name,
        version: versionInfo[item.name] ?? item.version[0] ?? '',
      }));
    const data = await createInstallInfo({
      high_availability: highAvailability.value,
      install_product: installProduct,
      unique_key: props.uniqueKey,
    });
    if (data?.data) {
      installationStore.setInstallInfo(data.unique_key, data.data);
    }
    open.value = false;
    router.push('/application_management/app_store/installation');
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
    :ok-button-props="{ disabled: selectedKeys.length === 0 }"
    ok-text="确认选择"
    title="批量安装-选择应用服务"
    :width="520"
    cancel-text="取消"
    destroy-on-close
    @ok="handleOk"
  >
    <Table
      :columns="columns"
      :data-source="dataSource"
      :loading="initLoading || submitting"
      :pagination="false"
      :row-key="(record) => record.name"
      :row-selection="{
        getCheckboxProps: (record: any) => ({ disabled: !record.is_continue }),
        selectedRowKeys: selectedKeys,
        onChange: (keys: any) => (selectedKeys = keys as string[]),
      }"
      :scroll="{ y: 270 }"
      size="small"
      class="border border-[#ebeef2]"
    >
      <template #bodyCell="{ column, record, text }">
        <template v-if="column.key === 'version'">
          <Select
            :bordered="false"
            :options="text.map((item: string) => ({ label: item, value: item }))"
            :value="versionInfo[record.name] ?? text[0]"
            :style="{ width: '120px' }"
            @select="(value: any) => (versionInfo[record.name] = String(value))"
          />
        </template>
      </template>
    </Table>
    <div class="mt-5 flex items-center justify-between px-5">
      <div class="flex items-center">
        高可用
        <Switch v-model:checked="highAvailability" class="ml-2.5" />
      </div>
      <div class="flex gap-4">
        <span>已选择 {{ selectedKeys.length }} 个</span>
        <span>共 {{ dataSource.length }} 个</span>
      </div>
    </div>
  </Modal>
</template>
