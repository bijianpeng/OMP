<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { InspectionApi } from '#/api/inspection';

import { h, onMounted, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { useUserStore } from '@vben/stores';

import { Badge, Button, message, Modal } from 'ant-design-vue';
import dayjs from 'dayjs';

import { getIpList } from '#/api/hosts';
import {
  distributeInspectionTask,
  getInspectionReport,
  listInspectionHistory,
  listInspectionServices,
} from '#/api/inspection';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { useEnvStore } from '#/store';

import PushEmailModal from './push-email-modal.vue';
import TaskSelectModal from './task-select-modal.vue';

defineOptions({ name: 'PatrolInspectionRecord' });

const TIME_FORMAT = 'YYYY-MM-DD HH:mm:ss';

const router = useRouter();
const userStore = useUserStore();
/** 当前环境上下文（手动巡检任务下发到当前环境） */
const envStore = useEnvStore();

/** 报告类型文案（与后端 InspectionHistory.inspection_type 一致） */
const typeText: Record<string, string> = {
  deep: '深度分析',
  host: '主机巡检',
  service: '组件巡检',
};

/** 执行方式文案 */
const executeText: Record<string, string> = {
  auto: '定时执行',
  man: '手动执行',
};

/** antd Badge 状态色（约束圆点配色取值范围） */
type BadgeStatus = 'default' | 'error' | 'processing' | 'success' | 'warning';

/**
 * 巡检结果圆点：2 成功（绿）/ 1 进行中（绿）/ 3 失败（红）。
 * 进行中与成功同色系沿用旧页 renderDisc('normal') 语义，靠文案区分。
 */
const statusBadge: Record<number, { status: BadgeStatus; text: string }> = {
  1: { status: 'success', text: '进行中' },
  2: { status: 'success', text: '成功' },
  3: { status: 'error', text: '失败' },
};

/** 推送结果圆点：1 成功（绿）/ 2 推送中（黄）/ 0 失败（红）/ 3 未推送（黄） */
const emailResultBadge: Record<number, { status: BadgeStatus; text: string }> = {
  0: { status: 'error', text: '失败' },
  1: { status: 'success', text: '成功' },
  2: { status: 'warning', text: '推送中' },
  3: { status: 'warning', text: '未推送' },
};

/** 格式化时间 */
const formatTime = (value?: null | string) =>
  value ? dayjs(value).format(TIME_FORMAT) : '-';

/** 巡检用时：秒 → "X小时 Y分钟 Z秒"（0/空显示 -，沿用旧页语义） */
function formatDuration(seconds?: null | number) {
  if (!seconds && seconds !== 0) return '-';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const sec = Math.floor(seconds % 60);
  const parts: string[] = [];
  if (hours) parts.push(`${hours}小时`);
  if (minutes) parts.push(`${minutes}分钟`);
  if (sec) parts.push(`${sec}秒`);
  return parts.length > 0 ? parts.join(' ') : '-';
}

/** 报告详情页跳转（仅成功状态的报告生成了文件可查看） */
function goDetail(record: InspectionApi.HistoryRecord) {
  router.push(
    `/status-patrol/patrol-inspection-record/status-patrol-detail/${record.id}`,
  );
}

/** 导出巡检报告：取报告 file_name 后走下载链接 */
async function exportReport(record: InspectionApi.HistoryRecord) {
  const report = await getInspectionReport(record.id);
  const fileName = report?.file_name;
  if (!fileName) {
    message.warning('暂无巡检报告文件');
    return;
  }
  message.success('正在下载巡检报告，双击文件夹中index.html查看报告');
  const link = document.createElement('a');
  link.href = `/download-inspection/${fileName}`;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
}

// ---- 巡检任务下发（深度分析/主机巡检/组件巡检） ----

const distributeLoading = shallowRef(false);

/** 任务下发请求体对齐旧页 taskDistribution（env 取当前环境上下文） */
async function distribute(
  type: string,
  extra?: Partial<InspectionApi.TaskDistributionParams>,
) {
  distributeLoading.value = true;
  try {
    await distributeInspectionTask({
      env: envStore.currentEnvId!,
      execute_type: 'man',
      inspection_name: 'mock',
      inspection_operator: userStore.userInfo?.username ?? null,
      inspection_status: '1',
      inspection_type: type,
      ...extra,
    });
    message.success('任务已下发');
    gridApi.query();
  } catch {
    // requestClient 已统一提示错误
  } finally {
    distributeLoading.value = false;
  }
}

/** 深度分析：确认后直接下发 */
function confirmDeepAnalysis() {
  Modal.confirm({
    cancelText: '取消',
    content: () =>
      h('div', [
        h('span', '确定要执行 '),
        h('span', { class: 'font-medium' }, '深度分析'),
        h('span', ' 操作？'),
      ]),
    okText: '确定',
    onOk: () => distribute('deep'),
    title: '提示',
  });
}

// 主机/组件勾选弹窗数据源（进页面即拉取，对齐旧页 useEffect）
const hostModalOpen = shallowRef(false);
const serviceModalOpen = shallowRef(false);
const hostOptions = shallowRef<Array<{ label: string; value: string }>>([]);
const serviceOptions = shallowRef<Array<{ label: string; value: number }>>([]);

onMounted(() => {
  getIpList()
    .then((data) => {
      hostOptions.value = (data ?? []).map((ip) => ({ label: ip, value: ip }));
    })
    .catch(() => {});
  listInspectionServices()
    .then((data) => {
      serviceOptions.value = (data ?? []).map((item) => ({
        label: item.service__app_name,
        value: item.service__id,
      }));
    })
    .catch(() => {});
});

async function onDistributeHosts(hosts: Array<number | string>) {
  await distribute('host', { hosts: hosts as string[] });
  hostModalOpen.value = false;
}

async function onDistributeServices(services: Array<number | string>) {
  await distribute('service', { services: services as number[] });
  serviceModalOpen.value = false;
}

// ---- 邮件推送弹窗 ----

const pushModalOpen = shallowRef(false);
const pushTarget = shallowRef<null | { id: number; module: string }>(null);

function openPush(record: InspectionApi.HistoryRecord) {
  pushTarget.value = { id: record.id, module: record.inspection_type };
  pushModalOpen.value = true;
}

function onPushed() {
  pushModalOpen.value = false;
  gridApi.query();
}

const formOptions: VbenFormProps = {
  collapsed: false,
  schema: [
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '输入报告名称',
      },
      fieldName: 'inspection_name',
      label: '报告名称',
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
  gridOptions: {
    columns: [
      // seq 需与后续 fixed:'left' 列同组，否则 vxe 会把它排到固定列之后（视觉第二列）
      { type: 'seq', title: '序列', width: 60, fixed: 'left' },
      {
        title: '报告名称',
        field: 'inspection_name',
        minWidth: 220,
        fixed: 'left',
        showOverflow: true,
        slots: {
          default: ({ row }) =>
            row.inspection_status === 2
              ? h(
                  'a',
                  { onClick: () => goDetail(row) },
                  row.inspection_name ?? '-',
                )
              : h('span', row.inspection_name ?? '-'),
        },
      },
      {
        title: '报告类型',
        field: 'inspection_type',
        minWidth: 100,
        filters: [
          { label: '组件巡检', value: 'service' },
          { label: '主机巡检', value: 'host' },
          { label: '深度分析', value: 'deep' },
        ],
        slots: {
          default: ({ row }) =>
            typeText[row.inspection_type as string] ??
            row.inspection_type ??
            '-',
        },
      },
      {
        title: '巡检结果',
        field: 'inspection_status',
        minWidth: 110,
        filters: [
          { label: '进行中', value: 1 },
          { label: '成功', value: 2 },
          { label: '失败', value: 3 },
        ],
        slots: {
          default: ({ row }) => {
            const badge = statusBadge[row.inspection_status as number];
            if (!badge) return '-';
            return h(
              'span',
              { class: 'inline-flex items-center gap-1.5' },
              [h(Badge, { status: badge.status }), h('span', badge.text)],
            );
          },
        },
      },
      {
        title: '执行方式',
        field: 'execute_type',
        minWidth: 100,
        filters: [
          { label: '手动', value: 'man' },
          { label: '定时', value: 'auto' },
        ],
        slots: {
          default: ({ row }) =>
            executeText[row.execute_type as string] ?? '-',
        },
      },
      {
        title: '巡检时间',
        field: 'start_time',
        minWidth: 170,
        sortable: true,
        formatter: ({ row }) => formatTime(row.start_time),
      },
      {
        title: '巡检用时',
        field: 'duration',
        minWidth: 140,
        formatter: ({ row }) => formatDuration(row.duration),
      },
      {
        title: '推送结果',
        field: 'send_email_result',
        minWidth: 100,
        slots: {
          default: ({ row }) => {
            const badge = emailResultBadge[row.send_email_result as number];
            if (!badge) return '-';
            return h(
              'span',
              { class: 'inline-flex items-center gap-1.5' },
              [h(Badge, { status: badge.status }), h('span', badge.text)],
            );
          },
        },
      },
      {
        title: '操作',
        field: 'action',
        minWidth: 110,
        fixed: 'right',
        slots: {
          default: ({ row }) => {
            // 仅成功（已生成报告）的记录可导出/推送，对齐旧页操作列语义
            if (row.inspection_status !== 2) {
              return h(
                'span',
                { class: 'cursor-not-allowed opacity-40' },
                '导出',
              );
            }
            return h('div', { class: 'flex justify-center gap-2' }, [
              h('a', { onClick: () => exportReport(row) }, '导出'),
              h('a', { onClick: () => openPush(row) }, '推送'),
            ]);
          },
        },
      },
    ],
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
          // vxe 列筛选（remote）→ inspection_type / inspection_status / execute_type
          const filterValue = (field: string) =>
            filterList?.find((item) => item.field === field)?.values?.[0] ??
            null;
          // 远端排序 → DRF ordering（asc → field、desc → -field）
          const sort = sorts?.[0];
          const ordering = sort?.field
            ? `${sort.order === 'desc' ? '-' : ''}${sort.field}`
            : null;
          return await listInspectionHistory({
            page: page.currentPage,
            size: page.pageSize,
            execute_type: filterValue('execute_type') as null | string,
            inspection_name: formValues.inspection_name || null,
            inspection_status: filterValue('inspection_status') as
              | null
              | number,
            inspection_type: filterValue('inspection_type') as null | string,
            ordering,
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
</script>

<template>
  <!-- content-class 基线：内容区限定高度，grid 高度自适应、表体内部滚动 -->
  <Page content-class="min-h-0 overflow-hidden pb-2">
    <Grid>
      <template #toolbar-actions>
        <Button type="primary" @click="confirmDeepAnalysis">深度分析</Button>
        <Button class="ml-2" type="primary" @click="hostModalOpen = true">
          主机巡检
        </Button>
        <Button class="ml-2" type="primary" @click="serviceModalOpen = true">
          组件巡检
        </Button>
      </template>
    </Grid>

    <TaskSelectModal
      v-model:open="hostModalOpen"
      :confirm-loading="distributeLoading"
      :options="hostOptions"
      title="主机巡检"
      @confirm="onDistributeHosts"
    />
    <TaskSelectModal
      v-model:open="serviceModalOpen"
      :confirm-loading="distributeLoading"
      :options="serviceOptions"
      title="组件巡检"
      @confirm="onDistributeServices"
    />
    <PushEmailModal
      v-model:open="pushModalOpen"
      :target="pushTarget"
      @pushed="onPushed"
    />
  </Page>
</template>
