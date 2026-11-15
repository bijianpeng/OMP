<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { ServiceApi } from '#/api/services';

import { computed, h, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { useUserStore } from '@vben/stores';

import {
  Badge,
  Button,
  Drawer,
  Dropdown,
  Menu,
  message,
  Tooltip,
} from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getIpList } from '#/api/hosts';
import {
  getServiceLabels,
  listServices,
  queryServiceDeleteMsg,
  submitServiceAction,
} from '#/api/services';
import { isSafeFrameSrc, withGrafanaTheme } from '#/utils/frame-src';

import ActionModal from './action-modal.vue';
import DetailDrawer from './detail-drawer.vue';
import InstallLogModal from './install-log-modal.vue';

defineOptions({ name: 'ServiceManagement' });

const route = useRoute();
const router = useRouter();
const userStore = useUserStore();

/**
 * 旧前端首页/主机管理跳转参数（location.state）改为 query 透传：
 * ip → IP 筛选初始值；app_type / label_name → 列筛选初始勾选项。
 */
const { ip: queryIp, app_type: queryAppType, label_name: queryLabelName } =
  route.query;
const initAppType =
  queryAppType === undefined || queryAppType === ''
    ? undefined
    : String(queryAppType);
const initLabelName = queryLabelName ? String(queryLabelName) : '';

/** 操作码文案（与旧页 operateObj 一致；行内菜单叫「卸载」，确认文案统一「删除」） */
const OPERATE_TEXT: Record<number, string> = {
  1: '启动',
  2: '停止',
  3: '重启',
  4: '删除',
};

/** 负载状态 → 文字颜色（照搬旧页 colorConfig） */
const loadColorClass: Record<string, string> = {
  critical: 'text-red-500',
  normal: 'text-green-600',
  warning: 'text-orange-500',
};

/** 服务状态 → Badge（照搬旧页 renderStatus 分色：灰/黄/红/绿） */
const STATUS_BADGE: Record<
  string,
  'default' | 'error' | 'success' | 'warning'
> = {
  停止: 'error',
  停止中: 'warning',
  启动中: 'warning',
  待安装: 'warning',
  安装中: 'warning',
  安装失败: 'error',
  未监控: 'default',
  正常: 'success',
  未知: 'warning',
  重启中: 'warning',
};

/** 可勾选状态（旧页 notSelectable：部署流转中的服务不可选） */
const SELECTABLE_STATUS = ['正常', '停止', '未监控'];

/** iframe 抽屉（监控/日志） */
const frameState = reactive<{
  isOpen: boolean;
  src: string;
  title: string;
}>({ isOpen: false, src: '', title: '' });

// ---- 服务操作（批量/单行共用确认弹窗） ----

const actionOpen = ref(false);
const actionLoading = ref(false);
const actionOperate = ref(1);
const actionScope = ref<'batch' | 'single'>('batch');
const actionTargets = ref<ServiceApi.ServiceRecord[]>([]);
/** 删除依赖提示语（点击删除时向后端拉取） */
const deleteMsg = ref<null | { items: string[]; key: string }>(null);

async function fetchDeleteMsg(targets: ServiceApi.ServiceRecord[]) {
  deleteMsg.value = null;
  const username = userStore.userInfo?.username ?? '';
  try {
    const data = await queryServiceDeleteMsg(
      targets.map((item) => ({
        action: '4',
        id: item.id,
        operation_user: username,
      })),
    );
    if (data) {
      // 后端返回 "标题:项1,项2" 或 "无依赖信息" 纯文本（照搬旧页 split 解析）
      const [key, values] = data.split(':');
      deleteMsg.value = {
        items: values ? values.split(',') : [],
        key: key ?? '',
      };
    }
  } catch {
    // 全局拦截器已提示错误信息；弹窗照常打开（无提示语）
  }
}

/** 批量操作入口（toolbar 按钮与下拉菜单） */
function openBatchAction(operate: number) {
  const checked = gridApi.grid.getCheckboxRecords() as ServiceApi.ServiceRecord[];
  if (checked.length === 0) return;
  actionOperate.value = operate;
  actionScope.value = 'batch';
  actionTargets.value = checked;
  if (operate === 4) fetchDeleteMsg(checked);
  actionOpen.value = true;
}

/** 行内操作入口（更多下拉） */
function openSingleAction(operate: number, row: ServiceApi.ServiceRecord) {
  actionOperate.value = operate;
  actionScope.value = 'single';
  actionTargets.value = [row];
  if (operate === 4) fetchDeleteMsg([row]);
  actionOpen.value = true;
}

/**
 * 确认下发：批量启动/停止/重启仅提交 operable 的服务、
 * 删除提交全部勾选（照搬旧页 onFinish 过滤规则）。
 * Salt 异步任务：接口成功即提示下发成功，延迟 1.5s 刷新看状态流转。
 */
