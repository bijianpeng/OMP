<script lang="ts" setup>
import type { DependenceItem } from '#/api/installation';

import DeployInstanceRow from './deploy-instance-row.vue';
import DeployNumRow from './deploy-num-row.vue';
import JdkRow from './jdk-row.vue';

/**
 * Step1 依赖信息行分发：基础环境（jdk）走 JdkRow 只读展示，
 * 其余按「复用依赖」/部署模式类型走实例选择或数量/模式配置行。
 */
defineOptions({ name: 'InstallationDependentInfoItem' });

defineProps<{
  data: DependenceItem;
  /** 旧页空产品分支传入：dependence[0] 以基本信息样式展示 */
  isBaseEnv?: boolean;
}>();
</script>

<template>
  <div class="mt-8 flex items-center">
    <JdkRow v-if="data.is_base_env" :data="data" :is-base-env="isBaseEnv" />
    <DeployInstanceRow
      v-else-if="data.is_use_exist"
      :data="data"
    />
    <DeployNumRow v-else :data="data" />
  </div>
  <div
    class="text-[red]"
    :class="data.error_msg ? 'h-5' : 'h-0'"
    style="transition: all 0.2s ease-in"
  >
    {{ data.error_msg }}
  </div>
</template>
