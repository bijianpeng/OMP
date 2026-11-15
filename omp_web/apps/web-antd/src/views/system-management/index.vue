<script lang="ts" setup>
import { onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';

import { Card, message, Modal, Switch } from 'ant-design-vue';

import { queryMaintainState, toggleMaintainMode } from '#/api/promemonitor';

defineOptions({ name: 'SystemManagement' });

/**
 * 全局维护模式开关。
 * Switch 受控绑定 maintainOn：change 只弹确认框不改值，确认成功后重新查询
 * （服务端按「是否存在维护记录」自动翻转，前端不传目标状态）。
 * 确认框沿用 backup-record.vue 立下的 Modal.confirm 约定。
 * 旧前端顶栏消费维护模式状态的全局联动，待顶栏迁移时接入。
 */

const loading = ref(false);
const toggling = ref(false);
const maintainOn = ref(false);

async function loadState() {
  loading.value = true;
  try {
    const data = await queryMaintainState();
    maintainOn.value = (data?.length ?? 0) > 0;
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

function confirmToggle(next: boolean) {
  Modal.confirm({
    content: next ? '确定进入全局维护模式 ？' : '确定退出全局维护模式 ？',
    okText: '确定',
    cancelText: '取消',
    title: '提示',
    async onOk() {
      toggling.value = true;
      try {
        await toggleMaintainMode();
        message.success(next ? '已进入全局维护模式' : '已退出全局维护模式');
        await loadState();
      } catch {
        // 失败保留当前状态（Switch 受控，未改值自动回弹），全局拦截器已提示
      } finally {
        toggling.value = false;
      }
    },
  });
}

onMounted(() => {
  loadState();
});
</script>

<template>
  <Page>
    <div class="flex flex-col gap-4">
      <Card title="维护模式" :loading="loading">
        <div class="mb-3">
          <!-- 垂直布局（label 在上）与邮件管理页配置表单风格对齐 -->
          <div class="mb-1.5">启用</div>
          <Switch
            :checked="maintainOn"
            :loading="toggling"
            @change="confirmToggle($event)"
          />
        </div>
        <p class="m-0 max-w-[720px] text-foreground/60 text-sm">
          开启维护模式后，将暂停平台异常告警功能；此功能适用于计划性升级、变更操作期间，避免造成误报带来的影响。
        </p>
      </Card>
    </div>
  </Page>
</template>
