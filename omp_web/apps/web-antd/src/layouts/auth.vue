<script lang="ts" setup>
import { computed } from 'vue';

import { AuthPageLayout } from '@vben/layouts';
import { preferences } from '@vben/preferences';

const appName = computed(() => preferences.app.name);
const logo = computed(() => preferences.logo.source);
const logoDark = computed(() => preferences.logo.sourceDark);
</script>

<template>
  <!-- 品牌文案中文化并关闭版权栏（去掉 vben 默认 ICP 备案/公司链接页脚） -->
  <!-- 登录页应用名称只保留顶栏 logo 旁一处：不传 page-title/page-description，
       左侧介绍面板不再重复显示应用名与产品描述语 -->
  <AuthPageLayout
    :app-name="appName"
    :copyright="false"
    :logo="logo"
    :logo-dark="logoDark"
  >
    <!-- 自定义工具栏 -->
    <!-- <template #toolbar></template> -->
  </AuthPageLayout>
</template>
