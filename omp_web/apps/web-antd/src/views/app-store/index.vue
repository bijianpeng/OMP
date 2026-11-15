<script lang="ts" setup>
import type { AppStoreApi } from '#/api/app-store';
import type { InstallationApi } from '#/api/installation';

import { onMounted, reactive, ref, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Dropdown,
  Empty,
  Input,
  Menu,
  Pagination,
  Spin,
} from 'ant-design-vue';

import {
  queryComponents,
  queryLabels,
  queryServices,
} from '#/api/app-store';
import { getBatchInstallEntrance } from '#/api/installation';

import RollbackModal from '../installation-record/rollback-modal.vue';
import AppStoreCard from './app-store-card.vue';
import BatchInstallModal from './batch-install-modal.vue';
import DeleteServerModal from './delete-server-modal.vue';
import GetServiceModal from './get-service-modal.vue';
import ReleaseModal from './release-modal.vue';
import ScanServerModal from './scan-server-modal.vue';
import ServiceUpgradeModal from './service-upgrade-modal.vue';

/**
 * 应用商店：基础组件 / 应用服务卡片网格 + 标签筛选 + 搜索 +
 * 批量安装 / 发布 / 扫描 / 删除 / 升级 / 回滚 / 纳管入口。
 * 旧实现 omp_web/src/pages/AppStore/index.js 契约迁移。
 */
defineOptions({ name: 'AppStore' });

type TabKey = 'component' | 'service';

const TABS: TabKey[] = ['component', 'service'];

const TAB_TEXT: Record<TabKey, string> = {
  component: '基础组件',
  service: '应用服务',
};

const loading = ref(false);
const tabKey = ref<TabKey>('component');
/** 标签筛选（「全部」为空条件，旧 searchKey 契约） */
const searchKey = ref('全部');
const searchName = ref('');
/** 当前 tab 可选标签列表 */
const searchData = ref<string[]>([]);
/** 「共收录 N 个」仅在无条件查询时更新（旧契约） */
const total = ref(0);
const dataSource = ref<AppStoreApi.StoreCard[]>([]);
const pagination = reactive({
  current: 1,
  pageSize: 12,
  total: 0,
});

/** 搜索/筛选参数透传缓存（旧 pagination.searchParams 契约，切 tab 重置） */
let searchParams: Record<string, null | string> = {};

const releaseModalRef = ref<InstanceType<typeof ReleaseModal>>();
const scanServerModalRef = ref<InstanceType<typeof ScanServerModal>>();

const router = useRouter();

// ── 更多菜单弹窗：删除 / 升级 / 回滚 / 纳管 ────────────────────────

const deleteModalOpen = shallowRef(false);
const upgradeModalOpen = shallowRef(false);
const rollbackModalOpen = shallowRef(false);
const getServiceModalOpen = shallowRef(false);

/** 回滚下发成功：跳转服务回滚页跟踪进度（旧弹窗内部 history.push 契约） */
function onRollbackSubmitted(history: number) {
  router.push({
    path: '/application_management/app_store/service_rollback',
    query: { history: String(history) },
  });
}

/** 升级下发成功：跳转服务升级页跟踪进度 */
function onUpgradeSubmitted(history: number) {
  router.push({
    path: '/application_management/app_store/service_upgrade',
    query: { history: String(history) },
  });
}

// ── 批量安装弹窗 ───────────────────────────────────────────────────

const batchModalOpen = shallowRef(false);
const batchList = shallowRef<InstallationApi.EntranceItem[]>([]);
const batchUniqueKey = shallowRef('');

/** 打开批量安装弹窗：入口拉取可装应用与流程唯一键（旧契约） */
async function openBatchInstall() {
  try {
    const data = await getBatchInstallEntrance();
    batchList.value = data?.data ?? [];
    batchUniqueKey.value = data?.unique_key ?? '';
    batchModalOpen.value = true;
  } catch {
    // 全局拦截器已提示
  }
}

/** 当前 tab 的名称搜索参数键：组件 app_name / 服务 pro_name（旧契约） */
function searchField() {
  return tabKey.value === 'component' ? 'app_name' : 'pro_name';
}

