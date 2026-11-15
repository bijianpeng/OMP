<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { HostApi } from '#/api/hosts';

import { computed, h, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import { Badge, Button, Drawer, Dropdown, Menu, message } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  changeHostMaintain,
  deleteHosts,
  getIpList,
  initHosts,
  listHosts,
  reinstallHostAgent,
  reinstallMonitorAgent,
  restartHostAgent,
  restartMonitorAgent,
} from '#/api/hosts';
import { isSafeFrameSrc, withGrafanaTheme } from '#/utils/frame-src';

import BatchImportModal from './batch-import-modal.vue';
import HostActionModal from './host-action-modal.vue';
import HostDetailDrawer from './host-detail-drawer.vue';
import HostFormModal from './host-form-modal.vue';

defineOptions({ name: 'MachineManagement' });

const route = useRoute();
const router = useRouter();

/**
 * 旧前端 location.state 透传参数改 query：ip → IP 筛选初始值
 * （告警记录/异常清单/服务管理的 IP 列与首页告警横幅均跳本页）
 */
const { ip: queryIp } = route.query;

/** 负载状态 → 文字颜色（与服务管理页 loadColorClass 统一） */
const loadColorClass: Record<string, string> = {
  critical: 'text-red-500',
  normal: 'text-green-600',
  warning: 'text-orange-500',
};

/** Agent 状态分色（照搬旧页 renderStatus：0 正常 1 重启中 2 启动失败 3 部署中 4 部署失败） */
const AGENT_BADGE: Record<number, 'default' | 'error' | 'success' | 'warning'> =
  {
    0: 'success',
    1: 'warning',
    2: 'error',
    3: 'warning',
    4: 'error',
  };
const AGENT_TEXT: Record<number, string> = {
  0: '正常',
  1: '重启中',
  2: '启动失败',
  3: '部署中',
  4: '部署失败',
};

/** 部署流转中的主机行内操作不可用（照搬旧页 host_agent/monitor_agent==3 判断） */
const isDeploying = (row: HostApi.HostRecord) =>
  row.host_agent === 3 || row.monitor_agent === 3;

/** 数值列文案（照搬旧页服务总数/告警总数渲染：>0 链接、0 带单位、空值 -） */
function renderCountCell(
  text: null | number,
  unit: string,
  onClick?: () => void,
) {
  if ((!text || text === ('-' as any)) && text !== 0) return '-';
  if (text && text !== 0) {
    return h('a', { onClick }, `${text}${unit}`);
  }
  return `${text}${unit}`;
}

// ── 通用确认弹窗（agent 操作/维护模式/删除/初始化共用） ──────────

type ConfirmKind =
  | 'agent'
  | 'command'
  | 'maintain-batch'
  | 'maintain-single';

const confirmOpen = ref(false);
const confirmLoading = ref(false);
const confirmState = reactive<{
  action: string;
  count: number;
  kind: ConfirmKind;
  run: () => Promise<void>;
  target?: string;
}>({
  action: '',
  count: 0,
  kind: 'agent',
  run: async () => {},
});

function openConfirm(state: {
  action: string;
  count: number;
  kind: ConfirmKind;
  run: () => Promise<void>;
  target?: string;
}) {
  Object.assign(confirmState, state);
  confirmOpen.value = true;
}

/** 取当前勾选行；空勾选不应到达入口（菜单项已禁用） */
function getChecked(): HostApi.HostRecord[] {
  return gridApi.grid.getCheckboxRecords() as HostApi.HostRecord[];
}

function clearChecked() {
  gridApi.grid.clearCheckboxRow();
  checkedRecords.value = [];
}

/** Agent 类任务下发（Salt 异步：成功即下发完成，保持当前页刷新看状态流转） */
async function runAgentAction(
  submit: (ids: number[]) => Promise<any>,
  successMsg: string,
) {
  confirmLoading.value = true;
  try {
    await submit(getChecked().map((item) => item.id));
    message.success(successMsg);
    confirmOpen.value = false;
    clearChecked();
    gridApi.query();
  } catch {
    // 全局拦截器已提示
  } finally {
    confirmLoading.value = false;
  }
}

/** Agent 重启/重装确认入口 */
function openAgentAction(
  type: 'reinstall-host' | 'reinstall-monitor' | 'restart-host' | 'restart-monitor',
) {
  const checked = getChecked();
  const verb = type.startsWith('restart') ? '重启' : '重装';
  const target = type.endsWith('host') ? '主机Agent' : '监控Agent';
  const submit =
    type === 'restart-host'
      ? restartHostAgent
      : type === 'restart-monitor'
        ? restartMonitorAgent
        : type === 'reinstall-host'
          ? reinstallHostAgent
          : reinstallMonitorAgent;
  openConfirm({
    kind: 'agent',
    action: verb,
    target,
    count: checked.length,
    run: () =>
      runAgentAction(submit, `${verb}${target}任务已下发`),
  });
}