async function submitAction(delFile: boolean) {
  const operate = actionOperate.value;
  let targets = actionTargets.value;
  if (actionScope.value === 'batch' && operate !== 4) {
    targets = targets.filter((item) => item.operable);
  }
  const username = userStore.userInfo?.username ?? '';
  actionLoading.value = true;
  try {
    await submitServiceAction(
      targets.map((item) => ({
        action: operate,
        del_file: delFile,
        id: item.id,
        operation_user: username,
      })),
    );
    message.success(`${OPERATE_TEXT[operate]}操作下发成功`);
    actionOpen.value = false;
    gridApi.grid.clearCheckboxRow();
    checkedRecords.value = [];
    // 任务态异步流转：延迟刷新列表（照搬旧页 1500ms setTimeout）
    setTimeout(() => gridApi.query(), 1_500);
  } catch {
    // 全局拦截器已提示错误信息
  } finally {
    actionLoading.value = false;
  }
}

// ---- 勾选状态（toolbar 按钮禁用依据 + 已选中计数） ----

const checkedRecords = ref<ServiceApi.ServiceRecord[]>([]);

const hasOperableChecked = computed(() =>
  checkedRecords.value.some((item) => item.operable),
);

const batchMenuItems = computed(() => [
  { disabled: !hasOperableChecked.value, key: '2', label: '停止' },
  { disabled: !hasOperableChecked.value, key: '3', label: '重启' },
  { disabled: checkedRecords.value.length === 0, key: '4', label: '删除' },
]);

/** 功能模块列筛选选项（异步拉取后 reloadColumns 注入） */
type LabelFilter = { checked?: boolean; label: string; value: string };

function buildColumns(labelFilters: LabelFilter[]) {
  return [
    // checkbox 需与后续 fixed:'left' 列同组，否则 vxe 会把它排到固定列之后（视觉第二列）
    { type: 'checkbox' as const, width: 44, fixed: 'left' as const },
    {
      title: '实例名称',
      field: 'service_instance_name',
      width: 170,
      fixed: 'left' as const,
      sortable: true,
      showOverflow: true,
      slots: {
        default: ({ row }) =>
          h(
            Tooltip,
            { title: row.service_instance_name ?? '' },
            {
              default: () =>
                h(
                  'a',
                  {
                    onClick: () =>
                      detailDrawerRef.value?.open(
                        row as ServiceApi.ServiceRecord,
                      ),
                  },
                  row.service_instance_name || '-',
                ),
            },
          ),
      },
    },
    { title: 'IP地址', field: 'ip', width: 140, sortable: true },
    {
      title: 'CPU使用率',
      field: 'cpu_usage',
      width: 100,
      sortable: true,
      slots: {
        default: ({ row }) => {
          if (row.cpu_usage === null || row.cpu_usage === undefined) return '-';
          return h(
            'span',
            {
              class: `font-medium ${loadColorClass[row.cpu_status as string] ?? ''}`,
            },
            `${row.cpu_usage}%`,
          );
        },
      },
    },
    {
      title: '内存使用率',
      field: 'mem_usage',
      width: 100,
      sortable: true,
      slots: {
        default: ({ row }) => {
          if (row.mem_usage === null || row.mem_usage === undefined) return '-';
          return h(
            'span',
            {
              class: `font-medium ${loadColorClass[row.mem_status as string] ?? ''}`,
            },
            `${row.mem_usage}%`,
          );
        },
      },
    },
    {
      title: '状态',
      field: 'service_status',
      width: 100,
      slots: {
        default: ({ row }) => {
          const status = STATUS_BADGE[row.service_status as string];
          if (!status) return row.service_status ?? '-';
          return h('span', { class: 'inline-flex items-center gap-1.5' }, [
            h(Badge, { status }),
            h('span', row.service_status),
          ]);
        },
      },
    },
    {
      title: '告警次数',
      field: 'alert_count',
      width: 90,
      slots: {
        default: ({ row }) => {
          const text = row.alert_count as string;
          // '-' / '0次' 为纯文本，其余跳告警记录（带 IP 初始化筛选）
          if (!text || text === '-' || text === '0次') return text;
          return h(
            'a',
            {
              onClick: () => {
                if (row.ip) {
                  router.push({
                    path: '/application-monitoring/alarm-log',
                    query: { ip: row.ip },
                  });
                }
              },
            },
            text,
          );
        },
      },
    },
    {
      title: '端口',
      field: 'port',
      width: 80,
      formatter: ({ row }) => row.port || '-',
    },
    {
      title: '服务名称',
      field: 'app_name',
      width: 130,
      showOverflow: true,
      formatter: ({ row }) => row.app_name || '-',
    },
    {
      title: '版本',
      field: 'app_version',
      width: 110,
      showOverflow: true,
      formatter: ({ row }) => row.app_version || '-',
    },
    {
      title: '功能模块',
      field: 'label_name',
      width: 120,
      showOverflow: true,
      // 动态选项由 labels 接口异步注入；跳转初始值先行占位保证首查生效
      filters: labelFilters,
      formatter: ({ row }) => row.label_name || '-',
    },
    {
      title: '服务类型',
      field: 'app_type',
      width: 100,
      filters: [
        {
          checked: initAppType === '0',
          label: '基础组件',
          value: 0,
        },
        {
          checked: initAppType === '1',
          label: '应用服务',
          value: 1,
        },
      ],
      slots: {
        default: ({ row }) => (row.app_type ? '应用服务' : '基础组件'),
      },
    },
    {
      title: '集群模式',
      field: 'cluster_type',
      width: 90,
      formatter: ({ row }) => row.cluster_type || '-',
    },
    {
      title: '操作',
      field: 'action',
      width: 150,
      fixed: 'right' as const,
      slots: {
        default: ({ row }) => {
          const serviceRow = row as ServiceApi.ServiceRecord;
          const children: any[] = [];
          // 监控/日志：有面板 URL 才可点，打开 iframe 抽屉
          children.push(
            serviceRow.monitor_url
              ? h(
                  'a',
                  {
                    onClick: () => {
                      Object.assign(frameState, {
                        isOpen: true,
                        src: serviceRow.monitor_url,
                        title: `监控 - ${serviceRow.service_instance_name ?? ''}`,
                      });
                    },
                  },
                  '监控',
                )
              : h('span', { class: 'cursor-not-allowed opacity-40' }, '监控'),
          );
          children.push(
            serviceRow.log_url
              ? h(
                  'a',
                  {
                    class: 'ml-2',
                    onClick: () => {
                      Object.assign(frameState, {
                        isOpen: true,
                        src: serviceRow.log_url,
                        title: `日志 - ${serviceRow.service_instance_name ?? ''}`,
                      });
                    },
                  },
                  '日志',
                )
              : h(
                  'span',
                  { class: 'ml-2 cursor-not-allowed opacity-40' },
                  '日志',
                ),
          );
          // 更多：启动/停止/重启需服务可操作（operable），卸载始终可用
          children.push(
            h(
              Dropdown,
              { placement: 'bottom' },
              {
                default: () => h('a', { class: 'ml-2' }, '更多'),
                overlay: () =>
                  h(Menu, {
                    items: [
                      {
                        disabled: !serviceRow.operable,
                        key: '1',
                        label: '启动',
                      },
                      {
                        disabled: !serviceRow.operable,
                        key: '2',
                        label: '停止',
                      },
                      {
                        disabled: !serviceRow.operable,
                        key: '3',
                        label: '重启',
                      },
                      { key: '4', label: '卸载' },
                    ],
                    onClick: ({ key }) =>
                      openSingleAction(Number(key), serviceRow),
                  }),
              },
            ),
          );
          return h('div', { class: 'flex justify-center' }, children);
        },
      },
    },
  ];
}

