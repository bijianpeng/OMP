<script lang="ts" setup>
import type { ExecutionRecordApi } from '#/api/execution-record';

import { h, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import { Badge, Tooltip } from 'ant-design-vue';
import dayjs from 'dayjs';

import { listExecutionRecords } from '#/api/execution-record';
import { useVbenVxeGrid } from '#/adapter/vxe-table';

import RollbackModal from './rollback-modal.vue';

defineOptions({ name: 'InstallationRecord' });

/** 记录类型文案（与后端 ModuleChoices 一致） */
const moduleText: Record<string, string> = {
  MainInstallHistory: '安装',
  RollbackHistory: '回滚',
  UpgradeHistory: '升级',
};

/**
 * 状态圆点：state 子串判色（state_display 提供文案）。
 * 成功→绿 / 失败→红 / 等待·进行中→黄。
 * 旧页把 INSTALL_STATUS_READY（等待安装）归入 '-' 是既有遗漏，这里并入黄色分支修正。
 */
function stateBadge(state?: null | string): {
  status: 'error' | 'success' | 'warning';
} | null {
  if (!state) return null;
  if (state.includes('SUCCESS')) return { status: 'success' };
  if (state.includes('FAIL')) return { status: 'error' };
  if (
    state.includes('WAIT') ||
    state.includes('ING') ||
    state.includes('READY') ||
    state.includes('REGISTER')
  ) {
    return { status: 'warning' };
  }
  return null;
}

/** 格式化时间 */
const formatTime = (value?: null | string) =>
  value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';

const router = useRouter();

/**
 * 「查看」跳转：旧前端经 location.state 传参，目标页尚未迁移，
 * 统一改为 query 透传契约：
 * - 安装：/app_store/installation?uniqueKey=<module_id>&step=3（进入执行步骤）
 * - 回滚：/app_store/service_rollback?history=<module_id>
 * - 升级：/app_store/service_upgrade?history=<module_id>
 */
function goView(row: ExecutionRecordApi.ExecutionRecord) {
  switch (row.module) {
    case 'MainInstallHistory': {
      router.push({
        path: '/application_management/app_store/installation',
        query: { step: '3', uniqueKey: row.module_id },
      });
      break;
    }
    case 'RollbackHistory': {
      router.push({
        path: '/application_management/app_store/service_rollback',
        query: { history: row.module_id },
      });
      break;
    }
    case 'UpgradeHistory': {
      router.push({
        path: '/application_management/app_store/service_upgrade',
        query: { history: row.module_id },
      });
      break;
    }
  }
}

// ---- 回滚弹窗 ----

const rollbackModalOpen = shallowRef(false);
const rollbackHistoryId = shallowRef<null | number | string>(null);

function openRollback(row: ExecutionRecordApi.ExecutionRecord) {
  rollbackHistoryId.value = row.module_id;
  rollbackModalOpen.value = true;
}

/** 回滚下发成功：跳转服务回滚页跟踪进度并刷新列表 */
function onRollbackSubmitted(history: number) {
  router.push({
    path: '/application_management/app_store/service_rollback',
    query: { history: String(history) },
  });
  gridApi.query();
}

const [Grid, gridApi] = useVbenVxeGrid({
  // 高度传导层：Grid 根 div（h-full）不是 flex 容器，窄视口时
  // vxe 表格会按全局 minHeight 撑开、裁掉分页条——让约束传导到 vxe 表格本体
  class: 'flex flex-col',
  gridClass: 'min-h-0 flex-1',
  gridOptions: {
    columns: [
      {
        title: '类型',
        field: 'module',
        width: 100,
        fixed: 'left',
        filters: [
          { label: '安装', value: 'MainInstallHistory' },
          { label: '升级', value: 'UpgradeHistory' },
          { label: '回滚', value: 'RollbackHistory' },
        ],
        slots: {
          default: ({ row }) =>
            moduleText[row.module as string] ?? row.module ?? '-',
        },
      },
      {
        title: '执行用户',
        field: 'operator',
        minWidth: 120,
        formatter: ({ row }) => row.operator || '-',
      },
      {
        title: '状态',
        field: 'state',
        width: 140,
        slots: {
          default: ({ row }) => {
            const badge = stateBadge(row.state as string);
            if (!badge) return '-';
            return h(
              'span',
              { class: 'inline-flex items-center gap-1.5' },
              [
                h(Badge, { status: badge.status }),
                h('span', row.state_display || '-'),
              ],
            );
          },
        },
      },
      {
        title: '服务数量',
        field: 'count',
        width: 90,
        formatter: ({ row }) =>
          row.count === null || row.count === undefined
            ? '-'
            : String(row.count),
      },
      {
        title: '开始时间',
        field: 'created',
        width: 170,
        sortable: true,
        formatter: ({ row }) => formatTime(row.created),
      },
      {
        title: '结束时间',
        field: 'end_time',
        width: 170,
        // 执行中的记录后端尚未回填结束时间，自然显示 -
        formatter: ({ row }) => formatTime(row.end_time),
      },
      {
        title: '用时',
        field: 'duration',
        width: 140,
        formatter: ({ row }) => row.duration || '-',
      },
      {
        title: '操作',
        field: 'action',
        width: 100,
        fixed: 'right',
        slots: {
          default: ({ row }) => {
            const view = h(
              Tooltip,
              { title: '查看执行详情' },
              { default: () => h('a', { onClick: () => goView(row) }, '查看') },
            );
            // 仅升级记录存在回滚，且需后端判定 can_rollback（可回滚版本）
            if (row.module !== 'UpgradeHistory') {
              return h('div', { class: 'flex justify-center' }, view);
            }
            const rollback = row.can_rollback
              ? h(
                  'a',
                  {
                    class: 'ml-2',
                    onClick: () => openRollback(row),
                  },
                  '回滚',
                )
              : h(
                  'span',
                  { class: 'ml-2 cursor-not-allowed opacity-40' },
                  '回滚',
                );
            return h('div', { class: 'flex justify-center' }, [view, rollback]);
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
        query: async ({ page, filters: filterList, sorts }) => {
          // vxe 列筛选（remote）→ module（后端 search_fields=module 模糊匹配）
          const module = filterList?.find(
            (item) => item.field === 'module',
          )?.values?.[0];
          // 远端排序 → DRF ordering（asc → field、desc → -field）
          const sort = sorts?.[0];
          const ordering = sort?.field
            ? `${sort.order === 'desc' ? '-' : ''}${sort.field}`
            : null;
          return await listExecutionRecords({
            page: page.currentPage,
            size: page.pageSize,
            ordering,
            search: module ?? null,
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
    <Grid />
    <RollbackModal
      v-model:open="rollbackModalOpen"
      :history-id="rollbackHistoryId"
      @submitted="onRollbackSubmitted"
    />
  </Page>
</template>
