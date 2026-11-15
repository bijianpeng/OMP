<script lang="ts">
import type { HomepageApi } from '#/api/homepage';

/**
 * 状态块：按实例聚合的状态按钮墙（旧前端 OmpStateBlock 等价物）。
 *
 * - 异常/正常/未监控三勾选过滤 + 展开收起
 * - 按钮按 异常→正常→未监控→警告 排序，颜色语义与旧版一致
 * - 点击异常项发 critical-click，其余发 item-click（由父级转 query 跳转）
 */

/** 聚合后的单条状态项 */
export interface AggregatedStateItem {
  /** 聚合主键（instance_name 或 ip） */
  key: string;
  /** 聚合组内条目（Popover 明细） */
  info: HomepageApi.InstrumentItem[];
  /** 组内首条的原始 severity */
  severity: null | string;
}
</script>

<script lang="ts" setup>
import { computed, ref } from 'vue';

import { Button, Checkbox, Popover } from 'ant-design-vue';

interface Props {
  items: AggregatedStateItem[];
  title: string;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  criticalClick: [item: AggregatedStateItem];
  itemClick: [item: AggregatedStateItem];
}>();

type FrontendStatus = 'abnormal' | 'noMonitored' | 'normal' | 'warning';

/** 后端 severity → 前端状态（critical/warning 均为异常语境，但旧版仅 critical 计异常红） */
function toFrontendStatus(severity: null | string): FrontendStatus {
  switch (severity) {
    case 'critical': {
      return 'abnormal';
    }
    case 'normal': {
      return 'normal';
    }
    case 'warning': {
      return 'warning';
    }
    default: {
      return 'noMonitored';
    }
  }
}

// 底色用状态色低透明度：亮色下呈浅彩底、暗色下呈暗彩底，双主题通用
// （写死浅色底在暗色下会成残留亮块）；文字用状态描边色，两主题均可读
const statusStyle: Record<FrontendStatus, { background: string; borderColor: string }> = {
  abnormal: { background: 'rgba(218, 78, 72, 0.15)', borderColor: '#da4e48' },
  noMonitored: { background: 'rgba(128, 128, 128, 0.18)', borderColor: '#aaaaaa' },
  normal: { background: 'rgba(84, 187, 166, 0.15)', borderColor: '#54bba6' },
  warning: { background: 'rgba(245, 199, 115, 0.15)', borderColor: 'rgb(245, 199, 115)' },
};

const sortedItems = computed(() => {
  const order: FrontendStatus[] = ['abnormal', 'normal', 'noMonitored', 'warning'];
  return [...props.items].sort(
    (a, b) =>
      order.indexOf(toFrontendStatus(a.severity)) -
      order.indexOf(toFrontendStatus(b.severity)),
  );
});

const filterStatus = ref<Record<'abnormal' | 'noMonitored' | 'normal', boolean>>({
  abnormal: true,
  noMonitored: true,
  normal: true,
});

/** 展示项 = 排序后列表按三个状态勾选过滤（警告态恒显示） */
const visibleItems = computed(() =>
  sortedItems.value.filter((item) => {
    const status = toFrontendStatus(item.severity);
    return status === 'warning'
      ? true
      : filterStatus.value[status as 'abnormal' | 'noMonitored' | 'normal'];
  }),
);

const isShowAll = ref(false);

function statusOf(item: AggregatedStateItem): FrontendStatus {
  return toFrontendStatus(item.severity);
}

function handleClick(item: AggregatedStateItem) {
  if (toFrontendStatus(item.severity) === 'abnormal') {
    emit('criticalClick', item);
  } else {
    emit('itemClick', item);
  }
}

function truncate(text: string, max = 100) {
  return text.length > max ? `${text.slice(0, max)}...` : text;
}
</script>

<template>
  <div>
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <span class="text-base font-medium">{{ title }}</span>
      <div class="flex items-center gap-1">
        <Checkbox v-model:checked="filterStatus.abnormal">异常</Checkbox>
        <Checkbox v-model:checked="filterStatus.normal">正常</Checkbox>
        <Checkbox v-model:checked="filterStatus.noMonitored">未监控</Checkbox>
        <Button class="ml-2" size="small" @click="isShowAll = !isShowAll">
          {{ isShowAll ? '收起' : '展开' }}
        </Button>
      </div>
    </div>

    <div
      v-if="visibleItems.length > 0"
      :class="{ 'overflow-y-auto': !isShowAll }"
      :style="isShowAll ? {} : { maxHeight: '170px' }"
      class="flex flex-wrap gap-2"
    >
      <Popover v-for="(item, index) in visibleItems" :key="`${title}-${index}`">
        <template #content>
          <div class="max-w-xs">
            <div
              v-for="(info, idx) in item.info"
              :key="idx"
              class="mb-1 flex flex-wrap items-center gap-2 text-xs"
            >
              <span
                v-if="info.ip"
                :style="{ color: statusStyle[toFrontendStatus(item.severity)].borderColor }"
              >
                {{ info.ip }}
              </span>
              <span v-if="info.date">{{ info.date }}</span>
              <span
                v-else
                :style="{ color: statusStyle[toFrontendStatus(item.severity)].borderColor }"
              >
                {{ toFrontendStatus(item.severity) === 'noMonitored' ? '未监控' : '正常' }}
              </span>
              <span v-if="info.describe">{{ truncate(info.describe) }}</span>
            </div>
          </div>
        </template>
        <template #title>
          <span class="text-sm">相关信息</span>
        </template>
        <Button
          :style="{
            background: statusStyle[statusOf(item)].background,
            borderColor: statusStyle[statusOf(item)].borderColor,
            // 文字用状态描边色：半透明底上彩字在明暗主题下均可读
            color: statusStyle[statusOf(item)].borderColor,
          }"
          class="max-w-[180px]"
          size="small"
          @click="handleClick(item)"
        >
          <span class="truncate">{{ item.key || '-' }}</span>
        </Button>
      </Popover>
    </div>
    <div v-else class="text-muted-foreground py-6 text-center text-sm">
      暂无数据
    </div>
  </div>
</template>
