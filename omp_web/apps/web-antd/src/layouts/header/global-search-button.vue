<script setup lang="ts">
import { useTemplateRef } from 'vue';

import { Search } from '@vben/icons';
import { $t } from '@vben/locales';
import { GlobalSearch } from '@vben/layouts';
import { usePreferences } from '@vben/preferences';
import { useAccessStore } from '@vben/stores';

defineOptions({
  name: 'GlobalSearchButton',
});

const accessStore = useAccessStore();
const { globalSearchShortcutKey } = usePreferences();

/**
 * 隐藏形态的 GlobalSearch：show-button=false 时不渲染默认的输入框触发器，
 * 仅保留搜索弹窗与 Ctrl+K / Cmd+K 快捷键（均在组件内部），由下方图标按钮
 * 经 defineExpose 的 open() 唤起——与共享包 user-dropdown 内置用法同构
 */
const refGlobalSearch = useTemplateRef('refGlobalSearch');
</script>

<template>
  <!--
    顶栏全局搜索改为纯图标按钮（用户验收反馈：输入框形态占宽，收成图标更紧凑）。
    触发按钮沿用环境切换器（env-switcher）的胶囊 token：h-8 / rounded-full /
    text-foreground/80 / hover:bg-accent，与顶栏其它部件高度对齐；外层 mr-1
    与 header 内置部件（preferences/notification 等）的统一间距保持一致
    （原 mr-1 sm:mr-4 抄自内置 GlobalSearch 默认 class，sm 以上 16px 与
    相邻部件的 4px 不一致——间距不一致的根因）
  -->
  <div class="mr-1 flex items-center">
    <GlobalSearch
      ref="refGlobalSearch"
      :enable-shortcut-key="globalSearchShortcutKey"
      :menus="accessStore.accessMenus"
      :show-button="false"
    />
    <button
      :aria-label="$t('ui.widgets.search.title')"
      :title="$t('ui.widgets.search.title')"
      class="focus-visible:ring-ring inline-flex h-8 items-center justify-center rounded-full p-2 text-foreground/80 transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-1 focus-visible:outline-none"
      type="button"
      @click="refGlobalSearch?.open()"
    >
      <Search class="size-4" />
    </button>
  </div>
</template>
