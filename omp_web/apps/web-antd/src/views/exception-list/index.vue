<script lang="ts" setup>
import type { VbenFormProps } from '@vben/common-ui';

import type { ExceptionListApi } from '#/api/exception-list';

import { h, onMounted, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import { Drawer, Tag, Tooltip } from 'ant-design-vue';

import { getExceptionList } from '#/api/exception-list';
import { getIpList } from '#/api/hosts';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { isSafeFrameSrc, withGrafanaTheme } from '#/utils/frame-src';

defineOptions({ name: 'ExceptionList' });

const route = useRoute();
const router = useRouter();

// 旧前端首页跳转参数（location.state）改为 query 透传：ip / instance_name / type
// （旧首页"异常服务/组件/实例"跳转携带 type，后端 explain_filter 按同名字段过滤）
const { ip: queryIp, instance_name: queryInstance, type: queryType } =
  route.query;

/** iframe 抽屉（监控/日志） */
const drawerState = reactive<{
  isOpen: boolean;
  src: string;
  title: string;
}>({ isOpen: false, src: '', title: '' });

/** 级别/类型文案 */
const levelText: Record<string, string> = {
  critical: '严重',
  info: '警告',
  warning: '警告',
};
const typeText: Record<string, string> = {
  component: '组件',
  database: '数据库',
  host: '主机',
  service: '服务',
};

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
    {
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '输入实例名称',
      },
      defaultValue: queryInstance ? String(queryInstance) : undefined,
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
      // seq 需与后续 fixed:'left' 列同组，否则 vxe 会把它排到固定列之后（视觉第二列）
      { type: 'seq', title: '序号', width: 70, fixed: 'left' },
      {
        title: '实例名称',
        field: 'instance_name',
        width: 200,
        fixed: 'left',
        showOverflow: true,
        slots: {
          default: ({ row }) =>
            h(
              Tooltip,
              { title: row.instance_name ?? '' },
              { default: () => h('span', row.instance_name ?? '-') },
            ),
        },
      },
      {
        title: 'IP地址',
        field: 'ip',
        width: 160,
        sortable: true,
        slots: {
          default: ({ row }) =>
            h(
              'a',
              {
                onClick: () => {
                  if (row.ip) {
                    router.push({
                      path: '/resource-management/machine-management',
                      query: { ip: row.ip },
                    });
                  }
                },
              },
              row.ip ?? '-',
            ),
        },
      },
      {
        title: '级别',
        field: 'severity',
        width: 100,
        filters: [
          { label: '严重', value: 'critical' },
          { label: '警告', value: 'warning' },
        ],
        slots: {
          default: ({ row }) => {
            const text = levelText[row.severity as string];
            if (!text) return '-';
            // 轻量状态 Tag：严重红 / 其余（警告等）橙；取值映射仍走 levelText，仅改呈现
            return h(
              Tag,
              { color: row.severity === 'critical' ? 'red' : 'orange' },
              { default: () => text },
            );
          },
        },
      },
      {
        title: '告警类型',
        field: 'type',
        width: 110,
        slots: {
          default: ({ row }) => typeText[row.type as string] ?? '-',
        },
      },
      {
        title: '告警描述',
        field: 'description',
        minWidth: 360,
        showOverflow: true,
        slots: {
          default: ({ row }) =>
            h(
              Tooltip,
              { title: row.description ?? '' },
              { default: () => h('span', row.description ?? '-') },
            ),
        },
      },
      {
        title: '告警时间',
        field: 'date',
        width: 170,
        sortable: true,
      },
      {
        title: '操作',
        field: 'action',
        width: 130,
        fixed: 'right',
        slots: {
          default: ({ row }) => {
            const children: any[] = [];
            // 监控：打开 iframe 抽屉
            children.push(
              row.monitor_url
                ? h(
                    'a',
                    {
                      onClick: () => {
                        Object.assign(drawerState, {
                          isOpen: true,
                          src: row.monitor_url,
                          title: `监控 - ${row.instance_name ?? ''}`,
                        });
                      },
                    },
                    '监控',
                  )
                : h('span', { class: 'cursor-not-allowed opacity-40' }, '监控'),
            );
            // 分析：主机告警跳巡检记录
            if (row.type === 'host') {
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
            } else if (row.log_url) {
              // 日志：打开 iframe 抽屉
              children.push(
                h(
                  'a',
                  {
                    class: 'ml-2',
                    onClick: () => {
                      Object.assign(drawerState, {
                        isOpen: true,
                        src: row.log_url,
                        title: `日志 - ${row.instance_name ?? ''}`,
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
        query: async (
          { page, sorts, filters: filterList },
          formValues,
        ): Promise<{
          count: number;
          results: ExceptionListApi.ExceptionRecord[];
        }> => {
          // vxe 列筛选 → severity
          const severity =
            filterList?.find((item) => item.field === 'severity')?.values?.[0] ??
            null;
          // 排序：该接口非 DRF 约定，asc '1' 升序 / '0' 降序
          const sort = sorts?.[0];
          const ordering = sort?.field ?? null;
          const asc = sort?.order === 'asc' ? '1' : '0';
          // 接口返回全量数组，由前端分页
          const all = await getExceptionList({
            asc: ordering ? asc : null,
            instance_name: formValues.instance_name || null,
            ip: formValues.ip || null,
            ordering,
            severity,
            // 旧首页跳转透传的类型过滤（全程生效，等价旧版首次查询行为）
            type: queryType ? String(queryType) : null,
          });
          const start = (page.currentPage - 1) * page.pageSize;
          return {
            count: all.length,
            results: all.slice(start, start + page.pageSize),
          };
        },
      },
    },
    rowConfig: {
      // 不设 keyField：同 IP 可能有多条告警，ip 作键会冲突，走 vxe 默认 _XID
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
          fieldName: 'ip',
        },
      ]);
    })
    .catch(() => {});
});
</script>

<template>
  <Page content-class="min-h-0 overflow-hidden pb-0">
    <Grid />

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
