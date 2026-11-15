<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { InspectionApi } from '#/api/inspection';

import { computed, h, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import {
  Collapse,
  CollapsePanel,
  Drawer,
  Empty,
  message,
  Spin,
  Table,
} from 'ant-design-vue';

import { getInspectionReportDetail } from '#/api/inspection';

import ExpandedContent from './expanded-content.vue';
import {
  formatCell,
  formatReportDuration,
  riskLevelCell,
} from './report-format';

defineOptions({ name: 'PatrolInspectionDetail' });

const route = useRoute();
const router = useRouter();

const loading = ref(false);
/** 报告详情；后端巡检报告缺失时 data 为提示文案字符串 */
const report = ref<InspectionApi.ReportDetail>();
const missingTip = ref('');

/** 风险描述 / 进程日志弹层 */
const drawerOpen = ref(false);
const drawerText = ref('');

function showLog(text: string) {
  drawerText.value = text;
  drawerOpen.value = true;
}

// ---- 概述信息 ----

const overviewBlocks = computed(() => {
  const summary = report.value?.summary;
  if (!summary) return [];
  const {
    scan_info: scan,
    scan_result: result,
    task_info: task,
    time_info: time,
  } = summary;
  const blocks: Array<{ lines: string[]; title: string }> = [];
  blocks.push(
    {
      lines: [
        `任务名称：${task?.task_name ?? ''}`,
        `操作人员：${task?.operator ?? ''}`,
        `任务状态：${task?.task_status === 2 ? '已完成' : '失败'}`,
      ],
      title: '任务信息',
    },
    {
      lines: [
        `开始时间：${time?.start_time ?? ''}`,
        `结束时间：${time?.end_time ?? ''}`,
        `任务耗时：${formatReportDuration(time?.cost)}`,
      ],
      title: '时间统计',
    },
  );
  const scanLines: string[] = [];
  if (scan?.host !== undefined && scan.host >= 0) {
    scanLines.push(`主机个数：${scan.host}台`);
  }
  if (scan?.service !== undefined && scan.service >= 0) {
    scanLines.push(`服务个数：${scan.service}个`);
  }
  blocks.push(
    { lines: scanLines, title: '扫描统计' },
    {
      lines: [
        `总指标数：${result?.all_target_num ?? ''}`,
        `异常指标：${result?.abnormal_target ?? ''}`,
      ],
      title: '分析结果',
    },
  );
  return blocks;
});

// ---- 各面板数据 ----

const risks = computed(() => report.value?.risks);
/** risks 存在且 host_list / service_list 任一非空才显示风险指标（旧页语义） */
const hasRisks = computed(
  () =>
    !!risks.value &&
    (risks.value.host_list.length > 0 || risks.value.service_list.length > 0),
);
const topology = computed(() => report.value?.service_topology ?? []);

/** 风险行无唯一键，注入行序键（规避 rowKey index 参数的 antd 弃用告警） */
const riskHostRows = computed(() =>
  (risks.value?.host_list ?? []).map((row, index) => ({
    ...row,
    _rowKey: index,
  })),
);
const riskServiceRows = computed(() =>
  (risks.value?.service_list ?? []).map((row, index) => ({
    ...row,
    _rowKey: index,
  })),
);

const hostRows = computed(() => report.value?.detail_dict?.host ?? []);
const databaseRows = computed(() => report.value?.detail_dict?.database ?? []);
const componentRows = computed(
  () => report.value?.detail_dict?.component ?? [],
);
const serviceRows = computed(() => report.value?.detail_dict?.service ?? []);

// ---- 表格列 ----

/** 空值/状态枚举统一走旧 formatTableRenderData 语义 */
const cellText = ({ text }: { text: unknown }) => formatCell(text);

/** 风险描述点击弹层查看全文（旧页 cursor:pointer span） */
const riskDescribeCell = ({ text }: { text: string }) =>
  h('span', { class: 'cursor-pointer', onClick: () => showLog(text) }, [text]);

const riskHostColumns: TableColumnsType<InspectionApi.ReportRiskRow> = [
  {
    title: '序列',
    key: 'idx',
    width: 50,
    align: 'center',
    customRender: ({ index }) => `${index + 1}`,
  },
  {
    title: 'IP地址',
    dataIndex: 'host_ip',
    width: 150,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '操作系统',
    dataIndex: 'system',
    align: 'center',
    customRender: cellText,
  },
  {
    title: '风险级别',
    dataIndex: 'risk_level',
    align: 'center',
    customRender: riskLevelCell,
  },
  {
    title: '风险描述',
    dataIndex: 'risk_describe',
    width: 400,
    align: 'center',
    ellipsis: true,
    customRender: riskDescribeCell,
  },
  {
    title: '解决方案',
    dataIndex: 'resolve_info',
    align: 'center',
    customRender: cellText,
  },
];

const riskServiceColumns: TableColumnsType<InspectionApi.ReportRiskRow> = [
  {
    title: '序列',
    key: 'idx',
    width: 50,
    align: 'center',
    customRender: ({ index }) => `${index + 1}`,
  },
  {
    title: '服务名称',
    dataIndex: 'service_name',
    align: 'center',
    customRender: cellText,
  },
  {
    title: 'IP地址',
    dataIndex: 'host_ip',
    width: 150,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '端口号',
    dataIndex: 'service_port',
    align: 'center',
    customRender: ({ text }) => text || '-',
  },
  {
    title: '风险级别',
    dataIndex: 'risk_level',
    align: 'center',
    customRender: riskLevelCell,
  },
  {
    title: '风险描述',
    dataIndex: 'risk_describe',
    width: 400,
    align: 'center',
    ellipsis: true,
    customRender: riskDescribeCell,
  },
  {
    title: '解决方案',
    dataIndex: 'resolve_info',
    align: 'center',
    customRender: cellText,
  },
];

/** 主机列表列（旧 report_host_ip/release_version/host_massage 等 10 列） */
const hostColumns: TableColumnsType<InspectionApi.ReportDetailRow> = [
  {
    title: '序列',
    key: 'idx',
    width: 50,
    align: 'center',
    customRender: ({ index }) => `${index + 1}`,
  },
  {
    title: 'IP地址',
    dataIndex: 'host_ip',
    width: 150,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '操作系统',
    dataIndex: 'release_version',
    align: 'center',
    customRender: cellText,
  },
  {
    title: '配置信息',
    dataIndex: 'host_massage',
    align: 'center',
    customRender: cellText,
  },
  {
    title: 'CPU使用率',
    dataIndex: 'cpu_usage',
    width: 110,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '内存使用率',
    dataIndex: 'mem_usage',
    width: 100,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '根分区使用率',
    dataIndex: 'disk_usage_root',
    width: 150,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '数据分区使用率',
    dataIndex: 'disk_usage_data',
    width: 130,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '运行时间',
    dataIndex: 'run_time',
    width: 120,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '平均负载',
    dataIndex: 'sys_load',
    align: 'center',
    customRender: cellText,
  },
];

/** 数据库/组件/服务列表共用列（旧 reportColumnConfig，端口号仅非空显示） */
const serviceColumns: TableColumnsType<InspectionApi.ReportDetailRow> = [
  {
    title: '序列',
    key: 'idx',
    width: 50,
    align: 'center',
    customRender: ({ index }) => `${index + 1}`,
  },
  {
    title: '服务名称',
    dataIndex: 'service_name',
    align: 'center',
    customRender: cellText,
  },
  {
    title: 'IP地址',
    dataIndex: 'host_ip',
    width: 150,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '端口号',
    dataIndex: 'service_port',
    align: 'center',
    customRender: ({ text }) => text || '-',
  },
  {
    title: '运行状态',
    dataIndex: 'service_status',
    align: 'center',
    customRender: cellText,
  },
  {
    title: 'CPU使用率',
    dataIndex: 'cpu_usage',
    width: 110,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '内存使用率',
    dataIndex: 'mem_usage',
    width: 100,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '运行时间',
    dataIndex: 'run_time',
    width: 120,
    align: 'center',
    customRender: cellText,
  },
  {
    title: '日志等级',
    dataIndex: 'log_level',
    align: 'center',
    customRender: cellText,
  },
];

// ---- 行为 ----

async function fetchDetail() {
  loading.value = true;
  try {
    const data = await getInspectionReportDetail(route.params.id as string);
    if (typeof data === 'string') {
      // InspectionReport 缺失：后端以字符串文案返回
      missingTip.value = data;
      report.value = undefined;
    } else {
      report.value = data;
      missingTip.value = '';
    }
  } catch {
    // requestClient 已统一提示
  } finally {
    loading.value = false;
  }
}

function goBack() {
  router.push('/status-patrol/patrol-inspection-record');
}

/** 导出巡检报告（旧 downloadFile：/download-inspection/<file_name>） */
function exportReport() {
  const fileName = report.value?.file_name;
  if (!fileName) {
    message.warning('暂无巡检报告文件');
    return;
  }
  message.success('正在下载巡检报告，双击文件夹中index.html查看报告');
  const link = document.createElement('a');
  link.href = `/download-inspection/${fileName}`;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
}

onMounted(() => {
  fetchDetail();
});
</script>

<template>
  <Page>
    <Spin :spinning="loading">
      <Empty v-if="missingTip" :description="missingTip" class="py-20" />
      <template v-else>
        <!-- 报告标题（旧 reportTitle：标题居中、返回/导出靠右） -->
        <div class="relative mb-5 flex h-10 items-center">
          <div class="w-full text-center text-[22px] font-medium">巡检报告</div>
          <div class="absolute right-2.5 flex gap-2.5 text-blue-500">
            <a class="cursor-pointer pr-2.5" @click="goBack">返回</a>
            <a class="cursor-pointer" @click="exportReport">导出</a>
          </div>
        </div>

        <Collapse
          :bordered="false"
          :default-active-key="[
            'overview',
            'risk',
            'map',
            'host',
            'database',
            'component',
            'service',
          ]"
        >
          <CollapsePanel key="overview" header="概述信息">
            <div class="grid grid-cols-2 gap-x-[1%] gap-y-2.5 py-2.5">
              <div
                v-for="block in overviewBlocks"
                :key="block.title"
                class="flex"
              >
                <div
                  class="flex w-[200px] shrink-0 items-center justify-center border border-r-0 border-border p-2.5 text-muted-foreground"
                >
                  {{ block.title }}
                </div>
                <div
                  class="flex-1 border border-border p-2.5"
                >
                  <div v-for="line in block.lines" :key="line">{{ line }}</div>
                </div>
              </div>
            </div>
          </CollapsePanel>

          <CollapsePanel v-if="hasRisks" key="risk" header="风险指标">
            <Table
              v-if="risks && risks.host_list.length > 0"
              class="mt-5"
              :columns="riskHostColumns"
              :data-source="riskHostRows"
              bordered
              size="small"
              :pagination="false"
              row-key="_rowKey"
            >
              <template #title>主机指标</template>
            </Table>
            <Table
              v-if="risks && risks.service_list.length > 0"
              class="mt-5"
              :columns="riskServiceColumns"
              :data-source="riskServiceRows"
              bordered
              size="small"
              :pagination="false"
              row-key="_rowKey"
            >
              <template #title>服务指标</template>
            </Table>
          </CollapsePanel>

          <CollapsePanel
            v-if="topology.length > 0"
            key="map"
            header="服务平面图"
          >
            <div class="m-2.5 flex flex-row flex-wrap">
              <div
                v-for="node in topology"
                :key="node.host_ip"
                class="mt-2.5 w-full border border-border"
              >
                <div
                  class="h-[30px] border-b border-border bg-muted font-medium leading-[30px]"
                >
                  <span
                    class="ml-5 mr-2.5 inline-block size-2.5 rounded-full bg-[#54bba6]"
                  />
                  {{ node.host_ip }}
                </div>
                <div class="max-h-[240px] overflow-y-auto p-5">
                  <div
                    v-for="service in node.service_list"
                    :key="service"
                    class="mb-2.5 mr-8 h-8 w-[178px] border border-border"
                  >
                    <div class="truncate text-center leading-[30px]">
                      {{ service }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </CollapsePanel>

          <CollapsePanel
            v-if="hostRows.length > 0"
            key="host"
            header="主机列表"
          >
            <Table
              class="mt-5"
              :columns="hostColumns"
              :data-source="hostRows"
              bordered
              size="small"
              :scroll="{ x: 1100 }"
              :pagination="false"
              row-key="id"
            >
              <template #expandedRowRender="{ record }">
                <ExpandedContent :record="record" @show-log="showLog" />
              </template>
            </Table>
          </CollapsePanel>

          <CollapsePanel
            v-if="databaseRows.length > 0"
            key="database"
            header="数据库列表"
          >
            <Table
              class="mt-5"
              :columns="serviceColumns"
              :data-source="databaseRows"
              bordered
              size="small"
              :pagination="false"
              row-key="id"
            >
              <template #expandedRowRender="{ record }">
                <ExpandedContent :record="record" @show-log="showLog" />
              </template>
            </Table>
          </CollapsePanel>

          <CollapsePanel
            v-if="componentRows.length > 0"
            key="component"
            header="组件列表"
          >
            <Table
              class="mt-5"
              :columns="serviceColumns"
              :data-source="componentRows"
              bordered
              size="small"
              :pagination="false"
              row-key="id"
            >
              <template #expandedRowRender="{ record }">
                <ExpandedContent :record="record" @show-log="showLog" />
              </template>
            </Table>
          </CollapsePanel>

          <CollapsePanel
            v-if="serviceRows.length > 0"
            key="service"
            header="服务列表"
          >
            <Table
              class="mt-5"
              :columns="serviceColumns"
              :data-source="serviceRows"
              bordered
              size="small"
              :pagination="false"
              row-key="id"
            >
              <template #expandedRowRender="{ record }">
                <ExpandedContent :record="record" @show-log="showLog" />
              </template>
            </Table>
          </CollapsePanel>
        </Collapse>
      </template>

      <Drawer
        v-model:open="drawerOpen"
        title="进程日志"
        :width="720"
        destroy-on-close
      >
        <div class="whitespace-pre-wrap break-all">{{ drawerText }}</div>
      </Drawer>
    </Spin>
  </Page>
</template>
