<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue/es/form';
import type { UploadFile } from 'ant-design-vue/es/upload/interface';

import { nextTick, reactive, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Form,
  FormItem,
  InputNumber,
  message,
  Modal,
  Tooltip,
  Upload,
} from 'ant-design-vue';

import { createCustomScript } from '#/api/rule-center';

defineOptions({ name: 'RuleExtendAddModal' });

const emit = defineEmits<{ success: [] }>();

const open = ref(false);
const saving = ref(false);
/** 上传限制（与旧前端一致：单个 .py、2MB 以内） */
const MAX_SIZE_MB = 2;

const formRef = ref<FormInstance>();
const model = reactive({ scrape_interval: 60 });
/** 已选采集脚本文件（beforeUpload 返回 false 阻止自动上传，提交时随 FormData 携带） */
const selectedFile = ref<null | UploadFile>(null);

function beforeUpload(file: File) {
  const sizeMb = file.size / 1024 / 1024;
  if (Math.ceil(sizeMb) > MAX_SIZE_MB) {
    message.error('仅支持传入2MB以内文件');
    return Upload.LIST_IGNORE;
  }
  selectedFile.value = { name: file.name, originFileObj: file } as UploadFile;
  return false;
}

function handleRemove() {
  selectedFile.value = null;
}

/** 下载脚本模板（平台静态资源，路径与旧前端一致） */
function downloadTemplate() {
  const url = '/custom_scripts/template.py';
  const a = document.createElement('a');
  a.href = url;
  a.download = url.split('/').pop() ?? 'template.py';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

async function openModal() {
  open.value = true;
  await nextTick();
  formRef.value?.resetFields();
  selectedFile.value = null;
  model.scrape_interval = 60;
}

defineExpose({ open: openModal });

async function handleSubmit() {
  if (!selectedFile.value) {
    message.warning('请上传采集脚本');
    return;
  }
  const valid = await formRef.value
    ?.validate()
    .then(() => true)
    .catch(() => false);
  if (!valid) return;

  const formData = new FormData();
  formData.append('file', selectedFile.value.originFileObj as File);
  formData.append('scrape_interval', String(model.scrape_interval));

  saving.value = true;
  try {
    await createCustomScript(formData);
    message.success('添加操作下发成功');
    open.value = false;
    emit('success');
  } catch {
    // 全局拦截器已提示（如「该脚本已存在，请重新上传！」）
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal
    :confirm-loading="saving"
    :open="open"
    :width="600"
    cancel-text="取消"
    destroy-on-close
    ok-text="确定"
    title="添加扩展指标"
    @cancel="open = false"
    @ok="handleSubmit"
  >
    <Form
      ref="formRef"
      :label-col="{ span: 8 }"
      :model="model"
      :wrapper-col="{ span: 15 }"
    >
      <FormItem label="下载模版">
        <Button @click="downloadTemplate">
          <IconifyIcon class="mr-1 inline align-[-2px]" icon="lucide:download" />
          点击下载
        </Button>
      </FormItem>
      <FormItem label="上传采集脚本" required>
        <Upload
          :before-upload="beforeUpload"
          :file-list="selectedFile ? [selectedFile] : []"
          :max-count="1"
          accept=".py"
          name="file"
          @remove="handleRemove"
        >
          <Button>
            <IconifyIcon class="mr-1 inline align-[-2px]" icon="lucide:upload" />
            点击上传
          </Button>
        </Upload>
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
    </Form>
  </Modal>
</template>
