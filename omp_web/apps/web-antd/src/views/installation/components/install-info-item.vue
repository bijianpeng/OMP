<script lang="ts" setup>
import type { InstallationApi } from '#/api/installation';

import InstallDetail from './install-detail.vue';
import SectionTitle from './section-title.vue';

/**
 * Step4 单应用安装分组卡片：应用名区块标题 + 该应用各主机的安装明细行。
 * 外层 div 承载锚点 id（右侧导航滚动定位）。
 */
defineOptions({ name: 'InstallationInstallInfoItem' });

defineProps<{
  /** 日志内容（当前展开项的，父级轮询下发） */
  log: string;
  /** 当前展开的日志面板键 `${应用名}=${ip}` */
  openName: string;
  title: string;
  items: InstallationApi.ProcessDetailItem[];
}>();

const emit = defineEmits<{ toggleOpen: [name: string] }>();
</script>

<template>
  <div :id="`a${title}`" class="mt-4 bg-card p-2.5 first:mt-0">
    <div class="pt-2.5">
      <SectionTitle :title="title" />
    </div>
    <div class="mt-2.5 pb-1 pl-5">
      <InstallDetail
        v-for="item in items"
        :key="`${title}=${item.ip}`"
        :ip="item.ip"
        :log="openName === `${title}=${item.ip}` ? log : ''"
        :open="openName === `${title}=${item.ip}`"
        :status="item.status"
        @toggle="emit('toggleOpen', `${title}=${item.ip}`)"
      />
    </div>
  </div>
</template>
