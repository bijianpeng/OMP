<script lang="ts" setup>
import type { ConfigService } from '#/api/installation';

import { computed } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Collapse, CollapsePanel, FormItem, Input, Tooltip } from 'ant-design-vue';

import { injectModel, INSTALL_CONFIG_MODEL } from '../shared';

/**
 * Step3 单服务配置面板：install_args + ports 逐项输入框。
 * 表单键契约：`${服务名}=${参数key}`（安装参数与端口共用一个命名空间，
 * 同一服务内 key 不重复）。后端校验失败经 argErrors 展示逐字段错误
 * （antdv4 无 setFields 注入字段错误，改为字段下方红字回显）。
 */
defineOptions({ name: 'InstallationServiceConfigItem' });

const props = defineProps<{
  /** 后端校验失败回显（键 = 参数 key，值 = 失败原因） */
  argErrors?: Record<string, string>;
  service: ConfigService;
}>();

/** 扁平表单模型（step3 provide，与外层 Form :model 同源） */
const formModel = injectModel(INSTALL_CONFIG_MODEL);

/** 安装参数在前、端口在后（旧 renderData 拼接顺序） */
const fields = computed(() => [
  ...props.service.install_args,
  ...props.service.ports,
]);
</script>

<template>
  <div class="p-2.5">
    <Collapse :bordered="false" expand-icon-position="start" default-active-key="1">
      <CollapsePanel
        :header="service.name"
        key="1"
        class="installation-config-panel bg-muted"
      >
        <div v-for="item in fields" :key="item.key" class="mt-2.5 w-[600px]">
          <FormItem
            :label="item.name"
            :name="`${service.name}=${item.key}`"
            :rules="[
              { message: `请输入${item.name}`, required: item.key !== 'vip' },
            ]"
          >
            <Input
              v-model:value="formModel[`${service.name}=${item.key}`]"
              :disabled="!item.editable"
              :placeholder="`请输入${item.name}`"
            >
              <template v-if="item.dir_key" #addonBefore>
                <span class="text-[#b1b1b1]">/ 数据分区</span>
              </template>
              <template v-if="item.dir_key" #suffix>
                <Tooltip title="数据分区：主机所设置的数据分区">
                  <IconifyIcon class="text-muted-foreground" icon="lucide:info" />
                </Tooltip>
              </template>
            </Input>
          </FormItem>
          <div v-if="argErrors?.[item.key]" class="pb-1 text-xs text-[#da4e48]">
            {{ argErrors[item.key] }}
          </div>
        </div>
      </CollapsePanel>
    </Collapse>
  </div>
</template>

<style scoped>
.installation-config-panel :deep(.ant-collapse-header) {
  font-weight: 500;
}
</style>
