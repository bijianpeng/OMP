<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { SelfHealingApi } from '#/api/self-healing';

import { h, onMounted, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import { Badge, Button, Drawer, Tooltip, message } from 'ant-design-vue';
import dayjs from 'dayjs';

import { getIpList } from '#/api/hosts';
import {
  listSelfHealingHistory,
  updateSelfHealingHistoryRead,
} from '#/api/self-healing';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { isSafeFrameSrc, withGrafanaTheme } from '#/utils/frame-src';

defineOptions({ name: 'SelfHealingRecord' });

const TIME_FORMAT = 'YYYY-MM-DD HH:mm:ss';

const route = useRoute();
const router = useRouter();

// 旧前端首页跳转参数（location.state）改为 query 透传：ip
const { ip: queryIp } = route.query;

/** iframe 抽屉（服务日志） */
const drawerState = reactive<{
  isOpen: boolean;
  src: string;
  title: string;
}>({ isOpen: false, src: '', title: '' });

/** 自愈状态圆点：0 失败（红）/ 1 成功（绿）/ 2 自愈中（黄） */
const stateBadge: Record<number, { status: string; text: string }> = {
  0: { status: 'error', text: '自愈失败' },
  1: { status: 'success', text: '自愈成功' },
  2: { status: 'warning', text: '自愈中' },
};

/** 格式化时间 */
const formatTime = (value?: null | string) =>
  value ? dayjs(value).format(TIME_FORMAT) : '-';

/** 已读后刷新 */
async function markRead(ids: number[]) {
  await updateSelfHealingHistoryRead(ids);
  message.success('已读成功');
  gridApi.query();
}

const formOptions: VbenFormProps = {
  collapsed: false,
  schema: [
    {
      component: 'RangePicker',
      componentProps: {
        format: TIME_FORMAT,
        showTime: { format: 'HH:mm:ss' },
        valueFormat: TIME_FORMAT,
      },
      fieldName: 'alert_time_range',
      label: '故障时间',
    },
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [],
        placeholder: '选择主机 IP',
        showSearch: true,
      },
      defaultValue: queryIp ? String(queryIp) : undefined,
      fieldName: 'host_ip',
      label: 'IP地址',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '输入实例名称',
      },
      fieldName: 'instance_name',
      label: '实例名称',
    },
  ],
  submitOnChange: true,
  submitOnEnter: true,
};

