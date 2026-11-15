<script lang="ts" setup>
import type { ArgItem } from '#/api/app-store-install';

import { computed, inject } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { FormItem, Input, Tooltip } from 'ant-design-vue';

import { INSTALL_FIELD_ERRORS, installArgKey, portArgKey } from '../shared';

/**
 * 「查看更多配置」内的参数/端口表单项组。
 *
 * 表单项 name 为 `install|{owner}|{json}` / `port|{owner}|{json}`
 * 三段扁平键（shared.ts 契约），值绑定页面共享 formModel，
 * 提交时按扁平键拆段组装载荷。
 * antdv4 Form.Item 不自动接管值绑定，需显式 v-model 到 formModel 键。
 * 后端校验失败的字段错误经 INSTALL_FIELD_ERRORS 注入展示（help 覆盖）。
 */
defineOptions({ name: 'InstallArgFormItems' });

const props = defineProps<{
  /** 安装参数列表（数据分区字段带提示） */
  args?: ArgItem[];
  /** 页面共享表单模型（扁平键 → 值） */
  formModel: Record<string, any>;
  /** 表单键中的服务名段 */
  owner: string;
  /** 端口列表 */
  ports?: ArgItem[];
}>();

const fieldErrors = inject(INSTALL_FIELD_ERRORS, {});

const installItems = computed(() =>
  (props.args ?? []).map((arg) => ({
    arg,
    key: installArgKey(props.owner, arg),
  })),
);

const portItems = computed(() =>
  (props.ports ?? []).map((port) => ({
    key: portArgKey(props.owner, port),
    port,
  })),
);
</script>

<template>
  <FormItem
    v-for="{ arg, key } in installItems"
    :key="arg.key"
    class="pb-4 pl-4"
    :help="fieldErrors[key]"
    :label="arg.name"
    :label-col="{ style: { width: '70px' } }"
    :name="key"
    :rules="[{ message: `请填写${arg.name}`, required: true }]"
    :validate-status="fieldErrors[key] ? 'error' : ''"
  >
    <Input
      v-model:value="formModel[key]"
      class="!w-[420px]"
      :addon-before="arg.dir_key ? '/ 数据分区' : undefined"
    >
      <template v-if="arg.dir_key" #suffix>
        <Tooltip title="数据分区：主机所设置的数据分区">
          <IconifyIcon class="text-muted-foreground" icon="lucide:info" />
        </Tooltip>
      </template>
    </Input>
  </FormItem>
  <FormItem
    v-for="{ key, port } in portItems"
    :key="port.key"
    class="pb-4 pl-4"
    :help="fieldErrors[key]"
    :label="port.name"
    :label-col="{ style: { width: '70px' } }"
    :name="key"
    :rules="[{ message: `请填写${port.name}`, required: true }]"
    :validate-status="fieldErrors[key] ? 'error' : ''"
  >
    <Input
      v-model:value="formModel[key]"
      class="!w-[420px]"
      :addon-before="port.dir_key ? '/ 数据分区' : undefined"
    >
      <template v-if="port.dir_key" #suffix>
        <Tooltip title="数据分区：主机所设置的数据分区">
          <IconifyIcon class="text-muted-foreground" icon="lucide:info" />
        </Tooltip>
      </template>
    </Input>
  </FormItem>
</template>
