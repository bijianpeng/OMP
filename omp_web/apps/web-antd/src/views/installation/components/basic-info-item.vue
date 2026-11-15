<script lang="ts" setup>
import type { BasicItem } from '#/api/installation';

import { onMounted, reactive, shallowRef } from 'vue';

import { FormItem, Input, InputNumber } from 'ant-design-vue';

import { injectModel, INSTALL_BASIC_MODEL, randomCode } from '../shared';
import CollapseArea from './collapse-area.vue';
import CollapseLink from './collapse-link.vue';

/**
 * Step1 基本信息产品行：名称/版本/实例名称 + 「更改服务信息」展开
 * 各服务的部署数量步进器。
 * 表单键契约：`${产品名}` = 实例名称；`${产品名}=${服务名}` = 部署数量
 * （提交时按 `=` 拆段还原，两侧序列化一致才能对上）。
 */
defineOptions({ name: 'InstallationBasicInfoItem' });

const props = defineProps<{
  data: BasicItem;
}>();

/** 扁平表单模型（step1 provide，与外层 Form :model 同源） */
const formModel = injectModel(INSTALL_BASIC_MODEL);

/** 服务信息展开状态 */
const isOpen = shallowRef(false);

/** 各服务上一次合法数量（步长越界回退用，键 `${产品名}=${服务名}`） */
const prevNum = reactive<Record<string, number>>({});

onMounted(() => {
  formModel[props.data.name] = `${props.data.name}-${randomCode()}`;
  for (const item of props.data.services_list) {
    const key = `${props.data.name}=${item.name}`;
    const def = Number(item.deploy_mode.default);
    prevNum[key] = def;
    formModel[key] = def;
  }
});

/**
 * 数量步进约束（旧 numRef 契约）：新值必须与上一次合法值恰好相差一个步长，
 * 否则回退（InputNumber 步进按钮 +1/-1，手输非法值不被接受）。
 */
function handleNumChange(key: string, step: number, value: null | number) {
  const prev = prevNum[key] ?? 0;
  if (value !== null && (value - step === prev || value + step === prev)) {
    prevNum[key] = value;
  } else {
    formModel[key] = prev;
  }
}
</script>

<template>
  <div class="mt-6 flex items-center">
    <div class="flex-2 pl-5">{{ data.name }}</div>
    <div class="flex-2">{{ data.version }}</div>
    <div class="flex-3 pr-8">
      <!-- 旧实现校验文案误写「请输入密码」，此处按字段语义修正 -->
      <FormItem
        :name="data.name"
        :rules="[{ message: '请输入实例名称', required: true }]"
        class="!mb-0"
        label="实例名称"
      >
        <Input v-model:value="formModel[data.name]" />
      </FormItem>
    </div>
    <div class="flex-7 flex justify-between">
      <div></div>
      <div class="pr-5">
        <CollapseLink
          :open="isOpen"
          text="更改服务信息"
          @toggle="isOpen = !isOpen"
        />
      </div>
    </div>
  </div>

  <CollapseArea :open="isOpen">
    <div class="flex flex-wrap p-2.5">
      <div
        v-for="item in data.services_list"
        :key="item.name"
        class="w-[360px]"
      >
        <FormItem
          class="!mb-0"
          :label="item.name"
          :label-col="{ style: { width: '180px' } }"
          :name="`${data.name}=${item.name}`"
        >
          <InputNumber
            v-model:value="formModel[`${data.name}=${item.name}`]"
            :disabled="item.deploy_mode.step === 0"
            :keyboard="false"
            :max="32"
            :min="1"
            :step="item.deploy_mode.step"
            @change="(v: any) => handleNumChange(`${data.name}=${item.name}`, item.deploy_mode.step, v)"
          />
        </FormItem>
      </div>
    </div>
  </CollapseArea>

  <div class="mt-1 whitespace-pre-line text-[red]">{{ data.error_msg }}</div>
</template>
