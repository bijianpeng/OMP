<script lang="ts" setup>
import type { DependenceItem } from '#/api/installation';

import { shallowRef, watch } from 'vue';

import { Checkbox, FormItem, Select } from 'ant-design-vue';

import { injectModel, INSTALL_DEPENDENT_MODEL } from '../shared';
import RenderArr from './render-arr.vue';
import RenderNum from './render-num.vue';

/**
 * 依赖「复用依赖」行：勾选时选择既有实例（value 为实例信息 JSON 串，
 * 提交侧 JSON.parse 还原），取消勾选回落到新装配置行。
 * 表单键契约：`${依赖名}` = 实例信息 JSON 串。
 */
defineOptions({ name: 'InstallationDeployInstanceRow' });

const props = defineProps<{
  data: DependenceItem;
}>();

/** 扁平表单模型（step1 provide，与外层 Form :model 同源） */
const formModel = injectModel(INSTALL_DEPENDENT_MODEL);

/** 是否复用既有实例（默认勾选，旧契约） */
const check = shallowRef(true);

/** 既有实例下拉选项（value = 实例信息 JSON 串，旧提交契约） */
const instanceOptions = props.data.exist_instance.map((item) => ({
  label: item.name,
  value: JSON.stringify({ id: item.id, name: item.name, type: item.type }),
}));

watch(
  check,
  (value) => {
    if (value) {
      // 勾选/重新勾选时默认选第一个既有实例（旧 useEffect 契约）
      formModel[props.data.name] = instanceOptions[0]?.value ?? '';
    }
    // 取消勾选时不清 formModel：提交侧经 formRef.getFieldsValue()
    // 只读已挂载字段，`${name}` 随 FormItem 卸载自动不参与提交（旧语义）
  },
  { immediate: true },
);
</script>

<template>
  <div class="flex-1 pl-5">{{ data.name }}</div>
  <div class="flex-1">{{ data.version }}</div>
  <template v-if="check">
    <div class="flex-3">
      <FormItem
        class="!mb-0"
        label="选择实例"
        :name="data.name"
        style="width: 180px"
      >
        <Select v-model:value="formModel[data.name]" :options="instanceOptions" />
      </FormItem>
    </div>
    <div class="flex-5"></div>
  </template>
  <RenderArr
    v-else-if="Array.isArray(data.deploy_mode)"
    :data="data"
  />
  <RenderNum v-else :data="data" />
  <div class="flex-2">
    <div class="flex items-center justify-end pr-[70px] text-[13px]">
      <Checkbox
        :checked="check"
        @change="(e: any) => (check = e.target.checked)"
      >
        复用依赖
      </Checkbox>
    </div>
  </div>
</template>
