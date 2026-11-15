<script lang="ts" setup>
import type { DependenceItem } from '#/api/app-store-install';

import { FormItem, Input, Select } from 'ant-design-vue';

import ArgFormItems from './arg-form-items.vue';
import CollapseArea from './collapse-area.vue';
import CollapseLink from './collapse-link.vue';
import SectionTitle from './section-title.vue';

/**
 * Step2 依赖服务安装面板（jdk 等基础环境随主服务同机安装）。
 * 主机固定为所选 IP（disabled），实例名默认 `{服务名}-{IP 末两段}`，
 * 「查看更多配置」内为依赖自身的参数/端口表单项。
 *
 * FormItem 必须置于页面唯一的 <Form> 上下文内（共享 model 与校验），
 * 值经 formModel 扁平键绑定，本组件只承担布局。
 */
defineOptions({ name: 'DependServicePanel' });

defineProps<{
  dep: DependenceItem;
  /** 页面共享表单模型（扁平键 → 值） */
  formModel: Record<string, any>;
  ipList: string[];
  open: boolean;
}>();

const emit = defineEmits<{ toggle: [] }>();
</script>

<template>
  <section class="mt-5 bg-card p-2.5">
    <SectionTitle :title="dep.name" />

    <div class="mt-2.5 pb-10 pl-5">
      <div class="flex items-start justify-between">
        <div class="flex items-center">
          <FormItem :name="`${dep.name}|ip`">
            <Select
              v-model:value="formModel[`${dep.name}|ip`]"
              class="!w-[200px]"
              disabled
              :options="ipList.map((ip) => ({ label: ip, value: ip }))"
            />
          </FormItem>
          <FormItem
            class="ml-[30px]"
            :name="`${dep.name}|instanceName`"
            :rules="[{ message: '请填写实例名称', required: true }]"
          >
            <Input v-model:value="formModel[`${dep.name}|instanceName`]" />
          </FormItem>
        </div>
        <CollapseLink :open="open" text="查看更多配置" @toggle="emit('toggle')" />
      </div>

      <CollapseArea :open="open">
        <div class="pt-5">
          <ArgFormItems
            :args="dep.app_install_args"
            :form-model="formModel"
            :owner="dep.name"
          />
          <ArgFormItems
            :form-model="formModel"
            :owner="dep.name"
            :ports="dep.app_port"
          />
        </div>
      </CollapseArea>
    </div>
  </section>
</template>