/** 批量删除主机 */
function openDelete() {
  const checked = getChecked();
  openConfirm({
    kind: 'command',
    action: '执行删除命令',
    count: checked.length,
    run: () => runAgentAction(deleteHosts, '删除主机任务已下发'),
  });
}

/**
 * 初始化主机：仅未执行/失败的主机参与，全部已初始化则直接提示
 * （旧前端 UI 已下线入口，逻辑保留与旧代码一致）
 */
function openInit() {
  const checked = getChecked();
  const pending = checked.filter(
    (item) => item.init_status === 1 || item.init_status === 3,
  );
  openConfirm({
    kind: 'command',
    action: '执行初始化',
    count: checked.length,
    run: async () => {
      if (pending.length === 0) {
        message.success('所选主机已经初始化完成');
        confirmOpen.value = false;
        clearChecked();
        return;
      }
      await runAgentAction(() => initHosts(pending.map((i) => i.id)), '初始化主机任务已下发');
    },
  });
}

/**
 * 维护模式切换：开启只提交未处于维护的、关闭只提交已维护的；
 * 无匹配主机时直接提示成功（照搬旧页 fetchMaintainChange 过滤规则）。
 */
async function runMaintain(open: boolean, targets: HostApi.HostRecord[]) {
  const submitTargets = targets.filter((item) =>
    open ? !item.is_maintenance : item.is_maintenance,
  );
  const successMsg = open ? '主机开启维护模式成功' : '主机关闭维护模式成功';
  if (submitTargets.length === 0) {
    confirmOpen.value = false;
    clearChecked();
    message.success(successMsg);
    return;
  }
  confirmLoading.value = true;
  try {
    await changeHostMaintain(open, submitTargets.map((item) => item.id));
    message.success(successMsg);
    confirmOpen.value = false;
    clearChecked();
    gridApi.query();
  } catch {
    // 全局拦截器已提示
  } finally {
    confirmLoading.value = false;
  }
}

function openMaintainBatch(open: boolean) {
  const checked = getChecked();
  openConfirm({
    kind: 'maintain-batch',
    action: open ? '开启维护模式' : '关闭维护模式',
    count: checked.length,
    run: () => runMaintain(open, checked),
  });
}

function openMaintainSingle(open: boolean, row: HostApi.HostRecord) {
  openConfirm({
    kind: 'maintain-single',
    action: open ? '开启维护模式' : '关闭维护模式',
    count: 1,
    run: () => runMaintain(open, [row]),
  });
}

// ── 勾选状态（顶栏菜单禁用依据 + 已选中计数） ────────────────────

const checkedRecords = ref<HostApi.HostRecord[]>([]);

const hasChecked = computed(() => checkedRecords.value.length > 0);

const moreMenuItems = computed(() => [
  {
    disabled: !hasChecked.value,
    key: 'maintain-open',
    label: '开启维护模式',
  },
  {
    disabled: !hasChecked.value,
    key: 'maintain-close',
    label: '关闭维护模式',
  },
  {
    disabled: !hasChecked.value,
    key: 'restart-host',
    label: '重启主机Agent',
  },
  {
    disabled: !hasChecked.value,
    key: 'restart-monitor',
    label: '重启监控Agent',
  },
  {
    disabled: !hasChecked.value,
    key: 'reinstall-host',
    label: '重装主机Agent',
  },
  {
    disabled: !hasChecked.value,
    key: 'reinstall-monitor',
    label: '重装监控Agent',
  },
  {
    disabled: !hasChecked.value,
    key: 'delete-host',
    label: '删除主机',
  },
]);

function handleMoreMenuClick({ key }: { key: number | string }) {
  switch (key) {
    case 'maintain-open': {
      openMaintainBatch(true);
      break;
    }
    case 'maintain-close': {
      openMaintainBatch(false);
      break;
    }
    case 'restart-host':
    case 'restart-monitor':
    case 'reinstall-host':
    case 'reinstall-monitor': {
      openAgentAction(
        key as 'reinstall-host' | 'restart-host' | 'restart-monitor' | 'reinstall-monitor',
      );
      break;
    }
    case 'delete-host': {
      openDelete();
      break;
    }
    case 'init-host': {
      openInit();
      break;
    }
  }
}

