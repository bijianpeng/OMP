<script lang="ts" setup>
/**
 * 区块标题：悬浮文字 + 贯穿分隔线（旧安装页区块头部契约）。
 * 文字背景与卡片同色以遮线，父容器需为白色卡片背景。
 * 与批 K install-wizard 同构组件的本地副本（跨批次目录不互相依赖）。
 */
defineOptions({ name: 'InstallationSectionTitle' });

defineProps<{ title: string }>();
</script>

<template>
  <div class="relative flex h-[30px] w-full items-center">
    <div class="absolute left-[30px] bg-card px-5 font-medium">{{ title }}</div>
    <div class="h-px w-full bg-border"></div>
  </div>
</template>
