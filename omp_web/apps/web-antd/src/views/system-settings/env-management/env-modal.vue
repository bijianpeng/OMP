<script lang="ts" setup>
import type { EnvApi } from '#/api/env';

import type { FormInstance } from 'ant-design-vue';
import type { Rule } from 'ant-design-vue/es/form';

import { reactive, ref } from 'vue';

import {
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Radio,
  RadioGroup,
  Select,
} from 'ant-design-vue';

import { createEnv, listEnvs, updateEnv } from '#/api/env';

defineOptions({ name: 'EnvModal' });

const emit = defineEmits<{ success: [] }>();

/** 环境编码 slug 规则（与后端校验一致：字母开头，字母/数字/下划线/中划线） */
const CODE_PATTERN = /^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/;

const editingEnv = ref<null | EnvApi.EnvRecord>(null);
const open = ref(false);
const saving = ref(false);

/** 配置来源可选环境（仅新建时使用） */
const envOptions = ref<EnvApi.EnvRecord[]>([]);

const formRef = ref<FormInstance>();
const formState = reactive({
  code: '',
  /** copy：从环境复制 / blank：空白创建 */
  configMode: 'copy',
  /** 来源环境 id（undefined = 未选择；提交空白创建时传 null） */
  config_source: undefined as number | undefined,
  description: '',
  name: '',
});

const nameRules: Rule[] = [{ message: '请输入环境名称', required: true }];

const codeRules: Rule[] = [
  { message: '请输入环境编码', required: true },
  {
    validator: (_rule: Rule, value: string) =>
      !value || CODE_PATTERN.test(value)
        ? Promise.resolve()
        : Promise.reject(
            '环境编码需以字母开头，仅支持字母、数字、下划线和中划线，最长 64 位',
          ),
  },
];

const configSourceRules: Rule[] = [
  { message: '请选择来源环境', required: true },
];

/** 打开弹窗：不传为新建，传入为编辑（code 只读展示） */
async function openModal(record?: EnvApi.EnvRecord) {
  editingEnv.value = record ?? null;
  open.value = true;
  if (record) {
    Object.assign(formState, {
      code: record.code,
      configMode: 'copy',
      config_source: undefined,
      description: record.description ?? '',
      name: record.name,
    });
  } else {
    // 配置来源候选环境（当前用户可见环境；superuser 全量）
    try {
      envOptions.value = await listEnvs();
    } catch {
      // 全局拦截器已提示；下拉为空时仍可改为空白创建
    }
    // 配置来源默认「从 default 环境复制」（spec 推荐默认）
    const defaultEnv =
      envOptions.value.find((env) => env.code === 'default') ??
      envOptions.value[0];
    Object.assign(formState, {
      code: '',
      configMode: 'copy',
      config_source: defaultEnv?.id,
      description: '',
      name: '',
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
    if (editingEnv.value === null) {
      await createEnv({
        code: formState.code.trim(),
        config_source:
          formState.configMode === 'copy' ? formState.config_source : null,
        description: formState.description.trim(),
        name: formState.name.trim(),
      });
      message.success('新建环境成功');
    } else {
      // code 创建后不可改（后端 read_only），编辑仅提交名称/描述
      await updateEnv(editingEnv.value.id, {
        description: formState.description.trim(),
        name: formState.name.trim(),
      });
      message.success('修改环境成功');
    }
    close();
    emit('success');
  } catch {
    // 全局拦截器已提示（如环境编码重复、非法字符等后端校验）
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal
    :confirm-loading="saving"
    :open="open"
    :title="editingEnv === null ? '新建环境' : '编辑环境'"
    :width="560"
    cancel-text="取消"
    destroy-on-close
    ok-text="确定"
    @cancel="close"
    @ok="handleSubmit"
  >
    <Form ref="formRef" :model="formState" layout="vertical">
      <FormItem label="环境名称" :rules="nameRules" name="name">
        <Input
          v-model:value="formState.name"
          :maxlength="64"
          placeholder="请输入环境名称（展示名，可中文）"
        />
      </FormItem>
      <FormItem
        :extra="
          editingEnv === null
            ? '以字母开头，仅支持字母、数字、下划线和中划线，最长 64 位'
            : '环境编码创建后不可修改'
        "
        :rules="codeRules"
        label="环境编码"
        name="code"
      >
        <Input
          v-model:value="formState.code"
          :disabled="editingEnv !== null"
          :maxlength="64"
          placeholder="例如: prod"
        />
      </FormItem>
      <FormItem label="描述" name="description">
        <Input
          v-model:value="formState.description"
          :maxlength="255"
          placeholder="请输入环境描述（可选）"
        />
      </FormItem>
      <template v-if="editingEnv === null">
        <FormItem label="配置来源" name="configMode">
          <div class="flex flex-col gap-2">
            <RadioGroup v-model:value="formState.configMode">
              <Radio value="copy">从环境复制</Radio>
              <Radio value="blank">空白创建</Radio>
            </RadioGroup>
            <div class="text-xs text-gray-400">
              {{
                formState.configMode === 'copy'
                  ? '复制来源环境的告警规则、阈值、推送与自愈配置（快照式，此后互不影响）'
                  : '不复制任何配置，该环境的监控/告警等配置初始为空'
              }}
            </div>
          </div>
        </FormItem>
        <FormItem
          v-if="formState.configMode === 'copy'"
          :rules="configSourceRules"
          label="来源环境"
          name="config_source"
        >
          <Select
            v-model:value="formState.config_source"
            :options="
              envOptions.map((env) => ({
                label: `${env.name}（${env.code}）`,
                value: env.id,
              }))
            "
            placeholder="选择来源环境"
          />
        </FormItem>
      </template>
    </Form>
  </Modal>
</template>