// ── 弹窗/抽屉引用 ────────────────────────────────────────────────

/** 行内操作（监控 + 更多菜单）；部署流转中的主机整列置灰（照旧页） */
function renderActionCell(hostRow: HostApi.HostRecord) {
  const disabled = isDeploying(hostRow);
  const children: any[] = [];
  // 监控：部署流转中不可用，其余按面板 URL 有无打开 iframe 抽屉
  children.push(
    !disabled && hostRow.monitor_url
      ? h(
          'a',
          {
            onClick: () => {
              Object.assign(frameState, {
                isOpen: true,
                src: hostRow.monitor_url,
                title: `监控 - ${hostRow.instance_name ?? ''}`,
              });
            },
          },
          '监控',
        )
      : h('span', { class: 'cursor-not-allowed opacity-40' }, '监控'),
  );
  // 更多：修改主机信息 / 开启或关闭维护模式（部署流转中不可点）
  children.push(
    disabled
      ? h('span', { class: 'ml-2 cursor-not-allowed opacity-40' }, '更多')
      : h(
          Dropdown,
          { placement: 'bottom' },
          {
            default: () => h('a', { class: 'ml-2' }, '更多'),
            overlay: () =>
              h(Menu, {
                items: [
                  { key: 'edit', label: '修改主机信息' },
                  hostRow.is_maintenance
                    ? { key: 'maintain-close', label: '关闭维护模式' }
                    : { key: 'maintain-open', label: '开启维护模式' },
                ],
                onClick: ({ key }) => {
                  if (key === 'edit') {
                    formModalRef.value?.open(hostRow);
                  } else if (key === 'maintain-open') {
                    openMaintainSingle(true, hostRow);
                  } else if (key === 'maintain-close') {
                    openMaintainSingle(false, hostRow);
                  }
                },
              }),
          },
        ),
  );
  return h('div', { class: 'flex justify-center' }, children);
}

const formModalRef = ref<InstanceType<typeof HostFormModal>>();
const batchImportRef = ref<InstanceType<typeof BatchImportModal>>();
const detailDrawerRef = ref<InstanceType<typeof HostDetailDrawer>>();

