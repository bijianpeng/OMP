<script lang="ts" setup>
import type { AppStoreApi } from '#/api/app-store';

import { computed, h, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Button, Select, Spin, Table, Tooltip } from 'ant-design-vue';
import dayjs from 'dayjs';

import { queryComponentDetail, queryServiceDetail } from '#/api/app-store';
import { createComponentInstallInfo } from '#/api/installation';
import { useInstallationStore } from '#/store/installation';

/**
 * 应用商店详情页：组件（app-component-detail）与应用服务（app-service-detail）
 * 两个隐藏路由共用本组件，按路径区分类型（旧 detail.js 契约）。
 * 「安装」入口按 path+params 契约跳转对应安装页（安装编排属后续批次）。
 */
defineOptions({ name: 'AppStoreDetail' });

const route = useRoute();
const router = useRouter();
const installationStore = useInstallationStore();

/** 路由参数（:name/:verson，vue-router 已解码） */
const name = computed(() => String(route.params.name ?? ''));
const versionParam = computed(() => String(route.params.verson ?? ''));
/** true 组件 / false 应用服务 */
const keyTab = computed(() => route.path.includes('component'));

/** 组件/服务字段前缀映射（旧 detail.js nameObj 契约；name 单列，用于索引详情顶层） */
type FieldMap = Record<
  | 'dependence'
  | 'description'
  | 'instanceInfo'
  | 'label'
  | 'logo'
  | 'md5'
  | 'user'
  | 'version',
  keyof AppStoreApi.VersionItem
>;
const field = computed<FieldMap>(() =>
  keyTab.value
    ? {
        dependence: 'app_dependence',
        description: 'app_description',
        instanceInfo: 'app_instances_info',
        label: 'app_labels',
        logo: 'app_logo',
        md5: 'app_package_md5',
        user: 'app_operation_user',
        version: 'app_version',
      }
    : {
        dependence: 'pro_dependence',
        description: 'pro_description',
        instanceInfo: 'pro_instances_info',
        label: 'pro_labels',
        logo: 'pro_logo',
        md5: 'pro_package_md5',
        user: 'pro_operation_user',
        version: 'pro_version',
      },
);

const nameField = computed<'app_name' | 'pro_name'>(() =>
  keyTab.value ? 'app_name' : 'pro_name',
);

const loading = ref(false);
const detail = ref<AppStoreApi.StoreDetail>();
const versionValue = ref('');
/** 实例信息是否展开为全部版本（默认当前版本） */
const isAll = ref(false);

/** versions 中同名版本可能存在多条发布记录，实例信息按下标合并（旧契约） */
const versionObj = computed<Record<string, AppStoreApi.VersionItem>>(() => {
  const obj: Record<string, AppStoreApi.VersionItem> = {};
  for (const item of detail.value?.versions ?? []) {
    const version = String(item[field.value.version] ?? '');
    const merged = [
      ...((obj[version]?.[field.value.instanceInfo] ??
        []) as AppStoreApi.InstanceInfo[]),
      ...((item[field.value.instanceInfo] ??
        []) as AppStoreApi.InstanceInfo[]),
    ];
    obj[version] = { ...item, [field.value.instanceInfo]: merged };
  }
  return obj;
});

const versionOptions = computed(() => Object.keys(versionObj.value));

const current = computed(
  () => versionObj.value[versionValue.value] ?? ({} as AppStoreApi.VersionItem),
);

/** 当前版本 logo（SVG 字符串，可能为空） */
const logo = computed(() => current.value[field.value.logo]);
const initial = computed(() =>
  String(detail.value?.[nameField.value] ?? '')
    .charAt(0)
    .toUpperCase(),
);

/** 全部版本的实例信息（展开「查看全部版本」时用） */
const allInstancesInfo = computed(() =>
  (detail.value?.versions ?? [])
    .map(
      (item) =>
        (item[field.value.instanceInfo] ?? []) as AppStoreApi.InstanceInfo[],
    )
    .flat(),
);

const tableData = computed(() =>
  isAll.value
    ? allInstancesInfo.value
    : ((current.value[field.value.instanceInfo] ??
        []) as AppStoreApi.InstanceInfo[]),
);

/** 类别标签展示文本 */
const labelText = computed(() => {
  const labels = current.value[field.value.label];
  return Array.isArray(labels) ? labels.join(',') : '';
});

/** 依赖信息（后端存 JSON 字符串；解析失败按无依赖展示） */
const dependenceList = computed(() => {
  const raw = current.value[field.value.dependence];
  if (!raw) return [];
  try {
    return JSON.parse(String(raw)) as { name: string; version: string }[];
  } catch {
    return [];
  }
});

const dependenceColumns = [
  { title: '名称', dataIndex: 'name', key: 'name', align: 'center' as const },
  {
    title: '版本',
    dataIndex: 'version',
    key: 'version',
    align: 'center' as const,
  },
];

