<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import { Check, ChevronDown } from '@vben/icons';

import { Dropdown, Menu, MenuItem, Tag } from 'ant-design-vue';

import { usePreferences } from '@vben/preferences';

import { useEnvStore } from '#/store';

defineOptions({
  name: 'EnvSwitcher',
});

const envStore = useEnvStore();
const { isDark } = usePreferences();

// envList 不持久化（store/env.ts），刷新后由本组件（顶栏首个消费者）重新拉取；
// 拉取失败保持空列表 → 切换器隐藏，错误提示由请求层统一弹出
onMounted(async () => {
  if (envStore.envList.length === 0) {
    const previousEnvId = envStore.currentEnvId;
    try {
      await envStore.fetchEnvList();
    } catch {
      return;
    }
    // 与登录流程同语义：刷新期间授权被回收/环境被删除时回落到第一项
    envStore.ensureValid();
    // 回落确实改变了环境选择时（持久化的当前环境已失效，如被他人删除），
    // 整页刷新一次让所有已加载页面按新环境重新拉数据——否则本轮页面
    // 仍在用失效的 X-Env-Id 请求，全量 403 白屏。回落后的 id 已持久化，
    // reload 后再进本组件不会再变，不会循环刷新
    if (envStore.currentEnvId !== previousEnvId) {
      window.location.reload();
    }
  }
});

/** 当前环境记录（列表未加载或 id 失效时 undefined，触发按钮 tooltip 退化为通用文案） */
const currentEnv = computed(() => envStore.currentEnv);

/**
 * 当前环境名（列表未加载或 id 失效时的兜底文案仅在 ensureValid 前瞬时闪现）。
 * 恒以醒目 Tag 展示（单环境 default 也显示，保持一致性），让用户一眼看到
 * "我在哪个环境"——这是本组件的主要存在感来源
 */
const currentEnvName = computed(() => currentEnv.value?.name ?? '未选择');

/** ant Menu 选中高亮 key（环境 id 字符串化；未选定时不高亮） */
const selectedKeys = computed(() =>
  envStore.currentEnvId === null ? [] : [String(envStore.currentEnvId)],
);

/** 触发按钮 tooltip：当前环境名称 + 编码（编码是监控链路标识，便于排查） */
const triggerTooltip = computed(() =>
  currentEnv.value
    ? `${currentEnv.value.name}（${currentEnv.value.code}）`
    : '切换环境',
);

/** 下拉展开态：仅用于旋转指示箭头，增强"可点开"暗示 */
const dropdownOpen = ref(false);

/**
 * Tag inline 样式：
 * - 清掉 .ant-tag 自带 margin-inline-end（胶囊内间距交给 gap，且 css-in-js
 *   注入晚于打包 CSS，inline style 是唯一稳定的覆盖方式）
 * - 暗色下 antd processing 预设文字色（蓝-6）在 Tag 深底上对比不足（约
 *   2.8:1），提亮到 antd 蓝-4；亮色用预设原色不动
 */
const tagStyle = computed(() => ({
  color: isDark.value ? '#69b1ff' : undefined,
  marginInlineEnd: '0',
}));

function handleMenuClick({ key }: { key: number | string }) {
  // setEnv 校验目标 id 必须在当前用户可见列表内（防未授权环境）
  if (!envStore.setEnv(Number(key))) {
    return;
  }
  // spec 决策：切换环境后整页刷新，让所有已加载页面按新环境重新拉取数据。
  // currentEnvId 持久化由 store 订阅同步写回，reload 前已完成
  window.location.reload();
}
</script>

<template>
  <!-- 无可见环境（未授权任何环境 / 列表拉取失败）时隐藏切换器 -->
  <div v-if="envStore.envList.length > 0">
    <Dropdown v-model:open="dropdownOpen" :trigger="['click']">
      <!--
        触发器为「当前环境名 Tag + 展开箭头」的胶囊按钮：
        - 不复用 VbenIconButton（固定方形仅容图标），但沿用其 icon 变体的
          token（h-8 / text-foreground/80 / hover:bg-accent / rounded-full），
          与顶栏其它部件高度对齐、风格一致，暗色模式随语义 token 自适应
        - Tag 用 antd 预设语义色 processing（蓝），随亮/暗主题自适应
          （暗色下文字提亮见 tagStyle）；间距交给 gap（清 .ant-tag 默认 margin）
      -->
      <button
        :title="triggerTooltip"
        class="focus-visible:ring-ring inline-flex h-8 items-center gap-1 rounded-full px-2 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-1 focus-visible:outline-none"
        type="button"
      >
        <Tag
          color="processing"
          :bordered="false"
          :style="tagStyle"
        >
          {{ currentEnvName }}
        </Tag>
        <ChevronDown
          :class="dropdownOpen ? 'rotate-180' : ''"
          class="text-foreground/60 size-3.5 shrink-0 transition-transform duration-200"
        />
      </button>
      <template #overlay>
        <Menu :selected-keys="selectedKeys" @click="handleMenuClick">
          <MenuItem v-for="env in envStore.envList" :key="String(env.id)">
            <span class="flex items-center gap-2">
              <!-- 选中项打勾；占位 span 保证各选项文字对齐 -->
              <Check
                v-if="env.id === envStore.currentEnvId"
                class="size-3.5"
              />
              <span v-else class="inline-block size-3.5"></span>
              <span>{{ env.name }}</span>
              <span class="text-foreground/50 text-xs">{{ env.code }}</span>
            </span>
          </MenuItem>
        </Menu>
      </template>
    </Dropdown>
  </div>
</template>
