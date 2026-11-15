<script lang="ts" setup>
import type { DataBackupApi } from '#/api/data-backup';

import { h, ref } from 'vue';

import { Page } from '@vben/common-ui';

import { Badge, Button, message, Modal, Tooltip } from 'ant-design-vue';

import { deleteBackupStrategy, executeBackupStrategy, queryBackupSettings } from '#/api/data-backup';
import { useVbenVxeGrid } from '#/adapter/vxe-table';

import CustomParamsModal from './custom-params-modal.vue';
import StrategyModal from './strategy-modal.vue';

defineOptions({ name: 'BackupStrategy' });

/** 星期汉字映射（索引即 crontab day_of_week 值） */
const WEEK_TEXT = [
  '星期一',
  '星期二',
  '星期三',
  '星期四',
  '星期五',
  '星期六',
  '星期日',
];

/** 定时策略展示文案（与旧前端 columns 渲染一致） */
function formatCrontab(row: DataBackupApi.BackupSetting) {
  const crontab = row.crontab_detail;
  if (!crontab) return '-';
  const time = `${crontab.hour}:${crontab.minute}`;
  if (crontab.day_of_month !== '*') return `每月 ${crontab.day_of_month} 日 ${time}`;
  if (crontab.day_of_week !== '*') {
    return `每周 ${WEEK_TEXT[Number(crontab.day_of_week)] ?? crontab.day_of_week} ${time}`;
  }
  return `每天 ${time}`;
}

const strategyModalRef = ref<InstanceType<typeof StrategyModal>>();
const customModalRef = ref<InstanceType<typeof CustomParamsModal>>();

const [Grid, gridApi] = useVbenVxeGrid({
  // flex 传导层：Grid 根 div 转 flex 列，表体内部滚动、分页钉视口底
  class: 'flex flex-col',
  gridClass: 'min-h-0 flex-1',
  gridOptions: {
    columns: [
      { type: 'seq', title: '序号', width: 60 },
      {
        title: '备份实例',
        field: 'backup_instances',
        minWidth: 200,
        formatter: ({ row }) => row.backup_instances?.join(',') ?? '-',
      },
      {
        title: '是否生效',
        field: 'is_on',
        width: 100,
        slots: {
          default: ({ row }) =>
            h('span', { class: 'inline-flex items-center gap-1.5' }, [
              h(Badge, { status: row.is_on ? 'success' : 'error' }),
              h('span', row.is_on ? '是' : '否'),
            ]),
        },
      },
      {
        title: '定时策略',
        field: 'crontab_detail',
        minWidth: 170,
        formatter: ({ row }) => formatCrontab(row),
      },
      {
        title: '保留路径',
        field: 'retain_path',
        minWidth: 170,
        showOverflow: true,
        slots: {
          default: ({ row }) =>
            h(
              Tooltip,
              { title: row.retain_path || '-', placement: 'topLeft' },
              { default: () => h('span', row.retain_path || '-') },
            ),
        },
      },
      {
        title: '保留时间',
        field: 'retain_day',
        width: 100,
        formatter: ({ row }) =>
          row.retain_day === -1 ? '永久保留' : `${row.retain_day} 天`,
      },
      {
        title: '操作',
        field: 'action',
        width: 130,
        fixed: 'right',
        slots: {
          default: ({ row }) => h('div', { class: 'space-x-2.5' }, [
            h('a', { onClick: () => confirmExecute(row) }, '执行'),
            h('a', { onClick: () => strategyModalRef.value?.open(row) }, '编辑'),
            h('a', { onClick: () => confirmDelete(row) }, '删除'),
          ]),
        },
      },
    ],
    height: 'auto',
    // 后端返回全量数组不分页，策略量少直接全量渲染（未启用分页器）
    pagerConfig: { enabled: false },
    proxyConfig: {
      autoLoad: true,
      ajax: {
        // 后端返回全量数组，包一层以命中 response.list 映射
        query: async () => ({ items: await queryBackupSettings() }),
      },
      response: {
        result: 'items',
        list: 'items',
      },
    },
    rowConfig: { keyField: 'id', isCurrent: true },
    toolbarConfig: { refresh: true, zoom: true },
  },
});

/** 刷新策略列表（自定义参数增删改后也需同步，旧页同款行为） */
function refresh() {
  gridApi.query();
}

/** 立即执行备份策略（触发一次备份任务） */
function confirmExecute(row: DataBackupApi.BackupSetting) {
  Modal.confirm({
    content: () =>
      h('div', [
        h('span', '确认对实例 '),
        h(
          'span',
          { class: 'font-medium text-red-500' },
          row.backup_instances?.join(',') ?? '',
        ),
        h('span', ' 执行备份策略吗？'),
      ]),
    okText: '确定',
    cancelText: '取消',
    async onOk() {
      await executeBackupStrategy(row.id);
      message.success('任务下发成功');
    },
  });
}

function confirmDelete(row: DataBackupApi.BackupSetting) {
  Modal.confirm({
    content: () =>
      h('div', [
        h('span', '确定 '),
        h('span', { class: 'font-medium' }, '删除'),
        h('span', ' 该策略吗？'),
      ]),
    okText: '确定',
    cancelText: '取消',
    async onOk() {
      await deleteBackupStrategy(row.id);
      message.success('删除成功');
      refresh();
    },
  });
}
</script>

<template>
  <Page content-class="min-h-0 overflow-hidden">
    <Grid>
      <template #toolbar-actions>
        <Button
          class="mr-2.5"
          type="primary"
          @click="strategyModalRef?.open()"
        >
          添加策略
        </Button>
        <Button @click="customModalRef?.open()">自定义参数</Button>
      </template>
    </Grid>
    <StrategyModal ref="strategyModalRef" @success="refresh" />
    <CustomParamsModal ref="customModalRef" @changed="refresh" />
  </Page>
</template>
