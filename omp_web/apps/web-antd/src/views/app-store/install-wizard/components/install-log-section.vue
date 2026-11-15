<script lang="ts" setup>
import type { InstallDetailItem } from '#/api/app-store-install';

import { nextTick, ref } from 'vue';

import CollapseArea from './collapse-area.vue';
import CollapseLink from './collapse-link.vue';
import SectionTitle from './section-title.vue';

/**
 * Step3 单服务安装日志区块：默认收起，展开后展示五阶段拼接日志
 * （黑底白字、高度 240 自滚动），日志为空时展示「正在安装...」。
 */
defineOptions({ name: 'InstallLogSection' });

const props = defineProps<{
  item: InstallDetailItem;
  open: boolean;
}>();

const emit = defineEmits<{ toggle: [] }>();

const logRef = ref<HTMLElement>();

/** 日志更新/展开时滚动到底部（旧版轮询回调里 scrollTop=scrollHeight 契约） */
async function scrollToBottom() {
  if (!props.open) return;
  await nextTick();
  if (logRef.value) {
    logRef.value.scrollTop = logRef.value.scrollHeight;
  }
}

defineExpose({ scrollToBottom });
</script>

<template>
  <section class="mt-5 bg-card p-2.5">
    <SectionTitle :title="item.service_name" />

    <div class="mt-2.5 pb-10 pl-5">
      <div class="flex items-center justify-between">
        <div class="flex w-[320px] items-center">{{ item.ip }}</div>
        <CollapseLink
          :open="open"
          text="查看详细安装信息"
          @toggle="emit('toggle')"
        />
      </div>

      <CollapseArea bare :open="open">
        <div
          ref="logRef"
          class="mt-2.5 h-60 overflow-x-hidden overflow-y-auto whitespace-pre-line break-all break-words bg-[#222] p-2.5 text-white"
        >
          {{ item.log || '正在安装...' }}
        </div>
      </CollapseArea>
    </div>
  </section>
</template>
