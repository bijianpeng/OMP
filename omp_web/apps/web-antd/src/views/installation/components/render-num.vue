<script lang="ts" setup>
import type { DependenceItem } from '#/api/installation';

import { onMounted, shallowRef } from 'vue';

import { FormItem, Input, InputNumber } from 'ant-design-vue';

import { injectModel, INSTALL_DEPENDENT_MODEL, randomCode } from '../shared';

/**
 * 数量型依赖配置：部署数量步进器 + 数量 >1 时自动生成集群名输入。
 * 表单键契约：`${依赖名}=num` / `${依赖名}=name`。
 */
defineOptions({ name: 'InstallationRenderNum' });

const props = defineProps<{
  data: DependenceItem;
}>();

/** 扁平表单模型（step1 provide，与外层 Form :model 同源） */
const formModel = injectModel(INSTALL_DEPENDENT_MODEL);

const deployMode = props.data.deploy_mode as {
  default: number;
  step: number;
};

/** 当前数量（>1 时展示集群名输入） */
const num = shallowRef(deployMode.default);
/** 上一次合法数量（步长越界回退用） */
let prevNum = deployMode.default;

onMounted(() => {
  formModel[`${props.data.name}=num`] = deployMode.default;
  if (deployMode.default > 1) {
    formModel[`${props.data.name}=name`] =
      `${props.data.name}-cluster-${randomCode(7)}`;
  }
});

function handleNumChange(value: null | number) {
  if (value !== null) {
    if (
      value - deployMode.step === prevNum ||
      value + deployMode.step === prevNum
    ) {
      prevNum = value;
      num.value = value;
    } else {
      formModel[`${props.data.name}=num`] = prevNum;
    }
  }
  if (value !== null && value > 1) {
    formModel[`${props.data.name}=name`] =
      `${props.data.name}-cluster-${randomCode(7)}`;
  }
}
</script>

<template>
  <div class="flex-3">
    <FormItem
      class="!mb-0"
      label="部署数量"
      :name="`${data.name}=num`"
      style="width: 180px"
    >
      <InputNumber
        v-model:value="formModel[`${data.name}=num`]"
        :disabled="deployMode.step === 0"
        :keyboard="false"
        :max="32"
        :min="1"
        :step="deployMode.step"
        :style="{ width: '100px' }"
        @change="(v: any) => handleNumChange(v)"
      />
    </FormItem>
  </div>
  <div class="flex-5">
    <FormItem
      v-if="num > 1"
      class="!mb-0"
      label="集群名称"
      :name="`${data.name}=name`"
      :rules="[{ message: '请输入集群名称', required: true }]"
      style="width: 240px"
    >
      <Input
        v-model:value="formModel[`${data.name}=name`]"
        placeholder="请输入集群名称"
      />
    </FormItem>
  </div>
</template>
