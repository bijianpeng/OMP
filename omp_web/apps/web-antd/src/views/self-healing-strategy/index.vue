<script lang="ts" setup>
import type { SelfHealingStrategyApi } from '#/api/self-healing-strategy';

import { h, ref } from 'vue';

import { Page } from '@vben/common-ui';

import { Badge, Button, message, Popconfirm, Tooltip } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  deleteSelfHealingStrategy,
  listSelfHealingStrategies,
} from '#/api/self-healing-strategy';

import StrategyModal from './strategy-modal.vue';

defineOptions({ name: 'SelfHealingStrategy' });

/** 自愈维度文案映射（与旧前端 columns 一致） */
const DIMENSION_TEXT: Record<string, string> = {
  component: '基础组件',
  host: '主机监控Agent',
  service: '自研服务',
};

const modalRef = ref<InstanceType<typeof StrategyModal>>();

/** 删除策略（接口无联锁数据影响，Popconfirm 二次确认与旧弹窗确认同等强度） */
async function handleDelete(id: number) {
  try {
    await deleteSelfHealingStrategy(id);
    message.success('删除成功');
    gridApi.query();
  } catch {
    // 全局拦截器已提示错误信息
  }
}

const [Grid, gridApi] = useVbenVxeGrid({
  // flex 传导层：Grid 根 div 非 flex 容器，高度约束传不到 vxe-grid（三层基线之一）
  class: 'flex flex-col',
  gridClass: 'min-h-0 flex-1',
  gridOptions: {
    columns: [
      { title: '序号', field: '_idx', width: 70 },
      {
        title: '自愈维度',
        field: 'repair_instance',
        minWidth: 220,
        showOverflow: true,
        slots: {
          default: ({ row }) => {
            const text = (row.repair_instance as string[])
              .map((item) => DIMENSION_TEXT[item] ?? item)
              .join(', ');
            return h(
              Tooltip,
              { title: text },
              { default: () => h('span', text) },
            );
          },
        },
      },
      {
        title: '自愈类型',
        field: 'instance_tp',
        minWidth: 130,
        formatter: ({ row }) =>
          row.instance_tp === 0 ? '启动 [start]' : '重启 [restart]',
      },
      {
        title: '探测周期',
        field: 'fresh_rate',
        minWidth: 100,
        formatter: ({ row }) => `${row.fresh_rate} min`,
      },
      { title: '重试次数', field: 'max_healing_count', minWidth: 100 },
      {
        title: '是否生效',
        field: 'used',
        minWidth: 100,
        slots: {
          default: ({ row }) =>
            h('span', { class: 'inline-flex items-center gap-1.5' }, [
              h(Badge, { status: row.used ? 'success' : 'error' }),
              h('span', row.used ? '是' : '否'),
            ]),
        },
      },
      {
        title: '操作',
        field: 'action',
        minWidth: 120,
        fixed: 'right',
        slots: {
          default: ({ row }) =>
            h('div', { class: 'flex justify-center gap-2' }, [
              h(
                'a',
                {
                  onClick: () => modalRef.value?.open(row as SelfHealingStrategyApi.Strategy),
                },
                '编辑',
              ),
              h(
                Popconfirm,
                {
                  title: '确定删除该策略吗？',
                  onConfirm: () => handleDelete(row.id as number),
                },
                { default: () => h('a', '删除') },
              ),
            ]),
        },
      },
    ],
    // 视口自适应：grid 填满父容器高度，表体内部滚动、分页条贴底（三层基线之二）
    height: 'auto',
    keepSource: true,
    pagerConfig: {
      enabled: true,
      pageSizes: [10, 20, 50, 100],
    },
    proxyConfig: {
      autoLoad: true,
      response: {
        result: 'items',
        total: 'total',
      },
      ajax: {
        query: async ({ page }) => {
          // 接口返回全量数组（无分页/排序/筛选契约），分页由前端本地切片，
          // 序号为全量连续编号（对齐旧前端 _idx）
          const all = await listSelfHealingStrategies();
          const start = (page.currentPage - 1) * page.pageSize;
          const items = all
            .slice(start, start + page.pageSize)
            .map((item, idx) => ({ ...item, _idx: start + idx + 1 }));
          return { items, total: all.length };
        },
      },
    },
    rowConfig: {
      keyField: 'id',
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
        <Button type="primary" @click="modalRef?.open()">添加策略</Button>
      </template>
    </Grid>

    <StrategyModal ref="modalRef" @success="gridApi.query()" />
  </Page>
</template>