/** 包含服务表格（仅应用服务详情有） */
const serviceColumns = [
  { title: '名称', dataIndex: 'name', key: 'name', align: 'center' as const },
  {
    title: '版本',
    dataIndex: 'version',
    key: 'version',
    align: 'center' as const,
    customRender: ({ text }: { text: null | string }) => text || '-',
  },
  {
    title: 'MD5',
    dataIndex: 'md5',
    key: 'md5',
    align: 'center' as const,
    customRender: ({ text }: { text: null | string }) => text || '-',
  },
  {
    title: '发布时间',
    dataIndex: 'created',
    key: 'created',
    align: 'center' as const,
    customRender: ({ text }: { text: null | string }) => text || '-',
  },
  {
    title: '安装',
    dataIndex: 'c',
    key: 'c',
    align: 'center' as const,
    customRender: ({
      record,
    }: {
      record: { name?: null | string; version?: null | string };
    }) => h('a', { onClick: () => installIncludedService(record) }, '点击安装'),
  },
];

/** 组件实例表格列 */
const componentInstanceColumns = [
  {
    title: '实例名称',
    dataIndex: 'instance_name',
    key: 'instance_name',
    align: 'center' as const,
  },
  { title: '主机IP', dataIndex: 'host_ip', key: 'host_ip', align: 'center' as const },
  {
    title: '端口',
    dataIndex: 'service_port',
    key: 'service_port',
    align: 'center' as const,
    customRender: ({ text }: { text: null | { default?: null | number }[] }) =>
      text ? text.map((i) => i.default).join(', ') : '-',
  },
  {
    title: '版本',
    dataIndex: 'app_version',
    key: 'app_version',
    align: 'center' as const,
  },
  { title: '模式', dataIndex: 'mode', key: 'mode', align: 'center' as const },
  {
    title: '安装时间',
    dataIndex: 'created',
    key: 'created',
    align: 'center' as const,
    customRender: ({ text }: { text: string }) =>
      text ? dayjs(text).format('YYYY-MM-DD HH:mm:ss') : '-',
  },
];

/** 服务实例表格列 */
const serviceInstanceColumns = [
  {
    title: '实例名称',
    dataIndex: 'instance_name',
    key: 'instance_name',
    align: 'center' as const,
  },
  {
    title: '版本',
    dataIndex: 'version',
    key: 'version',
    align: 'center' as const,
  },
  {
    title: '服务名称',
    dataIndex: 'app_name',
    key: 'app_name',
    align: 'center' as const,
  },
  {
    title: '服务版本',
    dataIndex: 'app_version',
    key: 'app_version',
    align: 'center' as const,
  },
  {
    title: '主机IP',
    dataIndex: 'host_ip',
    key: 'host_ip',
    align: 'center' as const,
  },
  {
    title: '端口',
    dataIndex: 'service_port',
    key: 'service_port',
    align: 'center' as const,
    customRender: ({ text }: { text: null | { default?: null | number }[] }) =>
      text ? text.map((i) => i.default).join(',') : '-',
  },
  {
    title: '安装时间',
    dataIndex: 'created',
    key: 'created',
    align: 'center' as const,
    customRender: ({ text }: { text: string }) =>
      text ? dayjs(text).format('YYYY-MM-DD HH:mm:ss') : '-',
  },
];

