<script lang="ts" setup>
import type { DataBackupApi } from '#/api/data-backup';

import { h } from 'vue';

import { Page } from '@vben/common-ui';

import { Badge, Button, message, Modal, Tooltip } from 'ant-design-vue';
import dayjs from 'dayjs';

import { deleteBackupHistory, queryBackupHistory } from '#/api/data-backup';
import { useVbenVxeGrid } from '#/adapter/vxe-table';

defineOptions({ name: 'BackupRecords' });

/** 状态圆点：0 失败（红）/ 1 成功（绿）/ 2 执行中（黄） */
const resultBadge: Record<number, { status: string; text: string }> = {
  0: { status: 'error', text: '失败' },
  1: { status: 'success', text: '成功' },
  2: { status: 'warning', text: '执行中' },
};

/** 格式化时间 */
const formatTime = (value?: null | string) =>
  value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';

/** 文本单元格：空值显示 -，悬停 Tooltip（照搬旧页语义） */
function renderText(value?: null | string) {
  return h(
    Tooltip,
    { title: value || '-', placement: 'topLeft' },
    { default: () => h('span', value || '-') },
  );
}

const [Grid, gridApi] = useVbenVxeGrid({
  // 根容器转 flex 列并让 vxe-grid 占满剩余高度：表体内部滚动、分页条钉在视口底部
  class: 'flex flex-col',
  gridClass: 'min-h-0 flex-1',
  gridOptions: {
    columns: [
      { type: 'checkbox', width: 50 },
      {
        title: '任务名称',
        field: 'backup_name',
        width: 240,
        fixed: 'left',
        showOverflow: true,
        slots: { default: ({ row }) => renderText(row.backup_name) },
      },
      {
        title: '状态',
        field: 'result',
        width: 100,
        slots: {
          default: ({ row }) => {
            const badge = resultBadge[row.result as number];
            if (!badge) return '-';
            return h(
              'span',
              { class: 'inline-flex items-center gap-1.5' },
              [
                h(Badge, { status: badge.status }),
                h('span', badge.text),
              ],
            );
          },
        },
      },
      {
        title: '备份实例',
        field: 'content',
        width: 140,
        showOverflow: true,
        formatter: ({ row }) => row.content || '-',
      },
      {
        title: '备份文件',
        field: 'file_name',
        width: 180,
        showOverflow: true,
        slots: {
          default: ({ row }) =>
            // 文件已被清理后显示 -
            renderText(row.file_deleted ? null : row.file_name),
        },
      },
      {
        title: '文件大小',
        field: 'file_size',
        width: 90,
        formatter: ({ row }) => row.file_size || '-',
      },
      {
        title: '备份路径',
        field: 'retain_path',
        width: 160,
        showOverflow: true,
        slots: { default: ({ row }) => renderText(row.retain_path) },
      },
      {
        title: '远程路径',
        field: 'remote_path',
        width: 160,
        showOverflow: true,
        slots: { default: ({ row }) => renderText(row.remote_path) },
      },
      {
        title: '过期时间',
        field: 'expire_time',
        width: 170,
        formatter: ({ row }) => formatTime(row.expire_time),
      },
      {
        title: '信息',
        field: 'message',
        width: 180,
        showOverflow: true,
        slots: { default: ({ row }) => renderText(row.message) },
      },
      {
        title: '操作',
        field: 'action',
        width: 100,
        fixed: 'right',
        slots: {
          default: ({ row }) =>
            row.result === 2
              ? // 执行中的记录不可删除
                h('span', { class: 'cursor-not-allowed opacity-40' }, '删除')
              : h(
                  'a',
                  { onClick: () => confirmDelete([row.id]) },
                  '删除',
                ),
        },
      },
    ],
    checkboxConfig: {
      // 执行中的记录不可勾选（与旧前端 notSelectable 一致）
      checkMethod: ({ row }) => row.result !== 2,
    },
    height: 'auto',
    keepSource: true,
    pagerConfig: {
      enabled: true,
      pageSizes: [10, 20, 50, 100],
    },
    proxyConfig: {
      autoLoad: true,
      response: {
        result: 'results',
        total: 'count',
      },
      ajax: {
        query: async ({ page }) => {
          // 后端未启用 OrderingFilter，排序参数不生效，故不提供列排序
          return await queryBackupHistory({
            page: page.currentPage,
            size: page.pageSize,
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

/** 删除确认弹窗（单条/批量共用） */
function confirmDelete(ids: number[]) {
  const isBatch = ids.length > 1;
  Modal.confirm({
    content: () =>
      h('div', [
        h('span', '确定 '),
        h('span', { class: 'font-medium' }, `删除 ${ids.length} `),
        h('span', '条 '),
        h('span', { class: 'font-medium' }, '备份记录'),
        h('span', ' 吗？'),
      ]),
    okText: '确定',
    cancelText: '取消',
    async onOk() {
      await doDelete(ids, isBatch);
    },
  });
}

/** 执行删除并刷新列表 */
async function doDelete(ids: number[], isBatch: boolean) {
  const res = await deleteBackupHistory(ids);
  // 部分文件已不存在时，后端 data 为 {code, message}
  if (res && typeof res === 'object' && res.message) {
    message.warning(String(res.message));
  } else {
    message.success(isBatch ? '删除记录成功' : '删除文件成功');
  }
  gridApi.query();
}

/** 批量删除（toolbar 按钮） */
function deleteChecked() {
  const checked = gridApi.grid.getCheckboxRecords() as DataBackupApi.BackupRecord[];
  if (checked.length === 0) {
    message.warning('请先勾选备份记录');
    return;
  }
  confirmDelete(checked.map((item) => item.id));
}
</script>

<template>
  <Page content-class="min-h-0 overflow-hidden pb-0">
    <Grid>
      <template #toolbar-actions>
        <Button danger type="primary" @click="deleteChecked">删除</Button>
      </template>
    </Grid>
  </Page>
</template>
