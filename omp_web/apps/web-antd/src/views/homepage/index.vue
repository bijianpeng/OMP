<script lang="ts" setup>
import type { HomepageApi } from '#/api/homepage';

import type { RingSegment } from '#/components/progress-ring.vue';

import type { AggregatedStateItem } from './state-block.vue';

import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';

import { Card, Spin } from 'ant-design-vue';

import { getInstrumentPanel } from '#/api/homepage';
import ProgressRing from '#/components/progress-ring.vue';

import ExceptionPanel from './exception-panel.vue';
import StateBlock from './state-block.vue';

defineOptions({ name: 'Homepage' });

const router = useRouter();

const loading = ref(false);
const dataSource = ref<HomepageApi.InstrumentPanel>({});

onMounted(async () => {
  loading.value = true;
  try {
    dataSource.value = await getInstrumentPanel();
  } finally {
    loading.value = false;
  }
});

/** 环形分段语义色（沿用旧前端配色） */
const SEG_EXC = '#ee686e';
const SEG_NO_MONITOR = '#ffbe40';
const SEG_NORMAL = '#54bba6';

/**
 * 正常占比：normal = all - exc - noMonitor；总数为 0 时按 100% 显示
 * （与旧前端 calcPercentage 语义一致）
 */
function calcPercent(all = 0, exc = 0, noMonitor = 0) {
  if (!all) {
    return 100;
  }
  return ((all - exc - noMonitor) / all) * 100;
}

interface OverviewLink {
  label: string;
  path: string;
  query?: Record<string, string>;
}

interface OverviewBlock {
  excCount: number;
  excLabel: string;
  excLink?: OverviewLink;
  noMonitorCount: number;
  percent: number;
  segments: RingSegment[];
  title: string;
  totalCount: number;
  totalLabel: string;
  totalLink?: OverviewLink;
}

/**
 * 状态概览四卡：应用服务 / 基础组件 / 数据库 / 主机。
 * 跳转全部转 query（旧前端 location.state 语义），目标页均已实现消费：
 * - 服务/组件 → 服务管理 ?app_type=0|1；数据库 → 服务管理 ?label_name=数据库
 * - 异常数 → 异常清单 ?type=service|component|database|host
 * - 主机总数 → 主机管理
 */
const overviewBlocks = computed<OverviewBlock[]>(() => {
  const d = dataSource.value;
  const build = (
    section: HomepageApi.InstrumentSection | undefined,
    prefix: string,
    title: string,
    totalLabel: string,
    excLabel: string,
    totalLink?: Omit<OverviewLink, 'label'>,
    excQuery?: Record<string, string>,
  ): OverviewBlock => {
    const all = Number(section?.[`${prefix}_all_count`] ?? 0);
    const exc = Number(section?.[`${prefix}_exc_count`] ?? 0);
    const noMonitor = Number(section?.[`${prefix}_no_monitor_count`] ?? 0);
    const normal = all - exc - noMonitor;
    return {
      excCount: exc,
      excLabel,
      // 有异常数才可点击跳异常清单（旧前端同款语义）
      excLink:
        exc > 0 && excQuery
          ? { label: excLabel, path: '/application-monitoring/exception-list', query: excQuery }
          : undefined,
      noMonitorCount: noMonitor,
      percent: calcPercent(all, exc, noMonitor),
      segments: [
        { color: SEG_EXC, name: '异常', value: exc },
        { color: SEG_NO_MONITOR, name: '未监控', value: noMonitor },
        { color: SEG_NORMAL, name: '正常', value: normal },
      ],
      title,
      totalCount: all,
      totalLabel,
      // 总数为 0 时不可点击（旧前端同款语义）
      totalLink: all > 0 && totalLink ? { ...totalLink, label: totalLabel } : undefined,
    };
  };

  return [
    build(
      d.service,
      'service_info',
      '应用服务状态',
      '服务总数',
      '异常服务',
      { path: '/application_management/service_management', query: { app_type: '1' } },
      { type: 'service' },
    ),
    build(
      d.component,
      'component_info',
      '基础组件状态',
      '组件实例',
      '异常组件',
      { path: '/application_management/service_management', query: { app_type: '0' } },
      { type: 'component' },
    ),
    build(
      d.database,
      'database_info',
      '数据库状态',
      '数据库实例',
      '异常实例',
      { path: '/application_management/service_management', query: { label_name: '数据库' } },
      { type: 'database' },
    ),
    build(
      d.host,
      'host_info',
      '主机状态',
      '主机总数',
      '异常主机',
      { path: '/resource-management/machine-management' },
      { type: 'host' },
    ),
  ];
});

