<script lang="ts" setup>
import { IconifyIcon } from '@vben/icons';

/**
 * 「更改服务信息 / 查看详细安装信息」展开触发链接，
 * 箭头随展开状态旋转。
 * 与批 K install-wizard 同构组件的本地副本（跨批次目录不互相依赖）。
 */
defineOptions({ name: 'InstallationCollapseLink' });

defineProps<{ open: boolean; text: string }>();

const emit = defineEmits<{ toggle: [] }>();
</script>

<template>
  <a
    class="flex cursor-pointer select-none items-center pr-2 text-[13px]"
    @click="emit('toggle')"
  >
    {{ text }}
    <IconifyIcon
      icon="lucide:chevron-down"
      class="relative ml-1 transition-transform"
      :class="open ? '-translate-y-px rotate-180' : 'translate-y-px'"
    />
  </a>
</template>
