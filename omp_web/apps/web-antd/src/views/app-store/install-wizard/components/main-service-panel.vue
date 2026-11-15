<script lang="ts" setup>
import type { ArgItem } from '#/api/app-store-install';

import { inject } from 'vue';

import { FormItem, Input, Select } from 'ant-design-vue';

import ArgFormItems from './arg-form-items.vue';
import CollapseArea from './collapse-area.vue';
import CollapseLink from './collapse-link.vue';
import SectionTitle from './section-title.vue';
import { INSTALL_FIELD_ERRORS } from '../shared';

/**
 * Step2 主服务面板：选择主机 + 实例名称（必填），「查看更多配置」内
 * 为主服务自身的安装参数/端口表单项。
 * 表单键 owner 与提交载荷的 name 段一致（组件页为入口 app_name、
 * 应用页为 pro_services[0].name，见两页面契约）。
 * 后端校验失败回填在 `instanceName` 上的错误经注入展示。
 */
defineOptions({ name: 'MainServicePanel' });

defineProps<{
  args?: ArgItem[];
  /** 页面共享表单模型（扁平键 → 值） */
  formModel: Record<string, any>;
  ipList: string[];
  open: boolean;
  /** 表单键中的服务名段（提交载荷 name 同此值） */
  owner: string;
  ports?: ArgItem[];
  /** 区块标题（组件页为路由名、应用页为包含服务名） */
  title: string;
}>();

const emit = defineEmits<{ toggle: []; 'ip-change': [ip: string] }>();

const fieldErrors = inject(INSTALL_FIELD_ERRORS, {});
</script>

<template>
  <section class="mt-5 bg-card p-2.5">
    <SectionTitle :title="title" />

    <div class="mt-2.5 pb-10 pl-5">
      <div class="flex items-start justify-between">
        <div class="flex items-center">
          <FormItem label="选择主机" name="ip">
            <Select
              v-model:value="formModel.ip"
              class="!w-[200px]"
              :options="ipList.map((ip) => ({ label: ip, value: ip }))"
              placeholder="请选择主机"
              @change="(v) => emit('ip-change', v as string)"
            />
          </FormItem>
          <FormItem
            class="ml-[30px]"
            :help="fieldErrors['instanceName']"
            label="实例名称"
            :rules="[{ message: '请填写实例名称', required: true }]"
            name="instanceName"
            :validate-status="fieldErrors['instanceName'] ? 'error' : ''"
          >
            <Input v-model:value="formModel.instanceName" />
          </FormItem>
        </div>
        <CollapseLink :open="open" text="查看更多配置" @toggle="emit('toggle')" />
      </div>

      <CollapseArea :open="open">
        <div class="pt-5">
          <ArgFormItems
            :args="args"
            :form-model="formModel"
            :owner="owner"
          />
          <ArgFormItems
            :form-model="formModel"
            :owner="owner"
            :ports="ports"
          />
        </div>
      </CollapseArea>
    </div>
  </section>
</template>
