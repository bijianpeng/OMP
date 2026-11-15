<script lang="ts" setup>
import type { SelfHealingStrategyApi } from '#/api/self-healing-strategy';

import { nextTick, ref } from 'vue';

import { z } from '@vben/common-ui';

import { message, Modal } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  createSelfHealingStrategy,
  updateSelfHealingStrategy,
} from '#/api/self-healing-strategy';

defineOptions({ name: 'SelfHealingStrategyModal' });

const emit = defineEmits<{ success: [] }>();

/** 编辑目标策略 id，null 表示新增 */
const editingId = ref<null | number>(null);
const open = ref(false);
const saving = ref(false);

const [Form, formApi] = useVbenForm({
  commonConfig: {
    componentProps: { style: { width: '240px' } },
    labelWidth: 'auto',
  },
  schema: [
    {
      component: 'Select',
      componentProps: {
        allowClear: true,
        maxTagCount: 'responsive',
        mode: 'multiple',
        options: [
          { label: '主机监控Agent', value: 'host' },
          { label: '所有公共组件', value: 'component' },
          { label: '所有自研服务', value: 'service' },
        ],
        placeholder: '请选择自愈维度',
        style: { width: '340px' },
      },
      fieldName: 'repair_instance',
      label: '自愈维度',
      rules: z
        .array(z.string(), { message: '自愈维度' })
        .min(1, { message: '自愈维度' }),
    },
    {
      component: 'InputNumber',
      componentProps: { addonAfter: '分钟', max: 60, min: 1 },
      defaultValue: 30,
      fieldName: 'fresh_rate',
      label: '探测周期',
      rules: z.number({ message: '请填写探测周期' }),
    },
    {
      component: 'Select',
      componentProps: {
        options: [
          { label: '启动 [start]', value: 0 },
          { label: '重启 [restart]', value: 1 },
        ],
        placeholder: '自愈类型',
      },
      defaultValue: 0,
      fieldName: 'instance_tp',
      label: '自愈类型',
      rules: z.number({ message: '请选择自愈类型' }),
    },
    {
      component: 'InputNumber',
      componentProps: { addonAfter: '次', max: 20, min: 1 },
      defaultValue: 5,
      fieldName: 'max_healing_count',
      label: '重试次数',
      rules: z.number({ message: '请填写重试次数' }),
    },
    {
      component: 'Switch',
      componentProps: { style: { width: 'auto' } },
      defaultValue: false,
      fieldName: 'used',
      label: '开启策略',
    },
  ],
  showDefaultActions: false,
});

/**
 * 打开弹窗：不传 record 为新增，传入为编辑（回填行数据）
 */
async function openModal(record?: SelfHealingStrategyApi.Strategy) {
  editingId.value = record?.id ?? null;
  open.value = true;
  await nextTick();
  await formApi.resetForm();
  if (record) {
    await formApi.setValues({
      fresh_rate: record.fresh_rate,
      instance_tp: record.instance_tp,
      max_healing_count: record.max_healing_count,
      repair_instance: record.repair_instance,
      used: record.used,
    });
  }
}

defineExpose({ open: openModal });

async function handleOk() {
  const { valid } = await formApi.validate();
  if (!valid) return;
  const values = await formApi.getValues();
  const payload: SelfHealingStrategyApi.StrategyPayload = {
    fresh_rate: values.fresh_rate as number,
    instance_tp: values.instance_tp as number,
    max_healing_count: values.max_healing_count as number,
    repair_instance: values.repair_instance as string[],
    used: Boolean(values.used),
  };
  saving.value = true;
  try {
    if (editingId.value === null) {
      await createSelfHealingStrategy(payload);
      message.success('添加自愈策略成功');
    } else {
      await updateSelfHealingStrategy(editingId.value, payload);
      message.success('修改自愈策略成功');
    }
    open.value = false;
    emit('success');
  } catch {
    // 全局拦截器已提示错误信息（如「服务不可重复」校验失败）
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal
    :confirm-loading="saving"
    :open="open"
    :title="editingId === null ? '添加自愈策略' : '编辑自愈策略'"
    :width="600"
    cancel-text="取消"
    destroy-on-close
    ok-text="确定"
    @cancel="open = false"
    @ok="handleOk"
  >
    <Form />
  </Modal>
</template>