/**
 * 状态块聚合（旧前端 dataAggregation 等价）：按 keyField 分组，
 * severity 取组内首条，info 收集全部明细供 Popover 展示
 */
function aggregate(
  list: HomepageApi.InstrumentItem[] | undefined,
  keyField: 'instance_name' | 'ip',
): AggregatedStateItem[] {
  const groups = new Map<string, AggregatedStateItem>();
  for (const item of list ?? []) {
    const key = String(item[keyField] ?? '');
    const existing = groups.get(key);
    if (existing) {
      existing.info.push(item);
    } else {
      groups.set(key, { info: [item], key, severity: item.severity ?? null });
    }
  }
  return [...groups.values()];
}

function go(path: string, query?: Record<string, string>) {
  router.push(query ? { path, query } : path);
}
</script>

<template>
  <Page content-class="min-h-0 overflow-y-auto pb-2">
    <Spin :spinning="loading">
      <div class="flex flex-col gap-4">
        <!-- 状态概览 -->
        <Card title="状态概览">
          <div class="flex flex-wrap justify-around gap-4">
            <div
              v-for="block in overviewBlocks"
              :key="block.title"
              class="flex min-w-[200px] items-center gap-3"
            >
              <ProgressRing :percent="block.percent" :segments="block.segments" />
              <div class="flex flex-col gap-1 text-sm">
                <div>{{ block.title }}</div>
                <div>
                  <template v-if="block.totalLink">
                    <span>{{ block.totalLabel }}：</span>
                    <a class="text-primary" @click="go(block.totalLink.path, block.totalLink.query)">{{ block.totalCount }}个</a>
                  </template>
                  <template v-else>
                    {{ block.totalLabel }}：{{ block.totalCount }}个
                  </template>
                </div>
                <div>
                  <template v-if="block.excLink">
                    <span>{{ block.excLabel }}：</span>
                    <a class="text-red-500" @click="go(block.excLink.path, block.excLink.query)">{{ block.excCount }}个</a>
                  </template>
                  <template v-else>
                    {{ block.excLabel }}：{{ block.excCount }}个
                  </template>
                </div>
              </div>
            </div>
          </div>
        </Card>

        <!-- 异常清单 -->
        <Card title="异常清单">
          <ExceptionPanel />
        </Card>

        <!-- 应用服务状态块 -->
        <Card>
          <StateBlock
            :items="aggregate(dataSource.service?.service_info_list, 'instance_name')"
            title="应用服务状态"
            @critical-click="
              (item) =>
                go('/application-monitoring/exception-list', {
                  ip: item.info[0]?.ip ?? '',
                  type: 'service',
                })
            "
            @item-click="
              (item) =>
                go('/application_management/service_management', {
                  app_type: '1',
                  ip: item.info[0]?.ip ?? '',
                })
            "
          />
        </Card>

        <!-- 基础组件状态块 -->
        <Card>
          <StateBlock
            :items="aggregate(dataSource.component?.component_info_list, 'instance_name')"
            title="基础组件状态"
            @critical-click="
              (item) =>
                go('/application-monitoring/exception-list', {
                  instance_name: item.info[0]?.instance_name ?? '',
                  type: 'component',
                })
            "
            @item-click="
              (item) =>
                go('/application_management/service_management', {
                  app_type: '0',
                  ip: item.info[0]?.ip ?? '',
                })
            "
          />
        </Card>

        <!-- 数据库状态块 -->
        <Card>
          <StateBlock
            :items="aggregate(dataSource.database?.database_info_list, 'instance_name')"
            title="数据库状态"
            @critical-click="
              (item) =>
                go('/application-monitoring/exception-list', {
                  instance_name: item.info[0]?.instance_name ?? '',
                  type: 'database',
                })
            "
            @item-click="
              (item) =>
                go('/application_management/service_management', {
                  ip: item.info[0]?.ip ?? '',
                  label_name: '数据库',
                })
            "
          />
        </Card>

        <!-- 主机运行状态块 -->
        <Card>
          <StateBlock
            :items="aggregate(dataSource.host?.host_info_list, 'ip')"
            title="主机运行状态"
            @critical-click="
              (item) =>
                go('/application-monitoring/exception-list', {
                  ip: item.info[0]?.ip ?? '',
                  type: 'host',
                })
            "
            @item-click="
              (item) =>
                go('/resource-management/machine-management', {
                  ip: item.info[0]?.ip ?? '',
                })
            "
          />
        </Card>
      </div>
    </Spin>
  </Page>
</template>
