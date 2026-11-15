<script lang="ts" setup>
// InputPassword 仅从 input 子模块导出，顶层用 Input.Password 点语法最稳
import type { Rule } from 'ant-design-vue/es/form';

import { onMounted, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';

import { Button, Card, Form, FormItem, Input, InputNumber, message } from 'ant-design-vue';

import {
  queryEmailSmtpConfig,
  updateEmailSmtpConfig,
} from '#/api/promemonitor';

defineOptions({ name: 'EmailSettings' });

/**
 * 邮件 SMTP 全局配置（告警邮件发送依赖此配置）。
 * 布局遵循配置表单模板：Page 允许滚动 + Card 分组 + Form @finish 提交。
 * 表单字段名与后端契约一致（host/port/username/password），省去旧前端字段映射。
 */

const loading = ref(false);
const saving = ref(false);
const model = reactive({
  host: '',
  password: '',
  port: undefined as number | undefined,
  username: '',
});

const rules: Record<string, Rule[]> = {
  host: [{ message: '请输入邮件服务器地址', required: true }],
  password: [{ message: '请输入发件人令牌', required: true }],
  port: [{ message: '请输入端口号', required: true }],
  username: [
    { message: '请输入发件人邮箱', required: true },
    { message: '请输入正确格式的邮箱', type: 'email' },
  ],
};

async function loadConfig() {
  loading.value = true;
  try {
    const data = await queryEmailSmtpConfig();
    model.host = data?.host ?? '';
    model.password = data?.password ?? '';
    model.port = data?.port ?? undefined;
    model.username = data?.username ?? '';
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

async function saveConfig() {
  saving.value = true;
  try {
    await updateEmailSmtpConfig({
      host: model.host,
      password: model.password,
      port: model.port as number,
      username: model.username,
    });
    message.success('更新邮件全局设置成功');
    // 与旧页一致：保存成功后重查回显（服务端规范化值覆盖本地输入）
    await loadConfig();
  } catch {
    // 失败保留表单状态，全局拦截器已提示
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  loadConfig();
});
</script>

<template>
  <Page>
    <div class="flex flex-col gap-4">
      <Card title="全局设置" :loading="loading">
        <Form
          :model="model"
          :rules="rules"
          layout="vertical"
          @finish="saveConfig"
        >
          <!-- 限宽挂包裹 div：antdv 样式未入 @layer，宽度类直接打组件上会被 width:100% 覆盖 -->
          <FormItem label="邮件服务器" name="host">
            <div class="max-w-[480px]">
              <Input
                v-model:value="model.host"
                placeholder="例如: 192.168.10.10"
              />
            </div>
          </FormItem>
          <FormItem label="端口号" name="port">
            <!-- 端口仅 1~5 位数字，控件单独限窄 -->
            <div class="max-w-[180px]">
              <InputNumber
                v-model:value="model.port"
                :max="65535"
                :min="1"
                placeholder="例如: 465"
                :style="{ width: '100%' }"
              />
            </div>
          </FormItem>
          <FormItem label="发件人邮箱" name="username">
            <div class="max-w-[480px]">
              <Input
                v-model:value="model.username"
                placeholder="例如: emailname@163.com"
              />
            </div>
          </FormItem>
          <FormItem label="发件人令牌" name="password">
            <div class="max-w-[480px]">
              <Input.Password
                v-model:value="model.password"
                placeholder="请输入Token"
              />
            </div>
          </FormItem>
          <Button type="primary" html-type="submit" :loading="saving">
            保存
          </Button>
        </Form>
      </Card>
    </div>
  </Page>
</template>
