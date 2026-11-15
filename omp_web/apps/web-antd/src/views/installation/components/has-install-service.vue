<script lang="ts" setup>
import { Tooltip } from 'ant-design-vue';

/**
 * 「已安装服务数」悬浮明细：展示该主机已安装的服务实例名列表。
 */
defineOptions({ name: 'InstallationHasInstallService' });

defineProps<{
  installed: { service_instance_name: string }[];
}>();
</script>

<template>
  <Tooltip color="white" :mouse-enter-delay="0.3" placement="right">
    <template #title>
      <div class="h-[330px] min-w-[300px] p-[5px] text-black/85">
        <div class="border-b border-border pb-[5px] text-[14px]">
          已选安装服务
        </div>
        <div class="h-[300px] overflow-y-auto">
          <div
            v-for="item in installed"
            :key="item.service_instance_name"
            class="pt-[5px] text-[14px]"
          >
            {{ item.service_instance_name }}
          </div>
        </div>
      </div>
    </template>
    <a><slot></slot></a>
  </Tooltip>
</template>