const formOptions: VbenFormProps = {
  collapsed: false,
  schema: [
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [],
        placeholder: '选择主机 IP',
        showSearch: true,
      },
      defaultValue: queryIp ? String(queryIp) : undefined,
      fieldName: 'ip',
      label: 'IP地址',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '输入实例名称',
      },
      fieldName: 'service_instance_name',
      label: '实例名称',
    },
  ],
  submitOnChange: true,
  submitOnEnter: true,
};

const [Grid, gridApi] = useVbenVxeGrid({
  // 高度传导层：Grid 根 div（h-full）不是 flex 容器，多字段表单 + 窄视口时
  // vxe 表格会按全局 minHeight 撑开、裁掉分页条——让约束传导到 vxe 表格本体
  class: 'flex flex-col',
  gridClass: 'min-h-0 flex-1',
  formOptions,
  gridEvents: {
    checkboxAll() {
      checkedRecords.value = gridApi.grid.getCheckboxRecords() as ServiceApi.ServiceRecord[];
    },
    checkboxChange() {
      checkedRecords.value = gridApi.grid.getCheckboxRecords() as ServiceApi.ServiceRecord[];
    },
  },
  gridOptions: {
    columns: buildColumns(
      initLabelName
        ? [{ checked: true, label: initLabelName, value: initLabelName }]
        : [],
    ),
    checkboxConfig: {
      // 部署流转中的服务不可勾选（照搬旧页 notSelectable）
      checkMethod: ({ row }) =>
        SELECTABLE_STATUS.includes(row.service_status as string),
    },
    // 视口自适应：grid 填满父容器高度，表体内部滚动、分页条贴底
    height: 'auto',
    // 排序/筛选走服务端（远程模式），query 里消费 sorts/filters
    sortConfig: {
      remote: true,
    },
    filterConfig: {
      remote: true,
    },
    keepSource: true,
    pagerConfig: {
      enabled: true,
      pageSizes: [10, 20, 50, 100],
    },
    proxyConfig: {
      autoLoad: true,
      // wire 排序/筛选变化事件到 proxy 重查（配合 sortConfig/filterConfig.remote）
      sort: true,
      filter: true,
      response: {
        result: 'results',
        total: 'count',
      },
      ajax: {
        query: async ({ page, filters: filterList, sorts }, formValues) => {
          // vxe 列筛选（remote）→ label_name / app_type
          const filterValue = (field: string) =>
            filterList?.find((item) => item.field === field)?.values?.[0];
          // 远端排序 → DRF ordering（asc → field、desc → -field）
          // 后端 ordering_fields: ip / service_instance_name；
          // cpu_usage / mem_usage 走视图层动态排序
          const sort = sorts?.[0];
          const ordering = sort?.field
            ? `${sort.order === 'desc' ? '-' : ''}${sort.field}`
            : null;
          return await listServices({
            page: page.currentPage,
            size: page.pageSize,
            ordering,
            ip: formValues.ip || null,
            service_instance_name: formValues.service_instance_name || null,
            label_name: filterValue('label_name') ?? null,
            app_type: filterValue('app_type') ?? null,
          });
        },
      },
    },
    rowConfig: {
      keyField: 'id',
      isCurrent: true,
    },
    toolbarConfig: {
      refresh: true,
      zoom: true,
    },
  },
});