async function fetchData(
  pageParams: { current: number; pageSize: number },
  params: Record<string, null | string>,
) {
  loading.value = true;
  try {
    const res =
      tabKey.value === 'component'
        ? await queryComponents({
            app_name: params.app_name ?? null,
            page: pageParams.current,
            size: pageParams.pageSize,
            type: params.type ?? null,
          })
        : await queryServices({
            page: pageParams.current,
            pro_name: params.pro_name ?? null,
            size: pageParams.pageSize,
            type: params.type ?? null,
          });
    // 查询条件全空时才刷新「共收录 N 个」（tabKey 非查询条件，旧契约）
    const hasCondition = Object.entries(params).some(
      ([key, value]) => key !== 'tabKey' && value,
    );
    if (!hasCondition) {
      total.value = res.count;
    }
    dataSource.value = res.results;
    pagination.total = res.count;
    pagination.current = pageParams.current;
    pagination.pageSize = pageParams.pageSize;
    searchParams = params;
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
    fetchLabelList();
  }
}

/** 刷新标签列表（label_type：0 组件 / 1 服务；旧契约：每次查询后刷新） */
async function fetchLabelList() {
  try {
    searchData.value = await queryLabels({
      label_type: tabKey.value === 'component' ? 0 : 1,
    });
  } catch {
    // 全局拦截器已提示
  }
}

/** 切换 tab：重置筛选/搜索/分页后全量查询 */
function switchTab(key: TabKey) {
  if (tabKey.value === key) return;
  tabKey.value = key;
  searchKey.value = '全部';
  searchName.value = '';
  searchParams = {};
  pagination.current = 1;
  pagination.total = 0;
  fetchData({ current: 1, pageSize: pagination.pageSize }, { tabKey: key });
}

/** 点击标签筛选（与旧版一致：标签与搜索词 AND 并传，点标签保留搜索词） */
function selectLabel(label: string) {
  searchKey.value = label;
  fetchData(
    { current: 1, pageSize: pagination.pageSize },
    {
      ...searchParams,
      type: label === '全部' ? null : label,
    },
  );
}

/** 搜索（回车/失触发生效；清空输入恢复全量，旧契约） */
function handleSearch() {
  fetchData(
    { current: 1, pageSize: pagination.pageSize },
    { ...searchParams, [searchField()]: searchName.value || null },
  );
}

function handleSearchChange(value: string) {
  searchName.value = value;
  if (!value) {
    fetchData(
      { current: 1, pageSize: pagination.pageSize },
      { ...searchParams, [searchField()]: null },
    );
  }
}

function handlePageChange(page: number) {
  fetchData(
    { current: page, pageSize: pagination.pageSize },
    { ...searchParams },
  );
}

/** 发布成功/扫描关闭后回到第 1 页刷新（旧 refresh 契约） */
function refresh() {
  fetchData(
    { current: 1, pageSize: pagination.pageSize },
    { ...searchParams, tabKey: tabKey.value },
  );
}

/** 打开发布向导（uuid 取毫秒时间戳，旧 timeUnix 契约） */
function openRelease() {
  releaseModalRef.value?.open(Date.now());
}

function openScan() {
  scanServerModalRef.value?.open();
}

/** 更多菜单（菜单项顺序与分隔线对齐旧版 Dropdown overlay） */
const moreMenuItems = [
  { key: 'release', label: '上传发布服务' },
  { key: 'scanServer', label: '扫描发布服务' },
  { key: 'deleteServer', label: '删除' },
  { type: 'divider' as const },
  { key: 'upgrade', label: '服务升级' },
  { key: 'rollback', label: '服务回滚' },
  { type: 'divider' as const },
  { key: 'getService', label: '服务纳管' },
];

function handleMoreClick({ key }: { key: number | string }) {
  if (key === 'release') {
    openRelease();
  } else if (key === 'scanServer') {
    openScan();
  } else if (key === 'deleteServer') {
    deleteModalOpen.value = true;
  } else if (key === 'upgrade') {
    upgradeModalOpen.value = true;
  } else if (key === 'rollback') {
    rollbackModalOpen.value = true;
  } else if (key === 'getService') {
    getServiceModalOpen.value = true;
  }
}

onMounted(() => {
  // 视口高度决定每页卡片数（旧契约：>955px 12 / 否则 8）
  pagination.pageSize = window.innerHeight > 955 ? 12 : 8;
  fetchData(
    { current: 1, pageSize: pagination.pageSize },
    { tabKey: tabKey.value },
  );
});
</script>

