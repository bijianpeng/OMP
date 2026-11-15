<script lang="ts" setup>
import type { EnvApi } from '#/api/env';

import { h, ref } from 'vue';

import { Page } from '@vben/common-ui';

import { Button, message, Modal } from 'ant-design-vue';
import dayjs from 'dayjs';

import { deleteEnv, listEnvs } from '#/api/env';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { useEnvStore } from '#/store';

import AuthDrawer from './auth-drawer.vue';
import EnvModal from './env-modal.vue';

defineOptions({ name: 'EnvManagement' });

const envStore = useEnvStore();

const envModalRef = ref<InstanceType<typeof EnvModal>>();
const authDrawerRef = ref<InstanceType<typeof AuthDrawer>>();

/** 格式化时间 */
const formatTime = (value?: null | string) =>
  value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';

const [Grid, gridApi] = useVbenVxeGrid({
  // flex 传导层：Grid 根 div 转 flex 列，表体内部滚动
  class: 'flex flex-col',
  gridClass: 'min-h-0 flex-1',
  gridOptions: {
    columns: [
      { type: 'seq', title: '序号', width: 70 },
      {
        title: '名称',
        field: 'name',
        minWidth: 140,
      },
      {
        title: '环境编码',
        field: 'code',
        width: 140,
      },
      {
        title: '描述',
        field: 'description',
        minWidth: 180,
        formatter: ({ row }) => row.description || '-',
      },
      {
        title: '主机数',
        field: 'host_count',
        width: 90,
      },
      {
        title: '服务数',
        field: 'service_count',
        width: 90,
      },
      {
        title: '创建时间',
        field: 'created',
        width: 170,
        formatter: ({ row }) => formatTime(row.created),
      },
      {
        title: '操作',
        field: 'action',
        width: 160,
        fixed: 'right',
        slots: {
          default: ({ row }) =>
            h('div', { class: 'space-x-2.5' }, [
              h(
                'a',
                { onClick: () => envModalRef.value?.open(row) },
                '编辑',
              ),
              h(
                'a',
                { onClick: () => authDrawerRef.value?.open(row) },
                '授权',
              ),
              h('a', { onClick: () => confirmDelete(row) }, '删除'),
            ]),
        },
      },
    ],
    height: 'auto',
    // 环境列表接口无分页契约（返回全量数组），环境数量少直接全量渲染
    pagerConfig: { enabled: false },
    proxyConfig: {
      autoLoad: true,
      ajax: {
        // 后端返回全量数组，包一层以命中 response.list 映射
        query: async () => ({ items: await listEnvs() }),
      },
      response: { result: 'items', list: 'items' },
    },
    rowConfig: { keyField: 'id', isCurrent: true },
    toolbarConfig: { refresh: true, zoom: true },
  },
});

/**
 * 刷新列表并同步顶栏切换器数据源（envStore.envList）：
 * 新建/删除环境后切换器需立即出现/移除该环境；当前环境被删除时
 * ensureValid 回落到列表第一项，避免后续请求携带失效的 X-Env-Id。
 */
async function refresh() {
  gridApi.query();
  try {
    await envStore.fetchEnvList();
    envStore.ensureValid();
  } catch {
    // 拉取失败由全局拦截器提示，不影响本页表格展示
  }
}

/** 删除环境（二次确认；后端 400 的拒绝原因由全局拦截器 message.error 透传） */
function confirmDelete(row: EnvApi.EnvRecord) {
  Modal.confirm({
    title: '删除环境',
    content: () =>
      h('div', [
        h('span', '确定删除环境 '),
        h('span', { class: 'font-medium text-red-500' }, row.name),
        h(
          'span',
          ' 吗？该环境下的告警规则、阈值等配置将被一并删除，操作不可恢复。',
        ),
      ]),
    okText: '确定',
    cancelText: '取消',
    async onOk() {
      // 默认环境、仍有主机/服务/策略关联或存在进行中任务时后端返回 400
      // （如「默认环境不可删除」），message 由全局拦截器透传展示
      await deleteEnv(row.id);
      message.success('删除环境成功');
      if (envStore.currentEnvId === row.id) {
        // 删除的是当前环境：后续请求携带的 X-Env-Id 已失效，继续留在
        // 本页会全量 403 白屏。先刷新列表拿到删除后的全集，ensureValid
        // 回落到列表第一项（default），持久化生效后整页刷新，让所有
        // 页面按新环境重新拉取数据
        try {
          await envStore.fetchEnvList();
        } catch {
          // 列表拉取失败：reload 后由 env-switcher 的 onMounted 兜底回落
        }
        envStore.ensureValid();
        window.location.reload();
        return;
      }
      await refresh();
    },
  });
}
</script>

<template>
  <Page content-class="min-h-0 overflow-hidden">
    <Grid>
      <template #toolbar-actions>
        <Button class="mr-2.5" type="primary" @click="envModalRef?.open()">
          新建环境
        </Button>
      </template>
    </Grid>
    <EnvModal ref="envModalRef" @success="refresh" />
    <AuthDrawer ref="authDrawerRef" />
  </Page>
</template>
