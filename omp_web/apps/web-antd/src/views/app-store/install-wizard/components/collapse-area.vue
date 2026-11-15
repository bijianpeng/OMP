<script lang="ts" setup>
/**
 * 折叠内容容器：grid-rows 0fr→1fr 高度过渡（替代旧版固定 height 公式动画，
 * 内容高度自适应），收起时不可交互。
 */
defineOptions({ name: 'InstallCollapseArea' });

defineProps<{
  /** 内容自带底色（安装日志深色面板）时不刷容器灰底，透出周围 bg-card（旧 step3Open 契约无灰带） */
  bare?: boolean;
  open: boolean;
}>();
</script>

<template>
  <div
    class="grid transition-all duration-200 ease-in"
    :class="[
      bare ? '' : 'bg-accent',
      open ? 'mt-2.5 grid-rows-[1fr]' : 'grid-rows-[0fr]',
    ]"
  >
    <div class="overflow-hidden" :class="open ? '' : 'invisible'">
      <slot></slot>
    </div>
  </div>
</template>
