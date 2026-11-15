<script lang="ts" setup>
import { Button, Result } from 'ant-design-vue';

import { useAuthStore } from '#/store';

defineOptions({ name: 'NoEnv' });

const authStore = useAuthStore();
</script>

<template>
  <!-- 无环境提示页（core 路由，无布局/菜单依赖）：登录成功但账号未授权任何环境 -->
  <div class="flex size-full items-center justify-center bg-background-deep">
    <Result status="warning" sub-title="请联系管理员" title="当前账号未授权任何环境">
      <template #extra>
        <Button type="primary" @click="authStore.logout()">重新登录</Button>
      </template>
    </Result>
  </div>
</template>
