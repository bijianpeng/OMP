<script lang="ts" setup>
import type { DependenceItem } from '#/api/installation';

import RenderArr from './render-arr.vue';
import RenderNum from './render-num.vue';

/** 依赖新装行：模式选项数组走 RenderArr，数量型走 RenderNum。 */
defineOptions({ name: 'InstallationDeployNumRow' });

defineProps<{
  data: DependenceItem;
}>();
</script>

<template>
  <div class="flex-1 pl-5">{{ data.name }}</div>
  <div class="flex-1">{{ data.version }}</div>
  <RenderArr
    v-if="Array.isArray(data.deploy_mode)"
    :data="data"
  />
  <RenderNum v-else :data="data" />
  <div class="flex-2"></div>
</template>
