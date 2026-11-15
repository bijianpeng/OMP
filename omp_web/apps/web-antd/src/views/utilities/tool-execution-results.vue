<script lang="ts" setup>
import type { UtilitiesApi } from '#/api/utilities';

import { computed, onMounted, onUnmounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Button, Collapse, CollapsePanel, Spin, Table, Tooltip } from 'ant-design-vue';
import dayjs from 'dayjs';
import { useRoute, useRouter } from 'vue-router';

import { queryToolResult } from '#/api/utilities';

defineOptions({ name: 'ToolExecutionResults' });

const route = useRoute();
const router = useRouter();
const routeId = computed(() => route.params.id as string);

/** 任务状态枚举（标题文案与颜色，与旧前端一致） */
const statusTextMap = ['等待执行', '执行中', '执行成功', '执行失败', '任务超时'];
const statusColorMap = ['#ffbf00', '#ffbf00', '#76ca68', '#f04134', '#f04134'];
/** 执行结果页签文案（首个状态旧前端展示「待执行」） */
const tabTextMap = ['待执行', '执行中', '执行成功', '执行失败', '任务超时'];

const loading = ref(false);
const info = ref<UtilitiesApi.ToolResult>();

/** 当前选中状态与 IP（结果页签联动） */
const currentStatus = ref<number>();
const currentIp = ref<string>();

let timer: ReturnType<typeof setTimeout> | undefined;

const formatTime = (value?: null | string) =>
  value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';

async function queryData(init = false) {
  init && (loading.value = true);
  try {
    const data = await queryToolResult(routeId.value);
    info.value = data;
    if (data.tool_detail?.length) {
      if (currentIp.value == null) {
        currentIp.value = data.tool_detail[0]!.ip;
        currentStatus.value = data.tool_detail[0]!.status;
      }
    }
    // 等待执行 / 执行中：持续轮询直到任务结束
    if (data.status === 0 || data.status === 1) {
      timer = setTimeout(() => queryData(), 5000);
    }
  } catch {
    // 全局拦截器已提示
  } finally {
    init && (loading.value = false);
  }
}

function stopPolling() {
  if (timer) {
    clearTimeout(timer);
    timer = undefined;
  }
}

onMounted(() => {
  queryData(true);
});

onUnmounted(() => {
  stopPolling();
});

/** 某状态的明细列表 */
function detailOf(status: number) {
  return info.value?.tool_detail?.filter((item) => item.status === status) ?? [];
}

/** 当前选中明细 */
const currentItem = computed(() =>
  info.value?.tool_detail?.find((item) => item.ip === currentIp.value),
);

/** 切换状态页签：取该状态第一个 IP（数量为 0 时页签禁用） */
function switchStatus(status: number) {
  const list = detailOf(status);
  if (list.length === 0) return;
  currentStatus.value = status;
  currentIp.value = list[0]!.ip;
}

/** 下载执行产物 */
function download(url: string) {
  const fileName = url.split('/').pop() ?? url;
  const link = document.createElement('a');
  link.href = `/${url}`;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
}

const argColumns = [
  { title: '参数名称', dataIndex: 'name', key: 'name', align: 'center' as const, width: 120 },
  { title: '参数值', dataIndex: 'value', key: 'value', align: 'center' as const, width: 120 },
];

const baseInfoItems = computed(() => [
  {
    label: '操作用户',
    tip: '执行本次任务的平台用户',
    value: info.value?.operator || '-',
  },
  {
    label: '执行对象',
    tip: '实用工具操作的目标对象类型，可以是主机或者具体服务',
    value: info.value?.tool?.target_name || '-',
  },
  {
    label: '目标数量',
    tip: '本次执行对象的数量',
    value: `${info.value?.count ?? '-'}`,
  },
  {
    label: '执行用户',
    tip: '工具在目标主机执行的用户名',
    value: info.value?.run_user || '-',
  },
  {
    label: '超时时间 (s)',
    tip: '工具在目标主机的执行的超时时间',
    value: `${info.value?.time_out ?? '-'}`,
  },
  { label: '开始时间', value: formatTime(info.value?.start_time) },
  { label: '结束时间', value: formatTime(info.value?.end_time) },
  { label: '总耗时', value: info.value?.duration || '-' },
]);
</script>