async function queryDetail() {
  loading.value = true;
  try {
    const data = keyTab.value
      ? await queryComponentDetail(name.value)
      : await queryServiceDetail(name.value);
    detail.value = data;
    versionValue.value = versionParam.value;
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

function goBack() {
  router.push('/application_management/app_store');
}

/**
 * 安装入口：按 path+params 契约跳转对应安装页（组件安装/应用安装页
 * 属后续批次，当前为占位路由；旧版此处的安装信息接口调用与 store 传递
 * 由安装编排批次接管）
 */
function goInstall(installName?: null | string) {
  const url = keyTab.value
    ? '/application_management/app_store/component_installation'
    : '/application_management/app_store/application_installation';
  // F3 衔接：携带当前查看版本，安装向导页据此选中初始版本
  router.push(
    `${url}/${encodeURIComponent(String(installName ?? name.value))}?version=${encodeURIComponent(String(versionValue.value || versionParam.value || ''))}`,
  );
}

/** 包含服务「点击安装」提交中（旧 detail.js 页级 loading 契约） */
const includeInstallLoading = ref(false);

/**
 * 包含服务「点击安装」（仅应用服务详情）：走组件安装链路——提交
 * createComponentInstallInfo 后经 installation store 跳批量安装页
 * （旧 detail.js 契约；包含服务为产品内服务，非商店组件/产品，
 * 不能走 componentEntrance/productEntrance 向导页）。
 */
async function installIncludedService(record: {
  name?: null | string;
  version?: null | string;
}) {
  includeInstallLoading.value = true;
  try {
    const data = await createComponentInstallInfo({
      high_availability: false,
      install_component: [
        {
          name: String(record.name ?? ''),
          version: String(record.version ?? ''),
        },
      ],
    });
    if (data?.data) {
      installationStore.setInstallInfo(data.unique_key, data.data);
    }
    router.push('/application_management/app_store/installation');
  } catch {
    // 全局拦截器已提示
  } finally {
    includeInstallLoading.value = false;
  }
}

onMounted(() => {
  queryDetail();
});
</script>

<template>
  <Page>
    <Spin :spinning="loading || includeInstallLoading">
      <!-- 顶部导航条：返回 + 名称 + 版本切换 -->
      <div
        class="flex h-10 items-center justify-between bg-muted px-5"
      >
        <div class="flex items-center gap-1">
          <Tooltip title="返回">
            <Button
              class="border-0 bg-transparent shadow-none"
              size="small"
              @click="goBack"
            >
              <template #icon>
                <IconifyIcon class="text-base" icon="lucide:arrow-left" />
              </template>
            </Button>
          </Tooltip>
          <span class="pl-4 text-base text-foreground">
            {{ detail?.[nameField] || name }}
          </span>
        </div>
        <div class="pr-2">
          版本:
          <Select
            v-model:value="versionValue"
            class="ml-2.5 w-40"
            :options="
              versionOptions.map((item) => ({ label: item, value: item }))
            "
            @change="isAll = false"
          />
        </div>
      </div>

      <!-- 标题区：logo + 描述 + 安装 -->
      <div class="flex items-center px-5 py-5 pr-[200px]">
        <div
          class="flex size-[80px] shrink-0 items-center justify-center overflow-hidden rounded-full border border-border"
        >
          <!-- logo 容器固定浅底（功能性画布）：素材底色不一，深色主题下需浅衬底保证可辨 -->
          <div
            v-if="logo"
            class="flex size-full items-center justify-center rounded-full bg-white [&>svg]:size-[50px]"
            v-html="logo"
          ></div>
          <div
            v-else
            class="flex size-full items-center justify-center rounded-full bg-gradient-to-r from-[#4f85f6] to-[#669aee] text-3xl text-white"
          >
            {{ initial }}
          </div>
        </div>
        <div class="relative min-w-0 flex-1 self-center pl-[60px]">
          <div
            class="line-clamp-2 text-foreground"
            :title="String(current[field.description] ?? '')"
          >
            {{ current[field.description] || '' }}
          </div>
          <Button
            class="!mt-3 px-5"
            size="small"
            type="primary"
            @click="goInstall()"
          >
            安装
          </Button>
        </div>
      </div>

      <!-- 基本信息 -->
      <div class="space-y-3.5 px-7 text-sm text-foreground">
        <div class="flex">
          <span class="w-[120px] shrink-0">类别:</span>
          <span>{{ labelText || '-' }}</span>
        </div>
        <div class="flex">
          <span class="w-[120px] shrink-0">发布时间:</span>
          <span>
            {{ current.created ? dayjs(current.created).format('YYYY-MM-DD HH:mm:ss') : '-' }}
          </span>
        </div>
        <div class="flex">
          <span class="w-[120px] shrink-0">MD5:</span>
          <span>{{ current[field.md5] || '-' }}</span>
        </div>
        <div class="flex">
          <span class="w-[120px] shrink-0">发布人:</span>
          <span>{{ current[field.user] || '-' }}</span>
        </div>
      </div>

      <!-- 依赖信息 -->
      <div class="mt-10 px-7">
        <div class="text-base">依赖信息</div>
        <div
          v-if="current[field.dependence]"
          class="page-table mt-5 mr-5 border border-border"
        >
          <Table
            :columns="dependenceColumns"
            :data-source="dependenceList"
            :pagination="false"
            row-key="name"
            size="middle"
          />
        </div>
        <p v-else class="pt-2.5 text-sm">无</p>
      </div>

      <!-- 包含服务（仅应用服务详情） -->
      <div v-if="!keyTab" class="mt-10 px-7">
        <div class="text-base">包含服务</div>
        <div
          v-if="current.pro_services"
          class="page-table mt-5 mr-5 border border-border"
        >
          <Table
            :columns="serviceColumns"
            :data-source="current.pro_services"
            :pagination="false"
            row-key="name"
            size="middle"
          />
        </div>
        <p v-else class="pt-2.5 text-sm">无</p>
      </div>

      <!-- 实例信息 -->
      <div class="mt-10 px-7 pb-5">
        <div class="flex items-center text-base">
          实例信息
          <span class="cursor-pointer pl-5 text-sm text-[#1f8aee]">
            <span v-if="isAll" @click="isAll = false">查看当前版本</span>
            <span v-else @click="isAll = true">查看全部版本</span>
          </span>
        </div>
        <p v-if="(tableData ?? []).length === 0" class="pt-2.5 text-sm">无</p>
        <div v-else class="mt-5 mr-5 border border-border">
          <Table
            :columns="
              keyTab ? componentInstanceColumns : serviceInstanceColumns
            "
            :data-source="tableData"
            :pagination="{ showSizeChanger: true }"
            size="middle"
          />
        </div>
      </div>
    </Spin>
  </Page>
</template>

<style scoped>
/* antdv Table 暗色算法下表头背景偏纯黑，统一为全站表头观感（accent 随主题） */
.page-table :deep(.ant-table-thead > tr > th) {
  background: hsl(var(--accent));
}
</style>
