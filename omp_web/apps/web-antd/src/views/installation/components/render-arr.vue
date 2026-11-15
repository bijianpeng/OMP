<script lang="ts" setup>
import type { DependenceItem } from '#/api/installation';

import { onMounted, shallowRef, watch } from 'vue';

import { FormItem, Input, Select } from 'ant-design-vue';

import { injectModel, INSTALL_DEPENDENT_MODEL, randomCode } from '../shared';

/**
 * 模式型依赖配置（mysql 等）：部署模式下拉 + 主从/主主集群名 + 主主 vip。
 * 表单键契约：`${依赖名}=num`（值为模式 key）/ `${依赖名}=name` / `${依赖名}=vip`。
 */
defineOptions({ name: 'InstallationRenderArr' });

const props = defineProps<{
  data: DependenceItem;
}>();

/** 扁平表单模型（step1 provide，与外层 Form :model 同源） */
const formModel = injectModel(INSTALL_DEPENDENT_MODEL);

const deployMode = props.data.deploy_mode as { key: string; name: string }[];

/** 当前部署模式 key */
const deployValue = shallowRef(deployMode[0]?.key ?? '');

/** 主从/主主模式需要集群名 */
function needClusterName(value: string) {
  return value === 'master-slave' || value === 'master-master';
}

onMounted(() => {
  formModel[`${props.data.name}=num`] = deployValue.value;
  if (needClusterName(deployValue.value)) {
    formModel[`${props.data.name}=name`] =
      `${props.data.name}-cluster-${randomCode(7)}`;
  }
});

watch(deployValue, (value) => {
  formModel[`${props.data.name}=num`] = value;
  if (needClusterName(value)) {
    formModel[`${props.data.name}=name`] =
      `${props.data.name}-cluster-${randomCode(7)}`;
  }
});
</script>

<template>
  <div class="flex-3">
    <FormItem
      class="!mb-0"
      label="部署数量"
      :name="`${data.name}=num`"
      style="width: 100px"
    >
      <Select
        v-model:value="formModel[`${data.name}=num`]"
        :options="deployMode.map((item) => ({ label: item.name, value: item.key }))"
        @change="(v: any) => (deployValue = String(v))"
      />
    </FormItem>
  </div>
  <div class="flex-3">
    <FormItem
      v-if="needClusterName(deployValue)"
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
  <div class="flex-2">
    <FormItem
      v-if="deployValue === 'master-master'"
      class="!mb-0"
      label="vip"
      :name="`${data.name}=vip`"
      :rules="[{ message: '请输入vip', required: true }]"
      style="width: 180px"
    >
      <Input
        v-model:value="formModel[`${data.name}=vip`]"
        placeholder="请输入vip"
      />
    </FormItem>
  </div>
</template>