<template>
  <Page>
    <Spin :spinning="loading">
      <div class="flex items-center justify-between pb-3">
        <div class="flex items-center gap-2.5 text-lg text-foreground">
          {{ info?.task_name || '-' }}
          <span
            :style="{ color: statusColorMap[info?.status ?? 0] }"
            class="text-base"
          >
            {{ statusTextMap[info?.status ?? 0] }}
          </span>
        </div>
        <a class="text-sm" @click="router.back()">返回</a>
      </div>

      <Collapse
        :bordered="false"
        :default-active-key="['baseInfo', 'executionInfo', 'executionResult']"
      >
        <CollapsePanel key="baseInfo" header="基本信息">
          <div class="grid grid-cols-4">
            <div
              v-for="item in baseInfoItems"
              :key="item.label"
              class="border-b border-r border-border px-3 py-2.5 last:border-r-0 [&:nth-child(4)]:border-r-0"
            >
              <div class="pb-1 text-gray-500">
                {{ item.label }}
                <Tooltip v-if="'tip' in item && item.tip" :title="item.tip">
                  <IconifyIcon
                    class="inline align-[-2px]"
                    icon="lucide:circle-help"
                  />
                </Tooltip>
              </div>
              <div class="text-foreground">{{ item.value }}</div>
            </div>
          </div>
        </CollapsePanel>
        <CollapsePanel key="executionInfo" header="执行参数信息">
          <div class="mt-2.5 border border-border">
            <Table
              :columns="argColumns"
              :data-source="info?.tool_args ?? []"
              :pagination="false"
              row-key="name"
              size="middle"
            />
          </div>
        </CollapsePanel>
        <CollapsePanel key="executionResult" header="执行结果">
          <div class="mt-2.5">
            <div
              class="flex h-9 w-[450px] border border-b-0 border-border bg-muted"
            >
              <div
                v-for="(text, status) in tabTextMap"
                :key="status"
                class="flex-1 text-center leading-9"
                :class="
                  currentStatus === status
                    ? 'cursor-pointer text-blue-500'
                    : detailOf(status).length === 0
                      ? 'cursor-not-allowed text-gray-400'
                      : 'cursor-pointer text-muted-foreground'
                "
                @click="switchStatus(status)"
              >
                {{ text }}({{ detailOf(status).length }})
              </div>
            </div>
            <div class="flex h-[400px] border border-border">
              <div class="h-full w-[160px] overflow-y-auto">
                <div
                  v-for="item in detailOf(currentStatus ?? 0)"
                  :key="item.ip"
                  class="cursor-pointer py-2.5 text-center"
                  :class="
                    currentIp === item.ip
                      ? 'bg-blue-500 text-white'
                      : 'bg-muted text-foreground'
                  "
                  @click="currentIp = item.ip"
                >
                  {{ item.ip }}
                </div>
              </div>
              <div class="h-full flex-1 bg-muted p-2.5">
                <Button
                  v-if="currentItem?.url"
                  class="mb-2.5"
                  @click="download(currentItem.url)"
                >
                  <template #icon>
                    <IconifyIcon icon="lucide:download" />
                  </template>
                  下载文件
                </Button>
                <div
                  class="h-full overflow-y-auto overflow-x-hidden whitespace-pre-line break-all bg-black p-5 text-white"
                  :style="
                    currentItem?.url ? { height: 'calc(100% - 40px)' } : {}
                  "
                >
                  {{ currentItem?.log || '' }}
                </div>
              </div>
            </div>
          </div>
        </CollapsePanel>
      </Collapse>
    </Spin>
  </Page>
</template>