const [Grid, gridApi] = useVbenVxeGrid({
  // 根容器转 flex 列并让 vxe-grid 占满剩余高度：表体内部滚动、分页条钉在视口底部
  class: 'flex flex-col',
  gridClass: 'min-h-0 flex-1',
  formOptions,
  gridOptions: {
    columns: [
      // checkbox 需与后续 fixed:'left' 列同组，否则 vxe 会把它排到固定列之后（视觉第二列）
      { type: 'checkbox', width: 50, fixed: 'left' },
      {
        title: '实例名称',
        field: 'instance_name',
        width: 200,
        fixed: 'left',
        sortable: true,
        showOverflow: true,
        slots: {
          default: ({ row }) =>
            h(
              Tooltip,
              { title: row.instance_name ?? '' },
              {
                default: () =>
                  h(
                    Badge,
                    {
                      dot: row.is_read === 0,
                      offset: [4, 0],
                      status: 'error',
                    },
                    {
                      default: () =>
                        h('span', { class: 'text-xs' }, [
                          row.instance_name || '-',
                        ]),
                    },
                  ),
              },
            ),
        },
      },
      {
        title: 'IP地址',
        field: 'host_ip',
        width: 160,
        sortable: true,
        formatter: ({ row }) => row.host_ip ?? '-',
      },
      {
        title: '自愈状态',
        field: 'state',
        width: 120,
        filters: [
          { label: '自愈成功', value: '1' },
          { label: '自愈失败', value: '0' },
          { label: '自愈中', value: '2' },
        ],
        slots: {
          default: ({ row }) => {
            const badge = stateBadge[row.state as number];
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
        title: '重试次数',
        field: 'healing_count',
        width: 90,
        formatter: ({ row }) => (row.healing_count ? `${row.healing_count}次` : '-'),
      },
      {
        title: '故障时间',
        field: 'alert_time',
        width: 170,
        formatter: ({ row }) => formatTime(row.alert_time),
      },
      {
        title: '结束时间',
        field: 'end_time',
        width: 170,
        formatter: ({ row }) => formatTime(row.end_time),
      },
      {
        title: '故障描述',
        field: 'alert_content',
        minWidth: 260,
        showOverflow: true,
        slots: {
          default: ({ row }) =>
            h(
              Tooltip,
              { title: row.alert_content ?? '' },
              { default: () => h('span', row.alert_content ?? '-') },
            ),
        },
      },
      {
        title: '自愈日志',
        field: 'healing_log',
        width: 220,
        showOverflow: true,
        slots: {
          default: ({ row }) =>
            h(
              Tooltip,
              { title: row.healing_log ?? '', placement: 'topLeft' },
              { default: () => h('span', row.healing_log ?? '-') },
            ),
        },
      },
      {
        title: '操作',
        field: 'action',
        width: 150,
        fixed: 'right',
        slots: {
          default: ({ row }) => {
            const children: any[] = [];
            // 关联告警：跳告警记录并透传实例名 + 故障时间
            children.push(
              row.instance_name
                ? h(
                    'a',
                    {
                      onClick: () => {
                        router.push({
                          path: '/application-monitoring/alarm-log',
                          query: {
                            alert_instance_name: row.instance_name,
                            time: row.alert_time ?? undefined,
                          },
                        });
                      },
                    },
                    '关联告警',
                  )
                : h(
                    'span',
                    { class: 'cursor-not-allowed opacity-40' },
                    '关联告警',
                  ),
            );
            // 服务日志：打开 iframe 抽屉，未读先标记
            children.push(
              row.monitor_log
                ? h(
                    'a',
                    {
                      class: 'ml-2',
                      onClick: () => {
                        if (row.is_read === 0) markRead([row.id]);
                        Object.assign(drawerState, {
                          isOpen: true,
                          src: row.monitor_log,
                          title: `服务日志 - ${row.instance_name ?? ''}`,
                        });
                      },
                    },
                    '服务日志',
                  )
                : h(
                    'span',
                    { class: 'ml-2 cursor-not-allowed opacity-40' },
                    '服务日志',
                  ),
            );
            return h('div', { class: 'flex justify-center gap-2' }, children);
          },
        },
      },
    ],
    filterConfig: {
      // 列筛选变化时触发 proxy query，由后端过滤
      remote: true,
    },
    height: 'auto',
    keepSource: true,
    pagerConfig: {
      enabled: true,
      pageSizes: [10, 20, 50, 100],
    },
    proxyConfig: {
      autoLoad: true,
      // 排序/筛选变化时联动触发 query（需配合 sortConfig/filterConfig.remote）
      filter: true,
      sort: true,
      response: {
        result: 'results',
        total: 'count',
      },
      ajax: {
        query: async ({ page, sorts, filters: filterList }, formValues) => {
          // vxe 列筛选 → state（后端为字符串模糊匹配）
          const state =
            filterList?.find((item) => item.field === 'state')?.values?.[0] ??
            null;
          // DRF ordering 标准语义：ascend → field（升序），descend → -field（降序）
          // （旧前端此处映射相反，属既有 bug，勿照搬）
          const sort = sorts?.[0];
          const ordering = sort?.field
            ? `${sort.order === 'desc' ? '-' : ''}${sort.field}`
            : null;
          const [startTime, endTime] = formValues.alert_time_range ?? [];
          return await listSelfHealingHistory({
            page: page.currentPage,
            size: page.pageSize,
            host_ip: formValues.host_ip ?? null,
            instance_name: formValues.instance_name || null,
            ordering,
            query_end_time: endTime ?? null,
            query_start_time: startTime ?? null,
            state,
          });
        },
      },
    },
    rowConfig: {
      keyField: 'id',
      isCurrent: true,
    },
    sortConfig: {
      // 排序变化时触发 proxy query，由后端排序
      remote: true,
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
          fieldName: 'host_ip',
        },
      ]);
    })
    .catch(() => {});
});

/** 批量已读 */
function markCheckedRead() {
  const checked = gridApi.grid.getCheckboxRecords() as SelfHealingApi.SelfHealingRecord[];
  if (checked.length === 0) {
    message.warning('请先勾选自愈记录');
    return;
  }
  markRead(checked.map((item) => item.id));
}
</script>

<template>
  <Page content-class="min-h-0 overflow-hidden pb-0">
    <Grid>
      <template #toolbar-actions>
        <Button type="primary" @click="markCheckedRead">批量已读</Button>
      </template>
    </Grid>

    <Drawer
      v-model:open="drawerState.isOpen"
      :title="drawerState.title"
      placement="right"
      width="70%"
      destroy-on-close
      :body-style="{ padding: 0 }"
      :header-style="{ background: 'hsl(var(--background-deep))' }"
    >
      <iframe
        v-if="drawerState.isOpen && isSafeFrameSrc(drawerState.src)"
        :src="withGrafanaTheme(drawerState.src)"
        class="h-full w-full border-0"
      />
    </Drawer>
  </Page>
</template>