const detailDrawerRef = ref<InstanceType<typeof DetailDrawer>>();
const installLogModalRef = ref<InstanceType<typeof InstallLogModal>>();

onMounted(() => {
  // IP 下拉数据源异步拉取后回填 schema options
  getIpList()
    .then((data) => {
      gridApi.formApi.updateSchema([
        {
          componentProps: {
            options: (data ?? []).map((item) => ({
              label: item,
              value: item,
            })),
          },
          fieldName: 'ip',
        },
      ]);
    })
    .catch(() => {});

  // 功能模块列筛选选项：合并当前已勾选值后 reloadColumns 注入全量标签
  getServiceLabels()
    .then((labels) => {
      const checked = gridApi.grid
        .getCheckedFilters?.()
        ?.find((item) => item.field === 'label_name')
        ?.values?.map((v) => String(v)) ?? (initLabelName ? [initLabelName] : []);
      const labelFilters = (labels ?? []).map((label) => ({
        checked: checked.includes(label),
        label,
        value: label,
      }));
      gridApi.grid.reloadColumn(buildColumns(labelFilters));
    })
    .catch(() => {});
});
</script>

<template>
  <!-- content-class 基线：内容区限定高度，grid 高度自适应、表体内部滚动 -->
  <Page content-class="min-h-0 overflow-hidden pb-2">
    <Grid>
      <template #toolbar-actions>
        <Button
          type="primary"
          @click="router.push('/application_management/app_store')"
        >
          安装
        </Button>
        <Button
          class="ml-2"
          :disabled="checkedRecords.length === 0"
          @click="openBatchAction(1)"
        >
          启动
        </Button>
        <Dropdown>
          <template #overlay>
            <Menu
              :items="batchMenuItems"
              @click="({ key }) => openBatchAction(Number(key))"
            />
          </template>
          <Button class="ml-2">更多</Button>
        </Dropdown>
        <span class="ml-3 text-sm text-gray-500">
          已选中 {{ checkedRecords.length }} 条
        </span>
      </template>
    </Grid>

    <!-- 服务操作确认（批量/单行共用） -->
    <ActionModal
      v-model:open="actionOpen"
      :delete-msg="deleteMsg"
      :loading="actionLoading"
      :operate="actionOperate"
      :scope="actionScope"
      :target-count="actionTargets.length"
      @confirm="submitAction"
    />

    <!-- 服务详情抽屉（基本信息/安装信息/历史记录） -->
    <DetailDrawer ref="detailDrawerRef" @view-install-log="installLogModalRef?.open($event)" />

    <!-- 安装记录（实时日志轮询） -->
    <InstallLogModal ref="installLogModalRef" />

    <!-- 监控/日志 iframe 抽屉 -->
    <Drawer
      v-model:open="frameState.isOpen"
      :title="frameState.title"
      width="calc(100% - 100px)"
      destroy-on-close
      placement="right"
      :body-style="{ padding: 0 }"
      :header-style="{ background: 'hsl(var(--background-deep))' }"
    >
      <iframe
        v-if="frameState.isOpen && isSafeFrameSrc(frameState.src)"
        :src="withGrafanaTheme(frameState.src)"
        class="h-full w-full border-0"
      ></iframe>
    </Drawer>
  </Page>
</template>
