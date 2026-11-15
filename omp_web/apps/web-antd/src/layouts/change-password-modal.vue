<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue';

import { reactive, ref } from 'vue';

import { Form, FormItem, Input, message, Modal } from 'ant-design-vue';

import { updateUserPassword } from '#/api/users';
import { useAuthStore } from '#/store';
import { rsaEncrypt } from '#/utils/rsa';

defineOptions({ name: 'ChangePasswordModal' });

/**
 * 修改密码弹窗（头像下拉入口）。
 *
 * 契约：old_password / new_password / username 三个字段均需先用
 * utils/rsa 的 rsaEncrypt 做 RSA 公钥加密，再调 api/users.ts 的
 * updateUserPassword（POST /api/users/updatePassword/，后端按 344 位
 * 密文长度校验后解密比对）。username 从 localStorage 的登录用户名读取
 * （key 与 store/auth.ts 的 USERNAME_KEY 同规则构造，登录成功时写入）。
 * 成功后强制登出回登录页（用新密码重新登录）；失败由全局拦截器统一提示，
 * 弹窗保持打开。
 */

// 与 store/auth.ts 的 USERNAME_KEY 保持一致（auth.ts 未导出该常量）
const USERNAME_KEY = `${import.meta.env.VITE_APP_NAMESPACE}-omp-username`;

const authStore = useAuthStore();
const open = ref(false);
const saving = ref(false);
const formRef = ref<FormInstance>();

const formState = reactive({
  confirm_password: '',
  new_password: '',
  old_password: '',
});

/** 新密码：必填 + 至少 8 位 + 同时含字母与数字（按后端惯例宽松校验） */
const newPasswordRules = [
  { message: '请输入新密码', required: true },
  { message: '新密码至少 8 位', min: 8, trigger: 'blur' as const },
  {
    trigger: 'blur' as const,
    validator: (_rule: unknown, value: string) =>
      !value || (/[a-zA-Z]/.test(value) && /\d/.test(value))
        ? Promise.resolve()
        : Promise.reject('新密码需同时包含字母和数字'),
  },
];

const confirmPasswordRules = [
  { message: '请再次输入新密码', required: true },
  {
    trigger: 'blur' as const,
    validator: (_rule: unknown, value: string) =>
      !value || value === formState.new_password
        ? Promise.resolve()
        : Promise.reject('两次输入的新密码不一致'),
  },
];

const oldPasswordRules = [{ message: '请输入旧密码', required: true }];

function openModal() {
  Object.assign(formState, {
    confirm_password: '',
    new_password: '',
    old_password: '',
  });
  open.value = true;
}

defineExpose({ open: openModal });

async function handleSubmit() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  const username = localStorage.getItem(USERNAME_KEY) ?? '';
  saving.value = true;
  try {
    await updateUserPassword({
      new_password: rsaEncrypt(formState.new_password),
      old_password: rsaEncrypt(formState.old_password),
      username: rsaEncrypt(username),
    });
    message.success('密码修改成功，请使用新密码重新登录');
    open.value = false;
    await authStore.logout(false);
  } catch {
    // 全局拦截器已提示（如旧密码不正确），弹窗保持打开
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal
    :confirm-loading="saving"
    :open="open"
    title="修改密码"
    :width="420"
    cancel-text="取消"
    destroy-on-close
    ok-text="确定"
    @cancel="open = false"
    @ok="handleSubmit"
  >
    <Form ref="formRef" :model="formState" layout="vertical">
      <FormItem label="旧密码" :rules="oldPasswordRules" name="old_password">
        <Input.Password
          v-model:value="formState.old_password"
          placeholder="请输入旧密码"
        />
      </FormItem>
      <FormItem label="新密码" :rules="newPasswordRules" name="new_password">
        <Input.Password
          v-model:value="formState.new_password"
          placeholder="至少 8 位，需同时包含字母和数字"
        />
      </FormItem>
      <FormItem
        label="确认新密码"
        :rules="confirmPasswordRules"
        name="confirm_password"
      >
        <Input.Password
          v-model:value="formState.confirm_password"
          placeholder="请再次输入新密码"
        />
      </FormItem>
    </Form>
  </Modal>
</template>
