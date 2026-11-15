<script lang="ts" setup>
import type { AppStoreApi } from '#/api/app-store';

import { computed } from 'vue';
import { useRouter } from 'vue-router';

defineOptions({ name: 'AppStoreCard' });

const props = defineProps<{
  info: AppStoreApi.StoreCard;
  tabKey: 'component' | 'service';
}>();

const emit = defineEmits<{ install: [] }>();

const router = useRouter();

/** 组件/服务字段前缀映射（旧 card.js nameObj 契约） */
const field = computed(() =>
  props.tabKey === 'component'
    ? {
        description: 'app_description' as const,
        logo: 'app_logo' as const,
        name: 'app_name' as const,
        version: 'app_version' as const,
      }
    : {
        description: 'pro_description' as const,
        logo: 'pro_logo' as const,
        name: 'pro_name' as const,
        version: 'pro_version' as const,
      },
);

const name = computed(() => String(props.info[field.value.name] ?? ''));
const version = computed(() => String(props.info[field.value.version] ?? ''));
const description = computed(() =>
  String(props.info[field.value.description] ?? ''),
);
/** logo 为后端下发的 SVG 字符串（v-html 渲染，同旧前端 dangerouslySetInnerHTML） */
const logo = computed(() => props.info[field.value.logo]);
/** logo 缺失时的首字母占位 */
const initial = computed(() => name.value.charAt(0).toUpperCase());

function goDetail() {
  router.push(
    `/application_management/app_store/app-${props.tabKey}-detail/${encodeURIComponent(name.value)}/${encodeURIComponent(version.value)}`,
  );
}

/**
 * 卡片「安装」入口跳转安装页（安装编排属后续批次，
 * 先按详情页「安装」按钮同款 path+params 契约跳转占位路由）
 */
function goInstall() {
  emit('install');
  const url =
    props.tabKey === 'component'
      ? '/application_management/app_store/component_installation'
      : '/application_management/app_store/application_installation';
  router.push(`${url}/${encodeURIComponent(name.value)}`);
}
</script>

<template>
  <div
    class="group flex h-[200px] w-[calc((100%-3%)/4)] cursor-pointer flex-col bg-card shadow-sm transition-all duration-200 hover:shadow-md"
  >
    <div class="flex min-h-0 flex-1 pt-2.5">
      <div class="w-20 shrink-0 pt-2.5">
        <!-- logo 容器固定浅底（功能性画布）：后端 logo 素材底色不一（部分黑底），深色主题下需浅衬底保证可辨 -->
        <div
          v-if="logo"
          class="mx-auto flex size-[50px] items-center justify-center overflow-hidden rounded-full border border-[#a8d0f8] bg-white [&>svg]:size-[30px]"
          v-html="logo"
        ></div>
        <div
          v-else
          class="mx-auto flex size-[50px] items-center justify-center rounded-full bg-gradient-to-r from-[#4f85f6] to-[#669aee] text-xl text-white"
        >
          {{ initial }}
        </div>
      </div>
      <div
        class="relative min-w-0 flex-1 pr-2.5 text-[13px] text-muted-foreground"
        @click="goDetail"
      >
        <div
          class="truncate text-sm text-foreground group-hover:text-[#247fe6]"
          :title="name"
        >
          {{ name }}
        </div>
        <div class="flex items-center justify-between px-2.5 pb-2.5 pt-2 text-xs">
          <span class="shrink-0">最新版本</span>
          <span class="truncate pl-2" :title="version">{{ version }}</span>
        </div>
        <p class="line-clamp-2 text-xs leading-5" :title="description">
          {{ description }}
        </p>
        <span class="absolute bottom-1.5 right-2.5 text-xs">
          已安装{{ info.instance_number ?? 0 }}个实例
        </span>
      </div>
    </div>
    <div class="flex border-t border-border text-[13px] leading-[48px]">
      <div
        class="w-1/2 text-center text-foreground hover:text-[#247fe6]"
        @click="goDetail"
      >
        查看
      </div>
      <div
        class="w-1/2 border-l border-border text-center text-foreground hover:text-[#247fe6]"
        @click="goInstall"
      >
        安装
      </div>
    </div>
  </div>
</template>