<template>
  <Page>
    <div class="flex flex-col">
      <!-- 头部：tab + 搜索 + 操作入口 + 标签行 -->
      <div class="border-b border-border bg-card pb-2.5">
        <div class="flex items-center justify-between px-2 pt-2.5">
          <div class="flex items-center gap-2.5 pl-4 text-sm text-foreground">
            <template v-for="(tab, idx) in TABS" :key="tab">
              <span
                class="cursor-pointer select-none hover:text-[#2e7cee]"
                :class="tabKey === tab ? 'text-[#2e7cee]' : ''"
                @click="switchTab(tab)"
              >
                {{ TAB_TEXT[tab] }}
              </span>
              <span v-if="idx < TABS.length - 1" class="text-muted-foreground">|</span>
            </template>
          </div>
          <div class="flex items-center gap-2.5 pr-4">
            <Input
              :value="searchName"
              allow-clear
              placeholder="请输入应用名称"
              :style="{ width: '200px' }"
              @blur="handleSearch"
              @change="(e: any) => handleSearchChange(e.target.value)"
              @press-enter="handleSearch"
            />
            <Button class="mr-2.5" type="primary" @click="openBatchInstall">
              批量安装
            </Button>
            <Dropdown placement="bottomRight">
              <template #overlay>
                <Menu :items="moreMenuItems" @click="handleMoreClick" />
              </template>
              <Button class="pr-2.5 pl-4">
                更多
                <IconifyIcon class="ml-1 inline align-[-2px]" icon="lucide:chevron-down" />
              </Button>
            </Dropdown>
          </div>
        </div>

        <div class="mt-2 flex items-center justify-between pl-4 text-xs text-foreground">
          <div class="flex flex-wrap items-center gap-x-5">
            <p
              class="cursor-pointer select-none"
              :class="searchKey === '全部' ? 'text-[#2e7cee]' : ''"
              @click="selectLabel('全部')"
            >
              全部
            </p>
            <p
              v-for="item in searchData"
              :key="item"
              class="cursor-pointer select-none"
              :class="searchKey === item ? 'text-[#2e7cee]' : ''"
              @click="selectLabel(item)"
            >
              {{ item }}
            </p>
          </div>
          <div class="flex items-center gap-3.5 pr-2.5 text-muted-foreground">
            <!-- 模板为 GET 文件流，浏览器直下（携带 JWT cookie） -->
            <a href="/api/appStore/applicationTemplate/" target="_blank">
              <Button size="small">
                <template #icon>
                  <IconifyIcon icon="lucide:download" />
                </template>
                <span class="text-[13px] text-muted-foreground">下载发布说明</span>
              </Button>
            </a>
            <span>共收录 {{ total }} 个{{ TAB_TEXT[tabKey] }}</span>
          </div>
        </div>
      </div>

      <!-- 卡片网格 -->
      <Spin :spinning="loading">
        <div
          v-if="dataSource.length === 0"
          class="flex h-[400px] items-center justify-center"
        >
          <Empty :description="`商店暂无${TAB_TEXT[tabKey]}`" />
        </div>
        <div v-else class="flex flex-wrap gap-x-[1%] gap-y-2.5 pt-2.5">
          <AppStoreCard
            v-for="(item, idx) in dataSource"
            :key="idx"
            :info="item"
            :tab-key="tabKey"
          />
        </div>
      </Spin>

      <!-- 分页 -->
      <div v-if="dataSource.length > 0" class="flex justify-center pt-4">
        <Pagination
          :current="pagination.current"
          :page-size="pagination.pageSize"
          :total="pagination.total"
          @change="handlePageChange"
        />
      </div>
    </div>

    <!-- 发布向导 / 扫描服务端安装包 -->
    <ReleaseModal ref="releaseModalRef" @refresh="refresh" />
    <ScanServerModal ref="scanServerModalRef" @refresh="refresh" />

    <!-- 批量安装 / 删除 / 升级 / 回滚（复用批 C 组件，无 history 限定） / 纳管 -->
    <BatchInstallModal
      v-model:open="batchModalOpen"
      :data-source="batchList"
      :init-loading="loading"
      :unique-key="batchUniqueKey"
    />
    <DeleteServerModal
      v-model:open="deleteModalOpen"
      :tab-key="tabKey"
      @refresh="refresh"
    />
    <ServiceUpgradeModal
      v-model:open="upgradeModalOpen"
      @submitted="onUpgradeSubmitted"
    />
    <RollbackModal
      v-model:open="rollbackModalOpen"
      :history-id="null"
      @submitted="onRollbackSubmitted"
    />
    <GetServiceModal v-model:open="getServiceModalOpen" />
  </Page>
</template>
