<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { RuleCenterApi } from '#/api/rule-center';

import { h, ref } from 'vue';

import { Page } from '@vben/common-ui';

import { Badge, Button, Dropdown, Menu, message, Modal } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  batchUpdateQuotaRules,
  deleteQuotaRule,
  listQuotaRules,
} from '#/api/rule-center';

import RuleModal from './rule-modal.vue';

defineOptions({ name: 'RuleIndicator' });

const SEVERITY_TEXT: Record<string, string> = {
  critical: '严重',
  warning: '警告',
};
const STATUS_TEXT = ['已停用', '已启用'];
const QUOTA_TYPE_TEXT = ['内置指标', '自定义promsql'];

const modalRef = ref<InstanceType<typeof RuleModal>>();

/** 停用/启用（单个或批量共用），成功提示与旧前端一致 */
async function switchStatus(rows: RuleCenterApi.QuotaRule[], status: 0 | 1) {
  try {
    await batchUpdateQuotaRules(
      rows.map((item) => item.id),
      status,
    );
    message.success(`${status === 1 ? '启用' : '停用'}操作下发成功`);
    gridApi.query();
  } catch {
    // 全局拦截器已提示
  }
}

/** 单条启停确认 */
function confirmSwitchRow(row: RuleCenterApi.QuotaRule) {
  const action = row.status === 1 ? '停用' : '启用';
  Modal.confirm({
    content: () =>
      h('div', [
        h('span', '确定要对 '),
        h('span', { class: 'font-medium' }, row.alert),
        h('span', ` 规则 `),
        h('span', { class: 'font-medium' }, `下发${action}命令`),
        h('span', ' ？'),
      ]),
    okText: '确定',
    cancelText: '取消',
    async onOk() {
      await switchStatus([row], row.status === 1 ? 0 : 1);
    },
  });
}

/** 删除确认（仅 forbidden==1 可删，入口置灰在操作列控制） */
function confirmDelete(row: RuleCenterApi.QuotaRule) {
  Modal.confirm({
    content: () =>
      h('div', [
        h('span', '确定要对 '),
        h('span', { class: 'font-medium' }, row.alert),
        h('span', ' 规则 '),
        h('span', { class: 'font-medium' }, '下发删除命令'),
        h('span', ' ？'),
      ]),
    okText: '确定',
    cancelText: '取消',
    async onOk() {
      try {
        await deleteQuotaRule(row.id);
        message.success('删除操作下发成功');
        gridApi.query();
      } catch {
        // 全局拦截器已提示
      }
    },
  });
}

/** 更多菜单：批量启停入口（未勾选时提示，沿用 alarm-log 批量已读惯例） */
function confirmSwitchBatch(status: 0 | 1) {
  const checked = gridApi.grid.getCheckboxRecords() as RuleCenterApi.QuotaRule[];
  if (checked.length === 0) {
    message.warning('请先勾选规则');
    return;
  }
  const action = status === 1 ? '启用' : '停用';
  Modal.confirm({
    content: () =>
      h('div', [
        h('span', '确定要对 '),
        h('span', { class: 'font-medium' }, `${checked.length}`),
        h('span', ' 条规则 '),
        h('span', { class: 'font-medium' }, `下发${action}命令`),
        h('span', ' ？'),
      ]),
    okText: '确定',
    cancelText: '取消',
    async onOk() {
      await switchStatus(checked, status);
      // 批量操作完成后清空勾选（与旧前端一致）
      gridApi.grid.clearCheckboxRow();
    },
  });
}

const formOptions: VbenFormProps = {
  collapsed: false,
  schema: [
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '请输入规则名称',
      },
      fieldName: 'alert',
      label: '规则名称',
    },
  ],
  submitOnChange: true,
  submitOnEnter: true,
};

const [Grid, gridApi] = useVbenVxeGrid({
  // flex 传导层：Grid 根 div 非 flex 容器，高度约束传不到 vxe-grid（三层基线之一）
  class: 'flex flex-col',
  gridClass: 'min-h-0 flex-1',
  formOptions,
  gridOptions: {
    columns: [
      // checkbox 需与后续 fixed:'left' 列同组，否则 vxe 会把它排到固定列之后（视觉第二列）
      { type: 'checkbox', width: 44, fixed: 'left' },
      {
        title: '规则名称',
        field: 'alert',
        width: 250,
        fixed: 'left',
        showOverflow: true,
      },
      { title: '对比规则', field: 'compare_str', width: 120 },
      { title: '阈值', field: 'threshold_value', width: 120 },
      { title: '持续时长(s)', field: 'for_time', width: 120 },
      {
        title: '级别',
        field: 'severity',
        width: 100,
        slots: {
          default: ({ row }: { row: RuleCenterApi.QuotaRule }) =>
            SEVERITY_TEXT[row.severity as string] ?? row.severity ?? '-',
        },
      },
      {
        title: '状态',
        field: 'status',
        width: 100,
        slots: {
          default: ({ row }: { row: RuleCenterApi.QuotaRule }) =>
            h('span', { class: 'inline-flex items-center gap-1.5' }, [
              h(Badge, {
                status: row.status === 1 ? 'success' : 'default',
              }),
              h('span', STATUS_TEXT[row.status as number] ?? '-'),
            ]),
        },
      },
      {
        title: '指标类型',
        field: 'quota_type',
        width: 120,
        formatter: ({ row }: { row: RuleCenterApi.QuotaRule }) =>
          QUOTA_TYPE_TEXT[row.quota_type as number] ?? row.quota_type ?? '-',
      },
      {
        title: '操作',
        field: 'action',
        width: 150,
        fixed: 'right',
        slots: {
          default: ({ row }: { row: RuleCenterApi.QuotaRule }) => {
            const record = row;
            const children: any[] = [
              h(
                'a',
                { onClick: () => modalRef.value?.open(record) },
                '修改',
              ),
              h(
                'a',
                {
                  class: 'ml-2',
                  onClick: () => confirmSwitchRow(record),
                },
                record.status === 1 ? '停用' : '启用',
              ),
            ];
            // forbidden==1 才可删除，否则置灰禁点（与旧前端一致）
            children.push(
              record.forbidden === 1
                ? h(
                    'a',
                    {
                      class: 'ml-2',
                      onClick: () => confirmDelete(record),
                    },
                    '删除',
                  )
                : h(
                    'span',
                    { class: 'ml-2 cursor-not-allowed opacity-40' },
                    '删除',
                  ),
            );
            return h('div', { class: 'flex justify-center' }, children);
          },
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
        result: 'results',
        total: 'count',
      },
      ajax: {
        query: async (
          { page }: { page: { currentPage: number; pageSize: number } },
          formValues: Record<string, any>,
        ) => {
          return await listQuotaRules({
            alert: formValues?.alert ?? null,
            ordering: null,
            page: page.currentPage,
            size: page.pageSize,
          });
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
        <Button type="primary" @click="modalRef?.open()">添加</Button>
        <Dropdown class="ml-2">
          <Button>更多</Button>
          <template #overlay>
            <Menu>
              <Menu.Item key="start" @click="confirmSwitchBatch(1)">
                启用规则
              </Menu.Item>
              <Menu.Item key="stop" @click="confirmSwitchBatch(0)">
                停用规则
              </Menu.Item>
            </Menu>
          </template>
        </Dropdown>
      </template>
    </Grid>

    <RuleModal ref="modalRef" @success="gridApi.query()" />
  </Page>
</template>
