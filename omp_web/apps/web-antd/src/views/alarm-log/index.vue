<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { AlarmLogApi } from '#/api/alarm-log';

import { h, onMounted, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import { Button, Drawer, Tag, Tooltip, message } from 'ant-design-vue';
import dayjs from 'dayjs';

import { listAlert, updateAlertRead } from '#/api/alarm-log';
import { getIpList } from '#/api/hosts';
import { useVbenVxeGrid } from '#/adapter/vxe-table';

import { isSafeFrameSrc, withGrafanaTheme } from '#/utils/frame-src';

defineOptions({ name: 'AlarmLog' });

const TIME_FORMAT = 'YYYY-MM-DD HH:mm:ss';

const route = useRoute();
const router = useRouter();

// 旧前端首页跳转参数（location.state）改为 query 透传：
// ip / alert_instance_name / time（单日）；无 time 时默认查近一个月。
// 通过 schema defaultValue 注入表单初始值，随 autoLoad 首查生效。
const { ip: queryIp, time: queryTime, alert_instance_name: queryInstance } =
  route.query;
const defaultTimeRange = (() => {
  if (queryTime) {
    const raw = String(queryTime);
    const day = dayjs(raw);
    // date-only（长度 10，如 2026-11-13）扩展为整日区间：
    // 零宽单点 [T 00:00:00, T 00:00:00] 只匹配恰在零点的记录（后端 range 闭区间）
    if (raw.length === 10 && day.isValid()) {
      return [
        day.startOf('day').format(TIME_FORMAT),
        day.endOf('day').format(TIME_FORMAT),
      ];
    }
    const formatted = day.format(TIME_FORMAT);
    return [formatted, formatted];
  }
  const end = dayjs();
  const start = end.subtract(1, 'month');
  return [start.format(TIME_FORMAT), end.format(TIME_FORMAT)];
})();

/** iframe 抽屉（监控/日志） */
const drawerState = reactive<{
  isOpen: boolean;
  src: string;
  title: string;
}>({ isOpen: false, src: '', title: '' });

/** 格式化时间 */
const formatTime = (value?: null | string) =>
  value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';

/** 级别/类型文案 */
const levelText: Record<string, string> = { critical: '严重', warning: '警告' };
const typeText: Record<string, string> = {
  component: '组件',
  database: '数据库',
  host: '主机',
  service: '服务',
};

/** 已读后刷新 */
async function markRead(ids: number[]) {
  await updateAlertRead(ids);
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
      defaultValue: defaultTimeRange,
      fieldName: 'alert_time_range',
      label: '告警时间',
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
      fieldName: 'alert_host_ip',
      label: 'IP地址',
    },
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '输入实例名称',
      },
      defaultValue: queryInstance ? String(queryInstance) : undefined,
      fieldName: 'alert_instance_name',
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
  gridOptions: {
    columns: [
      // checkbox 需与后续 fixed:'left' 列同组，否则 vxe 会把它排到固定列之后（视觉第二列）
      { type: 'checkbox', width: 44, fixed: 'left' },
      {
        title: '实例名称',
        field: 'alert_instance_name',
        width: 160,
        fixed: 'left',
        slots: {
          default: ({ row }) =>
            h(
              Tooltip,
              { title: row.alert_instance_name ?? '' },
              {
                default: () =>
                  h('span', { class: 'inline-flex items-center gap-1.5' }, [
                    row.is_read === 0
                      ? h('span', {
                          class: 'size-1.5 shrink-0 rounded-full bg-red-500',
                        })
                      : null,
                    h(
                      'span',
                      { class: 'text-xs' },
                      row.alert_instance_name || '-',
                    ),
                  ]),
              },
            ),
        },
      },
      {
        title: 'IP地址',
        field: 'alert_host_ip',
        width: 150,
        sortable: true,
        slots: {
          default: ({ row }) =>
            h(
              'a',
              {
                onClick: () => {
                  if (row.alert_host_ip) {
                    router.push({
                      path: '/resource-management/machine-management',
                      query: { ip: row.alert_host_ip },
                    });
                  }
                },
              },
              row.alert_host_ip ?? '-',
            ),
        },
      },
      {
        title: '级别',
        field: 'alert_level',
        width: 90,
        filters: [
          { label: '严重', value: 'critical' },
          { label: '警告', value: 'warning' },
        ],
        slots: {
          default: ({ row }) => {
            const text = levelText[row.alert_level as string];
            if (!text) return '-';
            // 轻量状态 Tag：严重红 / 其余（警告等）橙；取值映射仍走 levelText，仅改呈现
            return h(
              Tag,
              { color: row.alert_level === 'critical' ? 'red' : 'orange' },
              { default: () => text },
            );
          },
        },
      },
      {
        title: '告警类型',
        field: 'alert_type',
        width: 100,
        filters: [
          { label: '服务', value: 'service' },
          { label: '主机', value: 'host' },
        ],
        slots: {
          default: ({ row }) =>
            typeText[row.alert_type as string] ?? row.alert_type ?? '-',
        },
      },
      {
        title: '告警描述',
        field: 'alert_describe',
        minWidth: 280,
        // 长文本列左对齐（全局 align center 下截断点参差）
        align: 'left',
        showOverflow: true,
        slots: {
          default: ({ row }) => row.alert_describe ?? '-',
        },
      },
      {
        title: '告警时间',
        field: 'alert_time',
        width: 160,
        sortable: true,
        formatter: ({ row }) => formatTime(row.alert_time),
      },
      {
        title: '更新时间',
        field: 'create_time',
        width: 160,
        formatter: ({ row }) => formatTime(row.create_time),
      },
      {
        title: '操作',
        field: 'action',
        width: 110,
        fixed: 'right',
        slots: {
          default: ({ row }) => {
            const children: any[] = [];
            // 监控：打开 iframe 抽屉
            children.push(
              row.monitor_path
                ? h(
                    'a',
                    {
                      onClick: () => {
                        if (row.is_read === 0) markRead([row.id]);
                        Object.assign(drawerState, {
                          isOpen: true,
                          src: row.monitor_path,
                          title: `监控 - ${row.alert_instance_name ?? ''}`,
                        });
                      },
                    },
                    '监控',
                  )
                : h('span', { class: 'cursor-not-allowed opacity-40' }, '监控'),
            );
            // 分析：主机告警跳巡检记录
            if (row.alert_type === 'host') {
              children.push(
                h(
                  'a',
                  {
                    class: 'ml-2',
                    onClick: () => {
                      router.push('/status-patrol/patrol-inspection-record');
                    },
                  },
                  '分析',
                ),
              );
            } else if (row.monitor_log) {
              // 日志：打开 iframe 抽屉
              children.push(
                h(
                  'a',
                  {
                    class: 'ml-2',
                    onClick: () => {
                      if (row.is_read === 0) markRead([row.id]);
                      Object.assign(drawerState, {
                        isOpen: true,
                        src: row.monitor_log,
                        title: `日志 - ${row.alert_instance_name ?? ''}`,
                      });
                    },
                  },
                  '日志',
                ),
              );
            } else {
              children.push(
                h(
                  'span',
                  { class: 'ml-2 cursor-not-allowed opacity-40' },
                  '日志',
                ),
              );
            }
            return h('div', { class: 'flex justify-center gap-2' }, children);
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
          // vxe 列筛选（remote）→ alert_level / alert_type
          const filterValue = (field: string) =>
            filterList?.find((item) => item.field === field)?.values?.[0];
          // 远端排序 → DRF ordering（asc → field、desc → -field；
          // 修正旧前端把"升序"映射为 -field 的颠倒行为）
          const sort = sorts?.[0];
          const ordering = sort?.field
            ? `${sort.order === 'desc' ? '-' : ''}${sort.field}`
            : null;
          // RangePicker 值拆成 start/end 两个查询参数
          const [startAlertTime, endAlertTime] =
            formValues.alert_time_range ?? [];
          return await listAlert({
            page: page.currentPage,
            size: page.pageSize,
            alert_level: filterValue('alert_level') ?? null,
            alert_type: filterValue('alert_type') ?? null,
            alert_host_ip: formValues.alert_host_ip ?? null,
            alert_instance_name: formValues.alert_instance_name ?? null,
            end_alert_time: endAlertTime ?? null,
            start_alert_time: startAlertTime ?? null,
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
          fieldName: 'alert_host_ip',
        },
      ]);
    })
    .catch(() => {});
});

/** 批量已读 */
function markCheckedRead() {
  const checked = gridApi.grid.getCheckboxRecords() as AlarmLogApi.AlertRecord[];
  if (checked.length === 0) {
    message.warning('请先勾选告警记录');
    return;
  }
  markRead(checked.map((item) => item.id));
}
</script>

<template>
  <!-- content-class 基线（pb-2 已升格为统一基线）：内容区限定高度，grid 高度自适应、表体内部滚动 -->
  <Page content-class="min-h-0 overflow-hidden pb-2">
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
