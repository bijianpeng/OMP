<script lang="ts" setup>
import type { UsersApi } from '#/api/users';

import type { FormInstance } from 'ant-design-vue';
import type { Rule } from 'ant-design-vue/es/form';

import { h, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { useUserStore } from '@vben/stores';

import { Button, Form, FormItem, Input, message, Modal } from 'ant-design-vue';
import dayjs from 'dayjs';

import { useAuthStore } from '#/store';
import { updateUserPassword, queryUsers } from '#/api/users';
import { rsaEncrypt } from '#/utils/rsa';
import { useVbenVxeGrid } from '#/adapter/vxe-table';

import UserModal from './user-modal.vue';

defineOptions({ name: 'UserManagement' });

const userStore = useUserStore();
const authStore = useAuthStore();

/** 角色文案（与旧前端一致：超管/内置只读账号 omp/普通用户） */
function formatRole(row: UsersApi.UserRecord) {
  if (row.is_superuser) return '普通管理员';
  return row.username === 'omp' ? '只读用户' : '普通用户';
}

/** 格式化时间 */
const formatTime = (value?: null | string) =>
  value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';

/** 可访问环境文案（superuser 天然全环境、不落 UserEnv 行） */
function formatEnvs(row: UsersApi.UserRecord) {
  if (row.is_superuser) return '全部环境';
  return row.env_names?.length ? row.env_names.join('、') : '-';
}

/** 当前操作的行（修改密码弹窗目标） */
const currentRow = ref<null | UsersApi.UserRecord>(null);

const userModalRef = ref<InstanceType<typeof UserModal>>();

const [Grid, gridApi] = useVbenVxeGrid({
  // flex 传导层：Grid 根 div 转 flex 列，表体内部滚动、分页钉视口底
  class: 'flex flex-col',
  gridClass: 'min-h-0 flex-1',
  formOptions: {
    collapsed: false,
    schema: [
      {
        component: 'Input',
        componentProps: {
          allowClear: true,
          placeholder: '请输入用户名',
        },
        fieldName: 'username',
        label: '用户名',
      },
    ],
    submitOnChange: true,
  },
  gridOptions: {
    columns: [
      { type: 'seq', title: '序列', width: 70 },
      { title: '用户名', field: 'username', width: 150 },
      {
        title: '角色',
        field: 'is_superuser',
        width: 140,
        slots: { default: ({ row }) => formatRole(row) },
      },
      {
        title: '用户状态',
        field: 'is_active',
        width: 120,
        formatter: ({ row }) => (row.is_active ? '正常' : '停用'),
      },
      {
        title: '创建时间',
        field: 'date_joined',
        minWidth: 180,
        formatter: ({ row }) => formatTime(row.date_joined),
      },
      {
        title: '可访问环境',
        field: 'env_names',
        minWidth: 160,
        showOverflow: true,
        slots: {
          default: ({ row }) => formatEnvs(row),
        },
      },
      {
        title: '用户操作',
        field: 'action',
        width: 160,
        fixed: 'right',
        slots: {
          default: ({ row }) =>
            h('div', { class: 'space-x-2.5' }, [
              h(
                'a',
                { onClick: () => userModalRef.value?.open(row) },
                '编辑',
              ),
              h('a', { onClick: () => openPasswordModal(row) }, '修改密码'),
            ]),
        },
      },
    ],
    height: 'auto',
    // 旧页未启用列排序，后端 ordering 保持空
    pagerConfig: { enabled: true, pageSizes: [10, 20, 50, 100] },
    proxyConfig: {
      autoLoad: true,
      response: { result: 'results', total: 'count' },
      ajax: {
        query: async ({ page }, formValues) => {
          return await queryUsers({
            page: page.currentPage,
            size: page.pageSize,
            username: formValues.username || null,
          });
        },
      },
    },
    rowConfig: { keyField: 'id', isCurrent: true },
    toolbarConfig: { refresh: true, zoom: true, column: true },
  },
});

/** 刷新用户列表（新建/编辑用户成功后回调） */
function refresh() {
  gridApi.query();
}

// ── 修改密码弹窗 ──────────────────────────────────────────────

const passwordOpen = ref(false);
const passwordSaving = ref(false);
const passwordFormRef = ref<FormInstance>();
const passwordFormState = reactive({
  new_password1: '',
  new_password2: '',
  old_password: '',
});

/**
 * 密码字符合法性：含白名单外字符返回 true（与旧前端 utils/verify isPassword 一致）
 */
function hasIllegalChar(value: string) {
  return /[^a-zA-Z0-9`~!?@#$%^&,(){}[\]_+*/.;:]/.test(value);
}

const oldPasswordRules: Rule[] = [
  { message: '请输入当前用户密码', required: true },
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

const newPasswordRules: Rule[] = [
  { message: '请输入新密码', required: true },
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

const confirmPasswordRules: Rule[] = [
  { message: '请再次输入新密码', required: true },
  {
    validator: (_rule: Rule, value: string) =>
      !value || value === passwordFormState.new_password1
        ? Promise.resolve()
        : Promise.reject('两次密码输入不一致'),
  },
];

function openPasswordModal(row: UsersApi.UserRecord) {
  currentRow.value = row;
  Object.assign(passwordFormState, {
    new_password1: '',
    new_password2: '',
    old_password: '',
  });
  passwordOpen.value = true;
}

async function handlePasswordSubmit() {
  const row = currentRow.value;
  if (!row) return;
  try {
    await passwordFormRef.value?.validate();
  } catch {
    return;
  }
  passwordSaving.value = true;
  try {
    // 三字段均 RSA 加密后提交（后端按 344 位密文校验）
    await updateUserPassword({
      new_password: rsaEncrypt(passwordFormState.new_password2),
      old_password: rsaEncrypt(passwordFormState.old_password),
      username: rsaEncrypt(row.username),
    });
    passwordOpen.value = false;
    if (userStore.userInfo?.username === row.username) {
      // 修改自己密码后强制重新登录（与旧前端一致）
      message.success('修改密码成功, 请重新登录');
      setTimeout(() => {
        authStore.logout();
      }, 1000);
    } else {
      message.success('修改密码成功');
    }
  } catch {
    // 全局拦截器已提示（如「当前密码不正确」）
  } finally {
    passwordSaving.value = false;
  }
}
</script>

<template>
  <Page content-class="min-h-0 overflow-hidden">
    <Grid>
      <template #toolbar-actions>
        <Button class="mr-2.5" type="primary" @click="userModalRef?.open()">
          新建用户
        </Button>
      </template>
    </Grid>
    <UserModal ref="userModalRef" @success="refresh" />
    <Modal
      :confirm-loading="passwordSaving"
      :open="passwordOpen"
      title="修改密码"
      :width="560"
      cancel-text="取消"
      destroy-on-close
      ok-text="确定"
      @cancel="passwordOpen = false"
      @ok="handlePasswordSubmit"
    >
      <Form
        ref="passwordFormRef"
        :model="passwordFormState"
        layout="vertical"
      >
        <FormItem label="当前密码" :rules="oldPasswordRules" name="old_password">
          <Input.Password
            v-model:value="passwordFormState.old_password"
            placeholder="请输入当前密码"
          />
        </FormItem>
        <FormItem label="新密码" :rules="newPasswordRules" name="new_password1">
          <Input.Password
            v-model:value="passwordFormState.new_password1"
            placeholder="请设置新密码"
          />
        </FormItem>
        <FormItem
          label="确认密码"
          :rules="confirmPasswordRules"
          name="new_password2"
        >
          <Input.Password
            v-model:value="passwordFormState.new_password2"
            placeholder="请再次输入新密码"
          />
        </FormItem>
      </Form>
    </Modal>
  </Page>
</template>
