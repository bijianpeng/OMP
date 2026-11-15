<script lang="ts" setup>
import type { VbenFormSchema } from '@vben/common-ui';

import { computed } from 'vue';

import { AuthenticationLogin, z } from '@vben/common-ui';
import { $t } from '@vben/locales';

import { useAuthStore } from '#/store';

defineOptions({ name: 'Login' });

const authStore = useAuthStore();

const formSchema = computed((): VbenFormSchema[] => {
  return [
    {
      component: 'VbenInput',
      componentProps: {
        placeholder: $t('authentication.usernameTip'),
      },
      fieldName: 'username',
      label: $t('authentication.username'),
      rules: z.string().min(1, { message: $t('authentication.usernameTip') }),
    },
    {
      component: 'VbenInputPassword',
      componentProps: {
        placeholder: $t('authentication.password'),
      },
      fieldName: 'password',
      label: $t('authentication.password'),
      rules: z.string().min(1, { message: $t('authentication.passwordTip') }),
    },
  ];
});
</script>

<template>
  <!-- OMP 仅账号密码登录：关闭 vben 默认的手机号/扫码/注册/找回密码/第三方登录入口 -->
  <!-- 登录页应用名称仅保留顶栏 logo 旁一处：表单大标题走 props title（保留
       AuthTitle 的 h2 样式容器——传 #title slot 会替换外层插槽、丢掉样式）；
       副标题（应用名）用正确驼峰名的 #subTitle 隐藏 span 压制兜底 i18n 文案
       （props 传空字符串为 falsy，同样触发兜底） -->
  <AuthenticationLogin
    :form-schema="formSchema"
    :loading="authStore.loginLoading"
    :show-code-login="false"
    :show-forget-password="false"
    :show-qrcode-login="false"
    :show-register="false"
    :show-third-party-login="false"
    title="欢迎登录"
    @submit="authStore.authLogin"
  >
    <template #subTitle><span hidden></span></template>
  </AuthenticationLogin>
</template>
