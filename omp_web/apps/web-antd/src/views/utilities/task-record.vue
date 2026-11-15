<script lang="ts" setup>
import { Page } from '@vben/common-ui';

import { h } from 'vue';
import { useRouter } from 'vue-router';

import { Tag } from 'ant-design-vue';
import dayjs from 'dayjs';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { queryTaskRecord } from '#/api/utilities';

defineOptions({ name: 'TaskRecord' });

const router = useRouter();

/** 工具分类枚举（与后端 ToolInfo.kind 一致） */
const kindText: Record<number, string> = {
  0: '管理工具',
  1: '检查工具',
  2: '安全工具',
  3: '其他工具',
};

/** 执行状态枚举（与后端 ToolExecuteMainHistory.STATUS_TYPE_CHOICES 一致） */
const statusMap: Record<number, { color: string; text: string }> = {
  0: { color: 'warning', text: '待执行' },
  1: { color: 'warning', text: '执行中' },
  2: { color: 'success', text: '执行成功' },
  3: { color: 'error', text: '执行失败' },
};

/** 格式化时间 */
const formatTime = (value?: null | string) =>
  value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';

/** 跳转执行结果页 */
function goExecutionResults(id: number) {
  router.push(`/utilitie/tool-management/tool-execution-results/${id}`);
}

const [Grid] = useVbenVxeGrid({
  // flex 传导层：Grid 根 div 非 flex 容器，多字段表单 + 窄视口时高度约束传不到 vxe-grid
  class: 'flex flex-col',
  gridClass: 'min-h-0 flex-1',
  formOptions: {
    collapsed: false,
    schema: [
      {
        component: 'Input',
        componentProps: {
          allowClear: true,
          placeholder: '请输入名称',
        },
        fieldName: 'search',
        label: '名称',
      },
    ],
    submitOnChange: true,
  },
  gridOptions: {
    columns: [
      {
        title: '任务标题',
        field: 'task_name',
        minWidth: 200,
        fixed: 'left',
        slots: {
          default: ({ row }) =>
            h(
              'a',
              {
                onClick: () => goExecutionResults(row.id),
              },
              row.task_name ?? '-',
            ),
        },
      },
      {
        title: '分类',
        field: 'kind',
        width: 120,
        filters: [
          { label: '管理工具', value: 0 },
          { label: '检查工具', value: 1 },
          { label: '安全工具', value: 2 },
          { label: '其他工具', value: 3 },
        ],
        slots: {
          default: ({ row }) => kindText[row.kind as number] ?? '-',
        },
      },
      {
        title: '执行时间',
        field: 'start_time',
        width: 180,
        sortable: true,
        formatter: ({ row }) => formatTime(row.start_time),
      },
      {
        title: '状态',
        field: 'status',
        width: 110,
        slots: {
          default: ({ row }) => {
            const status = statusMap[row.status as number];
            return status
              ? h(Tag, { color: status.color }, { default: () => status.text })
              : '-';
          },
        },
      },
      { title: '执行用时', field: 'duration', width: 140 },
      {
        title: '操作',
        field: 'action',
        width: 90,
        fixed: 'right',
        slots: {
          default: ({ row }) =>
            h(
              'a',
              {
                onClick: () => goExecutionResults(row.id),
              },
              '查看',
            ),
        },
      },
    ],
    pagerConfig: { enabled: true, pageSizes: [10, 20, 50, 100] },
    // 自适应父容器高度：表体内部滚动，分页条贴 grid 底部（配合 Page content-class 的 min-h-0）
    height: 'auto',
    // 远程排序 / 远程列筛选：变化触发重新请求（sorts / filters 经 ajax.query 第一参传入）
    sortConfig: { remote: true },
    filterConfig: { remote: true },
    proxyConfig: {
      autoLoad: true,
      // 排序/筛选变化触发重新请求（须配合上方 sortConfig/filterConfig 的 remote）
      sort: true,
      filter: true,
      response: { result: 'results', total: 'count' },
      ajax: {
        query: async ({ page, filters, sorts }, formValues) => {
          const sort = sorts?.[0];
          // DRF ordering：ascend → field，descend → -field（修正旧前端 asc→-field 的翻转 bug）
          const ordering = sort?.field
            ? `${sort.order === 'desc' ? '-' : ''}${sort.field}`
            : null;
          // vxe 列筛选（filters 为数组）→ kind
          const kind = filters?.find((f) => f.field === 'kind')?.values?.[0];
          return await queryTaskRecord({
            page: page.currentPage,
            size: page.pageSize,
            ordering,
            kind: kind ?? null,
            search: formValues.search || null,
          });
        },
      },
    },
    rowConfig: { keyField: 'id' },
    toolbarConfig: { refresh: true, zoom: true, column: true },
  },
});
</script>

<template>
  <Page content-class="min-h-0 overflow-hidden">
    <Grid />
  </Page>
</template>
