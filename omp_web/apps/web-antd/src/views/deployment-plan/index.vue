<script lang="ts" setup>
import { h, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import { Button, Modal, Tooltip } from 'ant-design-vue';
import dayjs from 'dayjs';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  getDeploymentOperable,
  listDeploymentPlans,
} from '#/api/deployment-plan';

import ImportPlanModal from './import-plan-modal.vue';

defineOptions({ name: 'DeploymentPlan' });

const router = useRouter();

/** 快速部署可用性：已安装服务后导入入口降级为提示（照搬旧页 operable） */
const operable = ref(false);

/** 不可用提示弹窗 */
const disableOpen = ref(false);

const importModalRef = ref<InstanceType<typeof ImportPlanModal>>();

async function refreshOperable() {
  try {
    operable.value = (await getDeploymentOperable()) === true;
  } catch {
    // 全局拦截器已提示
  }
}

function openImportModal() {
  if (operable.value) {
    importModalRef.value?.open();
  } else {
    disableOpen.value = true;
  }
}

const [Grid, gridApi] = useVbenVxeGrid({
  // 高度传导层：约束传导到 vxe 表格本体（三层布局基线）
  class: 'flex flex-col',
  gridClass: 'min-h-0 flex-1',
  gridOptions: {
    columns: [
      { type: 'seq', title: '编号', width: 140 },
      {
        title: '模板名称',
        field: 'plan_name',
        width: 280,
        showOverflow: true,
        formatter: ({ row }) => row.plan_name || '-',
      },
      {
        title: '主机数量',
        field: 'host_num',
        width: 150,
        formatter: ({ row }) => row.host_num ?? '-',
      },
      {
        title: '产品数量',
        field: 'product_num',
        width: 150,
        formatter: ({ row }) => row.product_num ?? '-',
      },
      {
        title: '服务数量',
        field: 'service_num',
        width: 150,
        formatter: ({ row }) => row.service_num ?? '-',
      },
      {
        title: '创建时间',
        field: 'created',
        width: 175,
        formatter: ({ row }) =>
          row.created
            ? dayjs(row.created).format('YYYY-MM-DD HH:mm:ss')
            : '-',
      },
      {
        title: '创建用户',
        field: 'create_user',
        minWidth: 110,
        // 照搬旧页：创建用户固定展示 Admin
        formatter: () => 'Admin',
      },
      {
        title: '操作',
        field: 'action',
        width: 100,
        fixed: 'right' as const,
        slots: {
          default: ({ row }) =>
            h(
              Tooltip,
              { title: '查看安装流程' },
              {
                default: () =>
                  h(
                    'a',
                    {
                      onClick: () =>
                        router.push({
                          path: '/application_management/app_store/installation',
                          query: {
                            step: '3',
                            uniqueKey: row.operation_uuid,
                          },
                        }),
                    },
                    '安装记录',
                  ),
              },
            ),
        },
      },
    ],
    // 视口自适应：grid 填满父容器高度，表体内部滚动、分页条贴底
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
          // 每次列表查询后同步导入可用性（照搬旧页 fetchData → getOpreable 契约）
          refreshOperable();
          return await listDeploymentPlans({
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

onMounted(() => {
  // 首查前先拉一次可用性，避免按钮态闪烁（列表 ajax 内会持续同步）
  refreshOperable();
});
</script>

<template>
  <!-- content-class 基线：内容区限定高度，grid 高度自适应、表体内部滚动 -->
  <Page content-class="min-h-0 overflow-hidden pb-2">
    <Grid>
      <template #toolbar-actions>
        <Button type="primary" @click="openImportModal">导入模板</Button>
      </template>
    </Grid>

    <!-- 导入部署模板（校验主机/服务分布 → 纳管 → 导入 → 进入安装） -->
    <ImportPlanModal ref="importModalRef" @success="gridApi.query()" />

    <!-- 已安装服务：快速部署不可用提示（照搬旧页 disableModal：仅「确定」按钮） -->
    <Modal v-model:open="disableOpen" title="提示" :footer="null">
      <div class="flex flex-col items-center gap-8 pb-2 pt-4">
        <div class="flex items-start gap-2">
          <span class="pt-0.5 text-xl text-orange-400">!</span>
          <span>已安装服务，快速部署仅在未安装任何服务状态下可用</span>
        </div>
        <Button type="primary" @click="disableOpen = false">确 定</Button>
      </div>
    </Modal>
  </Page>
</template>
