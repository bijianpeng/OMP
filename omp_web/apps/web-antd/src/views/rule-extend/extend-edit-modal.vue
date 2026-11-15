<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue/es/form';

import type { RuleCenterApi } from '#/api/rule-center';

import { nextTick, reactive, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Tooltip,
} from 'ant-design-vue';

import { updateCustomScript } from '#/api/rule-center';

import HostSelectModal from './host-select-modal.vue';

defineOptions({ name: 'RuleExtendEditModal' });

const emit = defineEmits<{ success: [] }>();

const open = ref(false);
const saving = ref(false);
const editingId = ref<null | number>(null);

const formRef = ref<FormInstance>();
const model = reactive({
  description: '',
  scrape_interval: 60,
});

/** 已选绑定主机（tag 区块数据源；id 仅作为 tag key 使用） */
const hosts = ref<{ id: number; ip: string }[]>([]);
/** 绑定主机为空时的校验提示（旧前端为自定义区块手动校验，非表单规则） */
const showHostError = ref(false);

const hostSelectRef = ref<InstanceType<typeof HostSelectModal>>();

async function openModal(record: RuleCenterApi.CustomScript) {
  editingId.value = record.id;
  open.value = true;
  await nextTick();
  formRef.value?.resetFields();
  model.description = record.description ?? '';
  model.scrape_interval = record.scrape_interval ?? 60;
  // 回填已绑定主机（id 用索引占位，仅作 key）
  hosts.value = (record.bound_hosts ?? []).map((ip, idx) => ({ id: idx, ip }));
  showHostError.value = false;
}

defineExpose({ open: openModal });

function removeHost(tag: { id: number; ip: string }) {
  hosts.value = hosts.value.filter((item) => item.id !== tag.id);
  if (hosts.value.length === 0) {
    showHostError.value = true;
  }
}

function clearHosts() {
  hosts.value = [];
  showHostError.value = true;
}

function openHostSelect() {
  showHostError.value = false;
  hostSelectRef.value?.open(hosts.value.map((item) => item.ip));
}

function handleHostsConfirm(
  rows: RuleCenterApi.HostItem[],
) {
  hosts.value = rows.map((item) => ({ id: item.id, ip: item.ip ?? '' }));
}

async function handleSubmit() {
  if (hosts.value.length === 0) {
    showHostError.value = true;
    return;
  }
  const valid = await formRef.value
    ?.validate()
    .then(() => true)
    .catch(() => false);
  if (!valid) return;

  saving.value = true;
  try {
    await updateCustomScript(editingId.value as number, {
      bound_hosts: hosts.value.map((item) => item.ip),
      description: model.description,
      scrape_interval: model.scrape_interval,
    });
    message.success('修改操作下发成功');
    open.value = false;
    emit('success');
  } catch {
    // 全局拦截器已提示
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal
    :confirm-loading="saving"
    :open="open"
    :width="900"
    cancel-text="取消"
    destroy-on-close
    ok-text="确定"
    title="修改扩展指标"
    @cancel="open = false"
    @ok="handleSubmit"
  >
    <Form
      ref="formRef"
      :label-col="{ span: 4 }"
      :model="model"
      :wrapper-col="{ span: 19 }"
    >
      <FormItem label="描述" name="description" required>
        <div class="max-w-[520px]">
          <Input v-model:value="model.description" placeholder="请输入描述" />
        </div>
      </FormItem>
      <FormItem label="探测周期(s)" name="scrape_interval" required>
        <Tooltip title="指定Prometheus对指标采集间隔时间">
          <InputNumber
            v-model:value="model.scrape_interval"
            :max="120"
            :min="1"
            :precision="0"
          />
        </Tooltip>
      </FormItem>
      <FormItem label="绑定主机" required>
        <!-- 绑定主机为自定义选择区块：手动校验（旧前端语义），红框 + 下方红字提示 -->
        <div
          class="relative flex min-h-20 flex-wrap gap-2 pb-12"
          :class="showHostError ? 'border border-red-500' : 'border border-transparent bg-muted'"
        >
          <span
            v-for="tag in hosts"
            :key="tag.id"
            class="flex h-7 max-w-full items-center overflow-hidden whitespace-nowrap rounded border border-border bg-card pl-3"
          >
            {{ tag.ip }}
            <IconifyIcon
              class="mx-2 shrink-0 cursor-pointer"
              icon="lucide:x"
              @click="removeHost(tag)"
            />
          </span>
          <div class="absolute bottom-2 left-1/2 flex -translate-x-1/2 gap-4">
            <Button size="small" @click="clearHosts">清除</Button>
            <Button size="small" type="primary" @click="openHostSelect">添加</Button>
          </div>
        </div>
        <div v-if="showHostError" class="mt-1 text-xs text-red-500">
          请选择绑定主机
        </div>
      </FormItem>
    </Form>

    <HostSelectModal ref="hostSelectRef" @confirm="handleHostsConfirm" />
  </Modal>
</template>
