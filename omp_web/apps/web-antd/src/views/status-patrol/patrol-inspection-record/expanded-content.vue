<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { InspectionApi } from '#/api/inspection';

import { computed, h } from 'vue';

import { Card, Collapse, CollapsePanel, Table } from 'ant-design-vue';

import { formatCell } from './report-format';

defineOptions({ name: 'PatrolExpandedContent' });

interface Props {
  /** 巡检报告明细行（含 basic 与巡检特有数组字段） */
  record: InspectionApi.ReportDetailRow;
}

const props = defineProps<Props>();

const emit = defineEmits<{ 'show-log': [text: string] }>();

/** 基础信息卡片项（旧页对 basic 过滤 cluster_ip 后渲染 BasicCard） */
const basicItems = computed(() =>
  (props.record.basic ?? []).filter((item) => item.name !== 'cluster_ip'),
);

/** basic 值沿用旧页 JSON.stringify 后走通用渲染（null → '-' 等） */
const basicText = (item: InspectionApi.ReportBasicItem) =>
  formatCell(JSON.stringify(item.value));

/** 内存/CPU Top10 进程表列（旧 deal_host_memory_top_columns，进程列点击查看日志） */
const procTopColumns: TableColumnsType = [
  { title: 'TOP', dataIndex: 'TOP', width: 50 },
  { title: 'PID', dataIndex: 'PID', width: 100, align: 'center' },
  { title: '使用率', dataIndex: 'P_RATE', width: 100, align: 'center' },
  {
    title: '进程',
    dataIndex: 'P_CMD',
    customRender: ({ text }) =>
      h(
        'span',
        {
          class: 'cursor-pointer',
          onClick: () => emit('show-log', String(text ?? '')),
        },
        [text],
      ),
  },
];

/** 端口连通性表列（连通性 False 标红，旧 host_port_connectivity_columns） */
const portConnectivityColumns: TableColumnsType = [
  { title: '服务', dataIndex: 'name' },
  { title: 'IP地址', dataIndex: 'ip', align: 'center' },
  { title: '端口', dataIndex: 'port', align: 'center' },
  {
    title: '连通性',
    dataIndex: 'status',
    align: 'center',
    customRender: ({ text }) =>
      h(
        'div',
        { style: text === 'False' ? { color: 'rgb(207, 19, 34)' } : {} },
        [text],
      ),
  },
];

const kafkaPartitionColumns: TableColumnsType = [
  { title: 'Topic', dataIndex: 'topic' },
  { title: '分区数', dataIndex: 'partition', align: 'center' },
  { title: '副本数', dataIndex: 'replication', align: 'center' },
];

const kafkaOffsetsColumns: TableColumnsType = [
  { title: 'Group', dataIndex: 'group' },
  { title: 'Topic', dataIndex: 'topic' },
  { title: 'Log Offset', dataIndex: 'log_offset', align: 'center' },
  { title: 'Lag Offset', dataIndex: 'lag_offset', align: 'center' },
];

const kafkaTopicSizeColumns: TableColumnsType = [
  { title: 'Topic', dataIndex: 'topic' },
  { title: 'Size', dataIndex: 'size', align: 'center' },
];

/** 巡检特有数组字段 → 展开行子面板配置（旧 contentMap） */
const CONTENT_MAP: Record<
  string,
  { columns?: TableColumnsType; plain?: boolean; title: string }
> = {
  port_connectivity: { columns: portConnectivityColumns, title: '端口连通性' },
  memory_top: { columns: procTopColumns, title: '内存使用率Top10进程' },
  cpu_top: { columns: procTopColumns, title: 'cpu使用率Top10进程' },
  kernel_parameters: { plain: true, title: '内核参数' },
  topic_partition: { columns: kafkaPartitionColumns, title: '分区信息' },
  kafka_offsets: { columns: kafkaOffsetsColumns, title: '消费位移信息' },
  topic_size: { columns: kafkaTopicSizeColumns, title: 'Topic消息大小' },
};

/** 按 JSON 键序取已配置的数组字段（未配置项静默跳过，对齐旧页） */
const sectionKeys = computed(() =>
  Object.entries(props.record)
    .filter(([, value]) => Array.isArray(value))
    .map(([key]) => key)
    .filter((key) => key in CONTENT_MAP),
);

const sectionTitle = (key: string) => CONTENT_MAP[key]?.title ?? key;
const sectionColumns = (key: string) => CONTENT_MAP[key]?.columns;
const sectionData = (key: string): unknown[] =>
  (props.record as Record<string, unknown>)[key] as unknown[];

/** 子表行无唯一键，注入行序键（规避 rowKey index 参数的 antd 弃用告警） */
const sectionTableData = (key: string): Array<Record<string, unknown>> =>
  sectionData(key).map((item, index) => ({
    ...(item as Record<string, unknown>),
    _rowKey: index,
  }));
</script>

<template>
  <div>
    <Card v-if="basicItems.length > 0">
      <div class="flex flex-row flex-wrap">
        <div
          v-for="item in basicItems"
          :key="item.name"
          class="mb-2.5 mr-2.5 w-[300px] p-[5px]"
        >
          <span class="text-gray-500">{{ item.name_cn }}: </span>
          <span>{{ basicText(item) }}</span>
        </div>
      </div>
    </Card>

    <Collapse
      v-if="sectionKeys.length > 0"
      :default-active-key="sectionKeys"
      class="mt-2.5"
    >
      <CollapsePanel
        v-for="key in sectionKeys"
        :key="key"
        :header="sectionTitle(key)"
      >
        <Table
          v-if="sectionColumns(key)"
          :columns="sectionColumns(key)"
          :data-source="sectionTableData(key)"
          bordered
          :pagination="false"
          row-key="_rowKey"
          size="small"
        />
        <div v-else class="flex flex-row flex-wrap">
          <div
            v-for="(item, idx) in sectionData(key)"
            :key="idx"
            class="mb-2.5 mr-2.5 w-[300px] p-[5px]"
          >
            {{ item }}
          </div>
        </div>
      </CollapsePanel>
    </Collapse>
  </div>
</template>
