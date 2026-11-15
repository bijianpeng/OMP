<script lang="ts" setup>
import { computed, shallowRef } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Button, Steps, Tooltip } from 'ant-design-vue';

import { useInstallationStore } from '#/store/installation';

import Step1Basic from './step1-basic.vue';
import Step2Distribution from './step2-distribution.vue';
import Step3Config from './step3-config.vue';
import Step4Process from './step4-process.vue';

/**
 * 批量安装向导（/application_management/app_store/installation）。
 * 四步编排：基本信息 → 服务分布 → 修改配置 → 开始安装。
 *
 * 进入契约：
 * - 应用商店批量安装/组件安装选择弹窗（批 K）写 store（uniqueKey + step1Data）
 *   后跳本页，从 Step1 开始；
 * - 执行记录页/部署模板导入跳 `?step=3&uniqueKey=` 直落进度步（旧
 *   location.state 语义的 query 透传），uniqueKey 以 query 为准。
 */
defineOptions({ name: 'Installation' });

const route = useRoute();
const router = useRouter();

const store = useInstallationStore();

/** 初始步骤（query 透传，0-3 越界回落 0，旧 location.state?.step 契约） */
const stepNum = shallowRef(clampStep(Number(route.query.step ?? 0)));

/** 流程唯一键：query 直跳优先（进度步消费），否则取入口交接值 */
const uniqueKey = computed(() => {
  const queryKey = route.query.uniqueKey;
  if (typeof queryKey === 'string' && queryKey) {
    return queryKey;
  }
  return store.uniqueKey;
});

function clampStep(value: number) {
  return Number.isInteger(value) && value >= 0 && value <= 3 ? value : 0;
}

function goBack() {
  router.back();
}
</script>

<template>
  <!-- 满高纵向布局：顶条/内容/底部操作条分区，内容区内部滚动（页面无滚动条） -->
  <Page content-class="flex min-h-0 flex-col overflow-hidden">
    <!-- 顶部导航条：返回 + 标题 + 步骤条 -->
    <div
      class="flex h-[50px] shrink-0 items-center justify-between bg-card pl-5 pr-[50px]"
    >
      <div class="flex shrink-0 items-center text-base">
        <Tooltip title="返回">
          <Button
            class="border-0 bg-transparent px-1 shadow-none"
            size="small"
            @click="goBack"
          >
            <template #icon>
              <IconifyIcon class="text-base" icon="lucide:arrow-left" />
            </template>
          </Button>
        </Tooltip>
        <span class="whitespace-nowrap pl-3">安装</span>
      </div>
      <!-- antdv Steps 根元素自带无层级 width:100%（压过 Tailwind 分层工具类），宽度需内联指定 -->
      <Steps
        :current="stepNum"
        :style="{ width: '600px', minWidth: 0 }"
        size="small"
      >
        <Steps.Step title="基本信息" />
        <Steps.Step title="服务分布" />
        <Steps.Step title="修改配置" />
        <Steps.Step title="开始安装" />
      </Steps>
      <div class="w-[40px]"></div>
    </div>

    <Step1Basic
      v-if="stepNum === 0"
      :unique-key="uniqueKey"
      @next="stepNum = 1"
    />
    <Step2Distribution
      v-else-if="stepNum === 1"
      :unique-key="uniqueKey"
      @next="stepNum = 2"
      @prev="stepNum = 0"
    />
    <Step3Config
      v-else-if="stepNum === 2"
      :unique-key="uniqueKey"
      @next="stepNum = 3"
      @prev="stepNum = 1"
    />
    <Step4Process v-else :unique-key="uniqueKey" />
  </Page>
</template>