/** iframe 抽屉（监控面板） */
const frameState = reactive<{ isOpen: boolean; src: string; title: string }>({
  isOpen: false,
  src: '',
  title: '',
});

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
      checkedRecords.value = gridApi.grid.getCheckboxRecords() as HostApi.HostRecord[];
    },
    checkboxChange() {
      checkedRecords.value = gridApi.grid.getCheckboxRecords() as HostApi.HostRecord[];
    },
  },
  gridOptions: {
    columns: [
      // checkbox 需与后续 fixed:'left' 列同组，否则 vxe 会把它排到固定列之后（视觉第二列）
      { type: 'checkbox', width: 44, fixed: 'left' },
      {
        title: 'IP地址',
        field: 'ip',
        width: 140,
        fixed: 'left',
        sortable: true,
        slots: {
          default: ({ row }) =>
            h(
              'a',
              {
                onClick: () =>
                  detailDrawerRef.value?.open(row as HostApi.HostRecord),
              },
              row.ip || '-',
            ),
        },
      },
      {
        title: '实例名称',
        field: 'instance_name',
        // 数据分区使用率列让位排序图标加宽后，从本列（内容短、无排序）回收等宽避免横向滚动
        width: 116,
        showOverflow: true,
        formatter: ({ row }) => row.instance_name || '-',
      },
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
        title: '根分区使用率',
        field: 'root_disk_usage',
        width: 110,
        sortable: true,
        slots: {
          default: ({ row }) => {
            if (
              row.root_disk_usage === null ||
              row.root_disk_usage === undefined
            )
              return '-';
            return h(
              'span',
              {
                class: `font-medium ${loadColorClass[row.root_disk_status as string] ?? ''}`,
              },
              `${row.root_disk_usage}%`,
            );
          },
        },
      },
      {
        title: '数据分区使用率',
        field: 'data_disk_usage',
        width: 134,
        sortable: true,
        slots: {
          default: ({ row }) => {
            if (
              row.data_disk_usage === null ||
              row.data_disk_usage === undefined
            )
              return '-';
            return h(
              'span',
              {
                class: `font-medium ${loadColorClass[row.data_disk_status as string] ?? ''}`,
              },
              `${row.data_disk_usage}%`,
            );
          },
        },
      },
      {
        title: '维护模式',
        field: 'is_maintenance',
        width: 90,
        formatter: ({ row }) =>
          row.is_maintenance === null || row.is_maintenance === undefined
            ? '-'
            : row.is_maintenance
              ? '开'
              : '关',
      },
      {
        title: '主机Agent',
        field: 'host_agent',
        width: 100,
        sortable: true,
        slots: {
          default: ({ row }) => {
            const conf = AGENT_TEXT[row.host_agent as number];
            if (!conf) return '-';
            return h('span', { class: 'inline-flex items-center gap-1.5' }, [
              h(Badge, { status: AGENT_BADGE[row.host_agent as number] }),
              h('span', conf),
            ]);
          },
        },
      },
      {
        title: '监控Agent',
        field: 'monitor_agent',
        width: 100,
        sortable: true,
        slots: {
          default: ({ row }) => {
            const conf = AGENT_TEXT[row.monitor_agent as number];
            if (!conf) return '-';
            return h('span', { class: 'inline-flex items-center gap-1.5' }, [
              h(Badge, { status: AGENT_BADGE[row.monitor_agent as number] }),
              h('span', conf),
            ]);
          },
        },
      },
      {
        title: '服务总数',
        field: 'service_num',
        width: 90,
        sortable: true,
        slots: {
          default: ({ row }) =>
            renderCountCell(row.service_num as null | number, '个', () => {
              if (row.ip) {
                // 跳服务管理（消费 ?ip= 契约）
                router.push({
                  path: '/application_management/service_management',
                  query: { ip: row.ip },
                });
              }
            }),
        },
      },
      {
        title: '告警总数',
        field: 'alert_num',
        width: 90,
        sortable: true,
        slots: {
          default: ({ row }) =>
            renderCountCell(row.alert_num as null | number, '次', () => {
              if (row.ip) {
                // 跳告警记录（消费 ?ip= 契约）
                router.push({
                  path: '/application-monitoring/alarm-log',
                  query: { ip: row.ip },
                });
              }
            }),
        },
      },
      {
        title: '操作',
        field: 'action',
        width: 120,
        fixed: 'right',
        slots: {
          default: ({ row }) => renderActionCell(row as HostApi.HostRecord),
        },
      },
    ],
    // 视口自适应：grid 填满父容器高度，表体内部滚动、分页条贴底
    height: 'auto',
    // 排序走服务端（远程模式），query 里消费 sorts
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
      sort: true,
      filter: true,
      response: {
        result: 'results',
        total: 'count',
      },
      ajax: {
        query: async ({ page, sorts }, formValues) => {
          // 远端排序 → DRF ordering（asc → field、desc → -field；
          // 修正旧前端把"升序"映射为 -field 的颠倒行为）
          const sort = sorts?.[0];
          const ordering = sort?.field
            ? `${sort.order === 'desc' ? '-' : ''}${sort.field}`
            : null;
          return await listHosts({
            page: page.currentPage,
            size: page.pageSize,
            ordering,
            ip: formValues.ip || null,
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
});
</script>

<template>
  <!-- content-class 基线：内容区限定高度，grid 高度自适应、表体内部滚动 -->
  <Page content-class="min-h-0 overflow-hidden pb-2">
    <Grid>
      <template #toolbar-actions>
        <Button type="primary" @click="formModalRef?.open()">添加</Button>
        <Button class="ml-2" @click="batchImportRef?.open()">导入</Button>
        <Dropdown>
          <template #overlay>
            <Menu
              :items="moreMenuItems"
              @click="handleMoreMenuClick"
            />
          </template>
          <Button class="ml-2">更多</Button>
        </Dropdown>
        <span class="ml-3 text-sm text-gray-500">
          已选中 {{ checkedRecords.length }} 条
        </span>
      </template>
    </Grid>

    <!-- 通用确认弹窗（重启/重装 Agent、维护模式、删除、初始化） -->
    <HostActionModal
      v-model:open="confirmOpen"
      :action="confirmState.action"
      :count="confirmState.count"
      :kind="confirmState.kind"
      :loading="confirmLoading"
      :target="confirmState.target"
      @confirm="confirmState.run()"
    />

    <!-- 新增/编辑主机 -->
    <HostFormModal ref="formModalRef" @success="gridApi.query()" />

    <!-- 批量导入（上传解析→校验→创建） -->
    <BatchImportModal ref="batchImportRef" @success="gridApi.query()" />

    <!-- 主机详情抽屉（基本信息/Agent状态/部署组件/历史记录） -->
    <HostDetailDrawer ref="detailDrawerRef" />

    <!-- 监控 iframe 抽屉 -->
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
