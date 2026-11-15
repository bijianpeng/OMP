<script lang="ts" setup>
/**
 * 区块标题：悬浮文字 + 贯穿分隔线（旧安装页区块头部契约）。
 * 文字背景与卡片同色以遮线，父容器需为白色卡片背景。
 */
defineOptions({ name: 'InstallSectionTitle' });

defineProps<{ title: string }>();
</script>

<template>
  <div class="relative flex h-[30px] w-full items-center">
    <div class="absolute left-[30px] bg-card px-5 font-medium">{{ title }}</div>
    <div class="h-px w-full bg-border"></div>
  </div>
</template>
