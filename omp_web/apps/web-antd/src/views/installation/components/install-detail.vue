<script lang="ts" setup>
import { nextTick, useTemplateRef, watch } from 'vue';

import CollapseArea from './collapse-area.vue';
import CollapseLink from './collapse-link.vue';

/**
 * Step4 单主机安装明细行：ip + 状态 + 可展开的安装日志面板
 * （黑底白字 300px 自滚动，日志更新时滚到底部）。
 */
defineOptions({ name: 'InstallationInstallDetail' });

const props = defineProps<{
  ip: string;
  /** 当前项日志（仅展开时父级下发） */
  log: string;
  open: boolean;
  status: number;
}>();

const emit = defineEmits<{ toggle: [] }>();

/** 状态渲染规则（0 等待 1 进行中 2 成功 3 失败，与后端枚举一致） */
const STATUS_TEXT: Record<number, { color: string; text: string }> = {
  0: { color: '#f0c242', text: '等待安装' },
  1: { color: 'rgba(0, 0, 0, 0.85)', text: '正在安装' },
  2: { color: 'rgb(118, 204, 104)', text: '安装成功' },
  3: { color: '#da4e48', text: '安装失败' },
};

const logRef = useTemplateRef<HTMLElement>('logRef');

/** 日志更新/展开时滚动到底部（旧 scrollTop=scrollHeight 契约） */
watch(
  () => props.log,
  async () => {
    if (!props.open) return;
    await nextTick();
    if (logRef.value) {
      logRef.value.scrollTop = logRef.value.scrollHeight;
    }
  },
);
</script>

<template>
  <div class="p-2.5">
    <div class="flex justify-between">
      <div class="min-w-0 flex-1">{{ ip }}</div>
      <div
        class="w-[90px] shrink-0 whitespace-nowrap"
        :style="{ color: STATUS_TEXT[status]?.color }"
      >
        {{ STATUS_TEXT[status]?.text ?? status }}
      </div>
      <div class="shrink-0 pr-[50px] text-right">
        <CollapseLink
          :open="open"
          text="查看详细安装信息"
          @toggle="emit('toggle')"
        />
      </div>
    </div>
    <CollapseArea bare :open="open">
      <div
        ref="logRef"
        class="mt-2.5 max-h-[300px] min-h-[30px] overflow-y-auto whitespace-pre-line bg-black p-2.5 text-white"
      >
        {{ log || '暂无数据' }}
      </div>
    </CollapseArea>
  </div>
</template>
