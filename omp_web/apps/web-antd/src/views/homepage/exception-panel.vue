<script lang="ts" setup>
import type {
  TableColumnType,
  TablePaginationConfig,
} from 'ant-design-vue';

import type { ExceptionListApi } from '#/api/exception-list';

import type { Key } from 'ant-design-vue/es/table/interface';

import { onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Badge, Drawer, Table, Tooltip } from 'ant-design-vue';

import { getExceptionList } from '#/api/exception-list';
import { isSafeFrameSrc, withGrafanaTheme } from '#/utils/frame-src';

/**
 * 仪表盘内嵌「异常清单」小表（旧前端 HomePage/warningList 等价物）。
 * 全量拉取 + 前端分页（默认 5 条）；远端排序（asc '1'/'0' 自定义契约）；
 * 跳转全部转 query：IP→主机管理、异常项→异常清单语义由主页状态块承担、
 * 告警→告警记录?ip=&time=（单日）。
 */
const router = useRouter();

const loading = ref(false);
const dataSource = ref<ExceptionListApi.ExceptionRecord[]>([]);

const pagination = reactive({
  current: 1,
  pageSize: 5,
  pageSizeOptions: ['5', '10', '20', '50'],
  showSizeChanger: true,
  showTotal: (total: number) => `共计 ${total} 条`,
  total: 0,
});

/** 远端排序状态（该接口为 asc '1' 升序 / '0' 降序，非 DRF 约定） */
const sortState = reactive<{ asc: null | string; ordering: null | string }>({
  asc: null,
  ordering: null,
});

async function fetchData() {
  loading.value = true;
  try {
    const all = await getExceptionList({
      asc: sortState.ordering ? sortState.asc : null,
      ordering: sortState.ordering,
    });
    dataSource.value = all;
    pagination.total = all.length;
    // 数据刷新后页码可能越界，回归首页
    pagination.current = 1;
  } finally {
    loading.value = false;
  }
}

/** onChange 排序参数的最小结构（仅消费 columnKey/order） */
interface SingleSorter {
  columnKey?: Key;
  order?: 'ascend' | 'descend' | null;
}

function handleTableChange(
  pag: TablePaginationConfig,
  _filters: Record<string, null | (boolean | number | string)[]>,
  sorter: SingleSorter | SingleSorter[],
) {
  pagination.current = pag.current ?? pagination.current;
  pagination.pageSize = pag.pageSize ?? pagination.pageSize;
  const single = Array.isArray(sorter) ? sorter[0] : sorter;
  if (single?.columnKey && single.order) {
    sortState.ordering = String(single.columnKey);
    sortState.asc = single.order === 'ascend' ? '1' : '0';
    fetchData();
  }
}

/** iframe 抽屉（监控/日志），与异常清单页同款契约 */
const drawerState = reactive<{
  isOpen: boolean;
  src: string;
  title: string;
}>({ isOpen: false, src: '', title: '' });

function openDrawer(src: null | string, title: string) {
  Object.assign(drawerState, { isOpen: true, src: src ?? '', title });
}

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

const columns: TableColumnType[] = [
  {
    align: 'center',
    dataIndex: 'instance_name',
    ellipsis: true,
    key: 'instance_name',
    sortDirections: ['descend', 'ascend'],
    sorter: true,
    title: '实例名称',
    width: 180,
  },
  {
    align: 'center',
    dataIndex: 'ip',
    ellipsis: true,
    key: 'ip',
    sortDirections: ['descend', 'ascend'],
    sorter: true,
    title: 'IP地址',
    width: 140,
  },
  { align: 'center', dataIndex: 'severity', key: 'severity', title: '级别', width: 90 },
  { align: 'center', dataIndex: 'type', key: 'type', title: '告警类型', width: 100 },
  {
    align: 'center',
    dataIndex: 'description',
    ellipsis: true,
    key: 'description',
    title: '告警描述',
  },
  {
    align: 'center',
    dataIndex: 'date',
    key: 'date',
    sortDirections: ['descend', 'ascend'],
    sorter: true,
    title: '告警时间',
    width: 170,
  },
  { align: 'center', key: 'action', title: '操作', width: 170 },
];

onMounted(() => {
  fetchData();
});
</script>

<template>
  <div class="border-border border">
    <Table
      :columns="columns"
      :data-source="dataSource"
      :loading="loading"
      :pagination="pagination"
      :row-key="(record) => `${record.ip}-${record.instance_name}-${record.date}`"
      size="small"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'instance_name'">
          <Tooltip :title="record.instance_name ?? ''">
            <Badge :dot="record.is_read === 0" :offset="[5, 2]">
              <span class="text-xs">{{ record.instance_name || '-' }}</span>
            </Badge>
          </Tooltip>
        </template>
        <template v-else-if="column.key === 'ip'">
          <a
            v-if="record.ip"
            @click="
              router.push({
                path: '/resource-management/machine-management',
                query: { ip: record.ip },
              })
            "
          >
            {{ record.ip }}
          </a>
          <span v-else>-</span>
        </template>
        <template v-else-if="column.key === 'severity'">
          <span
            :class="
              record.severity === 'critical'
                ? 'text-red-500'
                : record.severity === 'warning'
                  ? 'text-orange-500'
                  : ''
            "
          >
            {{ levelText[record.severity] ?? '-' }}
          </span>
        </template>
        <template v-else-if="column.key === 'type'">
          {{ typeText[record.type] ?? '-' }}
        </template>
        <template v-else-if="column.key === 'description'">
          <Tooltip :title="record.description ?? ''">
            <span>{{ record.description || '-' }}</span>
          </Tooltip>
        </template>
        <template v-else-if="column.key === 'action'">
          <div class="flex justify-center gap-2">
            <a
              v-if="record.monitor_url"
              @click="openDrawer(record.monitor_url, `监控 - ${record.instance_name ?? ''}`)"
            >
              监控
            </a>
            <span v-else class="cursor-not-allowed opacity-40">监控</span>
            <a
              v-if="record.type === 'host'"
              @click="router.push('/status-patrol/patrol-inspection-record')"
            >
              分析
            </a>
            <a
              v-else-if="record.log_url"
              @click="openDrawer(record.log_url, `日志 - ${record.instance_name ?? ''}`)"
            >
              日志
            </a>
            <span v-else class="cursor-not-allowed opacity-40">日志</span>
            <a
              v-if="record.ip && record.date"
              @click="
                router.push({
                  path: '/application-monitoring/alarm-log',
                  query: { ip: record.ip, time: String(record.date).slice(0, 10) },
                })
              "
            >
              告警
            </a>
          </div>
        </template>
      </template>
    </Table>

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
  </div>
</template>
