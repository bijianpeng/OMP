<script lang="ts" setup>
import type { UsersApi } from '#/api/users';

import type { EnvApi } from '#/api/env';

import type { FormInstance } from 'ant-design-vue';
import type { Rule } from 'ant-design-vue/es/form';

import { computed, reactive, ref } from 'vue';

import {
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Select,
} from 'ant-design-vue';

import { listEnvs } from '#/api/env';
import { createUser, updateUser } from '#/api/users';

defineOptions({ name: 'UserModal' });

const emit = defineEmits<{ success: [] }>();

/**
 * 密码字符合法性：含白名单外字符返回 true
 * （与修改密码弹窗 isPassword 语义一致）
 */
function hasIllegalChar(value: string) {
  return /[^a-zA-Z0-9`~!?@#$%^&,(){}[\]_+*/.;:]/.test(value);
}

const editingUser = ref<null | UsersApi.UserRecord>(null);
const open = ref(false);
const saving = ref(false);

/**
 * 编辑对象是超管：天然可访问全部环境、不落 UserEnv 行（列表列显示
 * 「全部环境」，授权抽屉同口径排除超管）——隐藏环境字段、提交体剔除
 * envs，否则必选规则拦截保存（record.envs 恒空）或写出冗余授权行。
 */
const editingSuperuser = computed(
  () => editingUser.value?.is_superuser === true,
);

/** 可访问环境选项 */
const envOptions = ref<EnvApi.EnvRecord[]>([]);

const formRef = ref<FormInstance>();
const formState = reactive({
  email: '',
  envs: [] as number[],
  password: '',
  re_password: '',
  username: '',
});

const usernameRules: Rule[] = [{ message: '请输入用户名', required: true }];

const emailRules: Rule[] = [
  { message: '请输入邮箱', required: true },
  { message: '请输入正确格式的邮箱', type: 'email' },
];

const passwordRules: Rule[] = [
  { message: '请输入密码', required: true },
  {
    validator: (_rule: Rule, value: string) =>
      !value || !hasIllegalChar(value)
        ? Promise.resolve()
        : Promise.reject('密码只支持数字、字母以及常用英文符号'),
  },
  {
    validator: (_rule: Rule, value: string) =>
      !value || value.length >= 8
        ? Promise.resolve()
        : Promise.reject('密码长度需大于8位'),
  },
];

const rePasswordRules: Rule[] = [
  { message: '请再次输入密码', required: true },
  {
    validator: (_rule: Rule, value: string) =>
      !value || value === formState.password
        ? Promise.resolve()
        : Promise.reject('两次密码输入不一致'),
  },
];

/** 可访问环境必选规则（超管不落 UserEnv 授权、字段隐藏，规则同步放空） */
const envsRules = computed<Rule[]>(() =>
  editingSuperuser.value
    ? []
    : [{ message: '请选择可访问环境', required: true, type: 'array' as const }],
);

/**
 * 打开弹窗：不传为新建，传入为编辑（用户名只读，不修改密码）。
 * 环境选项直取 listEnvs()（superuser 返回全量）而非 envStore 缓存，
 * 保证新建的环境立即可选。
 */
async function openModal(record?: UsersApi.UserRecord) {
  editingUser.value = record ?? null;
  open.value = true;
  try {
    envOptions.value = await listEnvs();
  } catch {
    // 全局拦截器已提示；选项为空时受必选规则拦截，无法误提交
  }
  if (record) {
    // 编辑：回显该用户现有环境授权（UserEnv 全量）
    Object.assign(formState, {
      email: record.email ?? '',
      envs: record.envs ? [...record.envs] : [],
      password: '',
      re_password: '',
      username: record.username,
    });
  } else {
    // 新建：默认勾选 default 环境（spec 决策 #21）
    const defaultEnv =
      envOptions.value.find((env) => env.code === 'default') ??
      envOptions.value[0];
    Object.assign(formState, {
      email: '',
      envs: defaultEnv ? [defaultEnv.id] : [],
      password: '',
      re_password: '',
      username: '',
    });
  }
  formRef.value?.clearValidate();
}

defineExpose({ open: openModal });

function close() {
  open.value = false;
}

async function handleSubmit() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  saving.value = true;
  try {
    if (editingUser.value === null) {
      await createUser({
        email: formState.email.trim(),
        envs: formState.envs,
        password: formState.password,
        re_password: formState.re_password,
        username: formState.username.trim(),
      });
      message.success('新建用户成功');
    } else {
      // 编辑走 PATCH 局部更新（不改密码），envs 全量覆盖式更新授权；
      // 超管不落 UserEnv 行，提交 envs 会写出冗余授权行——剔除
      await updateUser(
        editingUser.value.id,
        editingSuperuser.value
          ? { email: formState.email.trim() }
          : {
              email: formState.email.trim(),
              envs: formState.envs,
            },
      );
      message.success('修改用户成功');
    }
    close();
    emit('success');
  } catch {
    // 全局拦截器已提示（如用户名已存在）
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal
    :confirm-loading="saving"
    :open="open"
    :title="editingUser === null ? '新建用户' : '编辑用户'"
    :width="560"
    cancel-text="取消"
    destroy-on-close
    ok-text="确定"
    @cancel="close"
    @ok="handleSubmit"
  >
    <Form ref="formRef" :model="formState" layout="vertical">
      <FormItem
        :extra="editingUser !== null ? '用户名不可修改' : undefined"
        :rules="usernameRules"
        label="用户名"
        name="username"
      >
        <Input
          v-model:value="formState.username"
          :disabled="editingUser !== null"
          :maxlength="32"
          placeholder="请输入用户名"
        />
      </FormItem>
      <FormItem :rules="emailRules" label="邮箱" name="email">
        <Input
          v-model:value="formState.email"
          :maxlength="64"
          placeholder="请输入邮箱"
        />
      </FormItem>
      <template v-if="editingUser === null">
        <FormItem :rules="passwordRules" label="密码" name="password">
          <Input.Password
            v-model:value="formState.password"
            placeholder="请设置密码"
          />
        </FormItem>
        <FormItem
          :rules="rePasswordRules"
          label="确认密码"
          name="re_password"
        >
          <Input.Password
            v-model:value="formState.re_password"
            placeholder="请再次输入密码"
          />
        </FormItem>
      </template>
      <FormItem
        v-if="!editingSuperuser"
        :rules="envsRules"
        label="可访问环境"
        name="envs"
      >
        <Select
          v-model:value="formState.envs"
          max-tag-count="responsive"
          mode="multiple"
          :options="
            envOptions.map((env) => ({
              label: `${env.name}（${env.code}）`,
              value: env.id,
            }))
          "
          placeholder="选择该用户可访问的环境"
        />
      </FormItem>
    </Form>
  </Modal>
</template>
