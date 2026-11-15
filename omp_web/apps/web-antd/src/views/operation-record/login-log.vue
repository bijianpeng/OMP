<script lang="ts" setup>
import { Page } from '@vben/common-ui';

import { queryLoginLog } from '#/api/operation-record';
import { useVbenVxeGrid } from '#/adapter/vxe-table';

defineOptions({ name: 'LoginLog' });

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
          placeholder: '请输入用户名',
        },
        fieldName: 'username',
        label: '用户名',
      },
    ],
    submitOnChange: true,
  },
  gridOptions: {
    columns: [
      { type: 'seq', title: '序号', width: 70 },
      { title: '用户名', field: 'username', minWidth: 140, sortable: true },
      { title: 'IP地址', field: 'ip', minWidth: 160, sortable: true },
      { title: '角色', field: 'role', minWidth: 140, sortable: true },
      { title: '登录时间', field: 'login_time', minWidth: 180, sortable: true },
    ],
    pagerConfig: { enabled: true, pageSizes: [10, 20, 50, 100] },
    // 自适应父容器高度：表体内部滚动，分页条贴 grid 底部（配合 Page content-class 的 min-h-0）
    height: 'auto',
    // 远程排序：变化触发重新请求（sorts 经 ajax.query 第一参传入）
    sortConfig: { remote: true },
    proxyConfig: {
      autoLoad: true,
      // 排序变化触发重新请求（须配合上方 sortConfig 的 remote）
      sort: true,
      response: { result: 'results', total: 'count' },
      ajax: {
        query: async ({ page, sorts }, formValues) => {
          const sort = sorts?.[0];
          // DRF ordering：ascend → field，descend → -field（修正旧前端 asc→-field 的翻转 bug）
          const ordering = sort?.field
            ? `${sort.order === 'desc' ? '-' : ''}${sort.field}`
            : null;
          return await queryLoginLog({
            page: page.currentPage,
            size: page.pageSize,
            ordering,
            username: formValues.username || null,
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
