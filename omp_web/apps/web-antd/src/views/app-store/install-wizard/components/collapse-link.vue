<script lang="ts" setup>
import { IconifyIcon } from '@vben/icons';

/**
 * 「查看更多配置 / 查看详细安装信息」展开触发链接，
 * 箭头随展开状态旋转（旧实现箭头误读另一键名恒不转，此处修正）。
 */
defineOptions({ name: 'InstallCollapseLink' });

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
