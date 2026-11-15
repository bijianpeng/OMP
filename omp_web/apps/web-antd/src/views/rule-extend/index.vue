<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { VbenFormProps } from '@vben/common-ui';

import type { RuleCenterApi } from '#/api/rule-center';

import { h, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Button, message, Modal, Table, Tooltip } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  deleteCustomScript,
  listCustomScripts,
  queryScriptJobInfo,
} from '#/api/rule-center';

import ExtendAddModal from './extend-add-modal.vue';
import ExtendEditModal from './extend-edit-modal.vue';

defineOptions({ name: 'RuleExtend' });

const addModalRef = ref<InstanceType<typeof ExtendAddModal>>();
const editModalRef = ref<InstanceType<typeof ExtendEditModal>>();

/** 删除确认（文案与旧前端一致） */
function confirmDelete(row: RuleCenterApi.CustomScript) {
  Modal.confirm({
    content: () =>
      h('div', [
        h('span', '确定要对 '),
        h('span', { class: 'font-medium' }, row.description),
        h('span', ' 指标 '),
        h('span', { class: 'font-medium' }, '下发删除命令'),
        h('span', ' ？'),
      ]),
    okText: '确定',
    cancelText: '取消',
    async onOk() {
      try {
        await deleteCustomScript(row.id);
        message.success('删除操作下发成功');
        gridApi.query();
      } catch {
        // 全局拦截器已提示
      }
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
        placeholder: '请输入描述',
      },
      fieldName: 'description',
      label: '描述',
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
      {
        title: '描述',
        field: 'description',
        width: 220,
        fixed: 'left',
        showOverflow: true,
      },
      {
        title: '绑定主机',
        field: 'bound_hosts_num',
        width: 120,
        slots: {
          // 列头带帮助提示（与旧前端一致）
          header: () =>
            h('span', { class: 'inline-flex items-center gap-1' }, [
              h('span', '绑定主机'),
              h(
                Tooltip,
                {
                  title: '脚本绑定主机数量，绑定主机后会在该主机上采集指标',
                },
                {
                  default: () =>
                    h(IconifyIcon, {
                      class: 'inline align-[-2px]',
                      icon: 'lucide:circle-help',
                    }),
                },
              ),
            ]),
        },
      },
      { title: '探测周期(s)', field: 'scrape_interval', width: 120 },
      {
        title: '操作',
        field: 'action',
        width: 130,
        fixed: 'right',
        slots: {
          default: ({ row }: { row: RuleCenterApi.CustomScript }) => {
            const record = row;
            return h('div', { class: 'flex justify-center gap-2' }, [
              h('a', { onClick: () => editModalRef.value?.open(record) }, '修改'),
              h('a', { onClick: () => openJobInfo(record) }, '查询'),
              h('a', { onClick: () => confirmDelete(record) }, '删除'),
            ]);
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
          return await listCustomScripts({
            description: formValues?.description ?? null,
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

// ── 查询采集作业状态弹窗 ─────────────────────────────────────────

const jobInfoOpen = ref(false);
const jobInfoLoading = ref(false);
const jobInfoRows = ref<RuleCenterApi.ScriptJobInfo[]>([]);

const jobInfoColumns: TableColumnsType = [
  {
    dataIndex: 'scrape_url',
    key: 'scrape_url',
    title: '采集端',
    width: 280,
  },
  { dataIndex: 'status', key: 'status', title: '状态', width: 120 },
  {
    dataIndex: 'last_scrape_duration',
    key: 'last_scrape_duration',
    title: '采集用时',
    width: 120,
  },
  { dataIndex: 'last_error', key: 'last_error', title: '错误信息', width: 220 },
];

async function openJobInfo(record: RuleCenterApi.CustomScript) {
  jobInfoOpen.value = true;
  jobInfoLoading.value = true;
  jobInfoRows.value = [];
  try {
    jobInfoRows.value = await queryScriptJobInfo(record.id);
  } catch {
    // 全局拦截器已提示
  } finally {
    jobInfoLoading.value = false;
  }
}
</script>

<template>
  <!-- content-class 基线：内容区限定高度，grid 高度自适应、表体内部滚动 -->
  <Page content-class="min-h-0 overflow-hidden pb-2">
    <Grid>
      <template #toolbar-actions>
        <Button type="primary" @click="addModalRef?.open()">添加</Button>
      </template>
    </Grid>

    <ExtendAddModal ref="addModalRef" @success="gridApi.query()" />
    <ExtendEditModal ref="editModalRef" @success="gridApi.query()" />

    <Modal
      :footer="null"
      :open="jobInfoOpen"
      :width="900"
      title="查看扩展指标状态"
      @cancel="jobInfoOpen = false"
    >
      <div class="border border-border">
        <Table
          :columns="jobInfoColumns"
          :data-source="jobInfoRows"
          :loading="jobInfoLoading"
          :pagination="false"
          :scroll="{ x: 740 }"
          size="small"
        >
          <template #bodyCell="{ column, text }">
            <template v-if="column.key === 'scrape_url'">
              <Tooltip :title="text || '-'">
                <span>{{ text || '-' }}</span>
              </Tooltip>
            </template>
            <template v-else-if="column.key === 'status'">
              {{ text === 'down' ? '停用' : '正常' }}
            </template>
            <template v-else-if="column.key === 'last_scrape_duration'">
              {{ text ? `${(text * 1000).toFixed(2)}ms` : '-' }}
            </template>
            <template v-else-if="column.key === 'last_error'">
              <Tooltip :title="text || '-'">
                <span>{{ text || '-' }}</span>
              </Tooltip>
            </template>
          </template>
        </Table>
      </div>
    </Modal>
  </Page>
</template>
