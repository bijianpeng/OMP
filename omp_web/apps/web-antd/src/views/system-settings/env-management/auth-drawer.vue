<script lang="ts" setup>
import type { UsersApi } from '#/api/users';

import type { EnvApi } from '#/api/env';

import { computed, ref } from 'vue';

import {
  Alert,
  Button,
  Drawer,
  message,
  Select,
  Spin,
} from 'ant-design-vue';

import { listEnvUsers, updateEnvUsers } from '#/api/env';
import { queryUsers } from '#/api/users';

defineOptions({ name: 'EnvAuthDrawer' });

/** 授权抽屉目标环境 */
const envRecord = ref<null | EnvApi.EnvRecord>(null);
const open = ref(false);
const loading = ref(false);
const saving = ref(false);

/** 全量用户（选项数据源） */
const allUsers = ref<UsersApi.UserRecord[]>([]);
/** 已勾选授权用户 id（初始为该环境现有 UserEnv 行） */
const selectedUserIds = ref<number[]>([]);

/**
 * 可授权用户：排除超级管理员（superuser 天然可访问所有环境、
 * 不落 UserEnv 行，勾选会造成冗余授权行）
 */
const eligibleUsers = computed(() =>
  allUsers.value.filter((user) => !user.is_superuser),
);

/** 多选框选项（label 用户名 / value 用户 id） */
const userOptions = computed(() =>
  eligibleUsers.value.map((user) => ({ label: user.username, value: user.id })),
);

/**
 * 用户接口为分页接口（size 上限 100），循环翻页取全量。
 */
async function fetchAllUsers(): Promise<UsersApi.UserRecord[]> {
  const pageSize = 100;
  let page = 1;
  let count = Number.POSITIVE_INFINITY;
  const all: UsersApi.UserRecord[] = [];
  while (all.length < count) {
    const res = await queryUsers({ page, size: pageSize, username: null });
    count = res.count;
    all.push(...res.results);
    if (res.results.length < pageSize) {
      break;
    }
    page += 1;
  }
  return all;
}

/** 打开授权抽屉（record 目标环境行） */
async function openDrawer(record: EnvApi.EnvRecord) {
  envRecord.value = record;
  open.value = true;
  loading.value = true;
  try {
    const [users, envUsers] = await Promise.all([
      fetchAllUsers(),
      listEnvUsers(record.id),
    ]);
    allUsers.value = users;
    // 勾选集与选项对齐：过滤超级管理员与已删除用户的残留授权 id，
    // 避免多选框出现无匹配选项的裸 id 标签
    const eligibleIds = new Set(
      users.filter((user) => !user.is_superuser).map((user) => user.id),
    );
    selectedUserIds.value = envUsers.user_ids.filter((id) =>
      eligibleIds.has(id),
    );
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

defineExpose({ open: openDrawer });

/**
 * 保存授权：全量覆盖语义——提交的 user_ids 即该环境最终的授权用户列表，
 * 未勾选的用户授权将被移除。
 */
async function handleSave() {
  const record = envRecord.value;
  if (!record) return;
  if (selectedUserIds.value.length === 0) {
    message.warning(
      '授权列表为全量覆盖，保存空列表将导致无普通用户可访问该环境，请至少选择一个用户',
    );
    return;
  }
  saving.value = true;
  try {
    await updateEnvUsers(record.id, selectedUserIds.value);
    message.success('更新授权用户成功');
    open.value = false;
  } catch {
    // 全局拦截器已提示
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Drawer
    v-model:open="open"
    :title="`授权用户 - ${envRecord?.name ?? ''}`"
    placement="right"
    :width="480"
    destroy-on-close
  >
    <div v-if="loading" class="flex h-full items-center justify-center">
      <Spin />
    </div>
    <div v-else class="flex h-full flex-col gap-3">
      <Alert
        :message="`保存后将全量覆盖「${envRecord?.name ?? ''}」的授权用户列表（未勾选的用户授权将被移除）；超级管理员默认可访问所有环境，无需授权。`"
        show-icon
        type="info"
      />
      <Select
        v-model:value="selectedUserIds"
        class="w-full"
        max-tag-count="responsive"
        mode="multiple"
        :options="userOptions"
        placeholder="选择可访问该环境的用户"
      />
      <div class="mt-auto flex justify-end gap-2.5">
        <Button @click="open = false">取消</Button>
        <Button :loading="saving" type="primary" @click="handleSave">
          保存
        </Button>
      </div>
    </div>
  </Drawer>
</template>
