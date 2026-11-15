<script lang="ts" setup>
import type { DependenceItem } from '#/api/installation';

import { Checkbox } from 'ant-design-vue';

/** 基础环境依赖行（jdk）：只读展示，无配置项。 */
defineOptions({ name: 'InstallationJdkRow' });

defineProps<{
  data: DependenceItem;
  /** 旧页空产品分支传入时隐藏「安装依赖」标记 */
  isBaseEnv?: boolean;
}>();
</script>

<template>
  <div class="flex-1 pl-5">{{ data.name }}</div>
  <div class="flex-1">{{ data.version }}</div>
  <div class="flex-3"></div>
  <div class="flex-5"></div>
  <div class="flex-2">
    <div class="flex items-center justify-end pr-[70px] text-[13px]">
      <Checkbox v-if="!isBaseEnv" checked disabled>安装依赖</Checkbox>
    </div>
  </div>
</template>
