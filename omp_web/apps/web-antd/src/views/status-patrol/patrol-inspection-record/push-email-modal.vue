<script lang="ts" setup>
import { reactive, shallowRef, watch } from 'vue';
import { useRouter } from 'vue-router';

import { Form, FormItem, Input, message, Modal } from 'ant-design-vue';

import { getPushEmailSetting, pushInspectionEmail } from '#/api/inspection';

defineOptions({ name: 'InspectionPushEmailModal' });

const props = defineProps<{
  /** 推送目标：巡检记录 id + 巡检类型（module） */
  target: null | { id: number; module: string };
}>();

const emit = defineEmits<{
  /** 推送成功（父组件据此关闭弹窗并刷新列表） */
  pushed: [];
}>();

/** 弹窗开关（父组件 v-model:open 控制） */
const open = defineModel<boolean>('open', { default: false });

const router = useRouter();

const formState = reactive({ toUsers: '' });
const rules = {
  toUsers: [
    { message: '请输入接收人邮箱', required: true, whitespace: true },
    { message: '请输入正确格式的邮箱', type: 'email' as const },
  ],
};
const { validate, resetFields } = Form.useForm(formState, rules);

const submitting = shallowRef(false);

/** 打开时拉取默认收件人配置回填表单（对齐旧页 fetchPushDate） */
watch(open, async (value) => {
  if (!value) return;
  resetFields();
  try {
    const setting = await getPushEmailSetting();
    formState.toUsers = setting?.to_users ?? '';
  } catch {
    // 读取默认配置失败不阻塞推送，收件人由用户手动填写
  }
});

async function handleOk() {
  if (!props.target) return;
  try {
    await validate();
  } catch {
    return; // 校验失败，antd 已在表单上标错
  }
  submitting.value = true;
  try {
    await pushInspectionEmail({
      id: props.target.id,
      module: props.target.module,
      to_users: formState.toUsers,
    });
    message.success('推送成功');
    emit('pushed');
  } catch {
    // 失败保留表单，全局拦截器已提示（与同批 distribute/回滚的 handleOk 一致）
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <Modal
    v-model:open="open"
    :confirm-loading="submitting"
    title="邮件推送"
    @ok="handleOk"
  >
    <Form
      :model="formState"
      :rules="rules"
      class="pl-10 pt-2"
      layout="horizontal"
    >
      <FormItem label="接收人" name="toUsers">
        <Input
          v-model:value="formState.toUsers"
          :maxlength="256"
          allow-clear
          placeholder="例如: emailname@163.com"
          style="width: 320px"
        />
      </FormItem>
    </Form>
    <p class="mt-8 pl-10 text-[13px] flex items-center gap-2">
      <span class="text-amber-500">!</span>
      如果需要配置默认的巡检报告接收人，请点击
      <a @click="router.push('/status-patrol/patrol-strategy')">这里</a>
    </p>
  </Modal>
</template>
