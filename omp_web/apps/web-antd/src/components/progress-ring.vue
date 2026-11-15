<script lang="ts">
/**
 * 环形状态进度图（仪表盘「状态概览」用，监控类页面可复用）。
 *
 * 用法：
 *   <ProgressRing :percent="80" :segments="[{ name: '异常', value: 2, color: '#ee686e' }, ...]" />
 *
 * - percent：中心百分比文案（0~100；NaN 情况由调用方归一，组件内 100% 显示为绿色）
 * - segments：环形分段（按数组顺序绘制）；全部为 0 时以第 1 段填 1 占位，
 *   避免空环（与旧前端 OmpProgress 行为一致）
 * - 已知约束：echarts 实例在 onMounted 后激活，watch(option, immediate) 的首次
 *   渲染会被吞掉——传**静态** segments 的父组件图表不渲染；segments 异步获取
 *   （fetch 后赋值）则正常。静态场景请在 mounted 后再赋值或二次触发
 */

/** 环形分段 */
export interface RingSegment {
  color: string;
  name: string;
  value: number;
}
</script>

<script lang="ts" setup>
import type { ECOption } from '@vben/plugins/echarts';

import type { ComponentPublicInstance } from 'vue';

import { computed, ref, watch } from 'vue';

import { EchartsUI, useEcharts } from '@vben/plugins/echarts';

interface Props {
  height?: string;
  percent: number;
  segments: RingSegment[];
  width?: string;
}

const props = withDefaults(defineProps<Props>(), {
  height: '100px',
  width: '100px',
});

const chartRef = ref<ComponentPublicInstance>();

const { renderEcharts } = useEcharts(chartRef);

/** 中心显示的百分比：NaN/Infinity 统一按 0 显示，100 显示绿色 */
const displayPercent = computed(() => {
  if (!Number.isFinite(props.percent)) {
    return 0;
  }
  return Math.round(props.percent);
});

const option = computed((): ECOption => {
  const allZero = props.segments.every((item) => !item.value);
  // 全 0 时以最后一段填 1 占位画出满环（约定 segments 末段为「正常」，
  // 与旧前端 OmpProgress 以正常段占位的语义一致）
  const placeholder = props.segments[props.segments.length - 1];
  // 0 值段会被 echarts 渲染成一条径向细线（环顶部正中的「小竖线」），
  // 过滤之，仅保留非 0 段与全 0 时的占位段
  const data = props.segments
    .filter((item) => item.value > 0 || (allZero && item === placeholder))
    .map((item) => ({
      itemStyle: { color: item.color },
      name: item.name,
      value: allZero && item === placeholder ? 1 : item.value,
    }));
  return {
    series: [
      {
        avoidLabelOverlap: false,
        center: ['50%', '50%'],
        data,
        label: { show: false },
        labelLine: { show: false },
        radius: ['72%', '88%'],
        type: 'pie',
      },
    ],
    title: { show: false },
    tooltip: { show: false },
  };
});

watch(
  option,
  (value) => {
    void renderEcharts(value);
  },
  { immediate: true },
);
</script>

<template>
  <!-- 中心百分比用 DOM 渲染（text-foreground 随主题；echarts title 的固定色无法感知暗色） -->
  <div class="relative" :style="{ height, width }">
    <EchartsUI ref="chartRef" :height="height" :width="width" />
    <span
      class="pointer-events-none absolute inset-0 flex items-center justify-center text-[18px] font-normal"
      :class="displayPercent === 100 ? 'text-[rgb(84,187,166)]' : 'text-foreground'"
    >
      {{ displayPercent }}%
    </span>
  </div>
</template>
