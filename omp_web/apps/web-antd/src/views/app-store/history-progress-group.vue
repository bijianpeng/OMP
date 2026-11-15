<script lang="ts" setup>
import { nextTick, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

/**
 * 升级/回滚进度分组卡片（旧 UpgradeInfoItem/RollbackInfoItem +
 * UpgradeDetail/RollbackDetail 四组件的合并等价物）：服务名区块标题 +
 * 各主机实例明细行（状态色文字 + 可展开的黑底日志面板，日志更新滚到底）。
 * 明细行展开各自独立（旧实现行内自持 openName，无互斥）。
 * 与批 K/L 同构组件保持本地副本惯例（跨批次目录不互相依赖）。
 */
defineOptions({ name: 'AppStoreHistoryProgressGroup' });

const props = defineProps<{
  /** 锚点 id（右侧导航滚动定位，旧 a{idx} 契约） */
  anchorId: string;
  items: ProgressDetailItem[];
  kind: 'rollback' | 'upgrade';
  title: string;
}>();

/** 归一后的明细行（页面将 upgrade_state/rollback_state 归一为 state） */
interface ProgressDetailItem {
  instance_name: string;
  message: null | string;
  state: number;
}

/** 明细行状态渲染规则（旧 UpgradeDetail/RollbackDetail 色值契约） */
const STATUS_TEXT: Record<string, Record<number, { color: string; text: string }>> = {
  rollback: {
    0: { color: '#f0c242', text: '等待回滚' },
    1: { color: 'rgba(0, 0, 0, 0.85)', text: '正在回滚' },
    2: { color: 'rgb(118, 204, 104)', text: '回滚成功' },
    3: { color: '#da4e48', text: '回滚失败' },
    4: { color: 'rgba(0, 0, 0, 0.45)', text: '正在注册' },
  },
  upgrade: {
    0: { color: '#f0c242', text: '等待升级' },
    1: { color: 'rgba(0, 0, 0, 0.85)', text: '正在升级' },
    2: { color: 'rgb(118, 204, 104)', text: '升级成功' },
    3: { color: '#da4e48', text: '升级失败' },
    4: { color: 'rgba(0, 0, 0, 0.45)', text: '正在注册' },
  },
};

/** 各行独立展开态（键 `${instance_name}=${ip}`，对齐旧 openName 契约） */
const openKeys = ref<Set<string>>(new Set());

function toggle(key: string) {
  const next = new Set(openKeys.value);
  if (next.has(key)) {
    next.delete(key);
  } else {
    next.add(key);
  }
  openKeys.value = next;
}

function isOpen(key: string) {
  return openKeys.value.has(key);
}

/** 展开面板 ref 集合（键 → 元素，日志更新滚到底） */
const logRefs = new Map<string, HTMLElement>();

function setLogRef(key: string, el: any) {
  if (el) logRefs.set(key, el as HTMLElement);
  else logRefs.delete(key);
}

// 任一展开面板日志变化时滚到底部（旧 scrollTop=scrollHeight 契约）
watch(
  () => props.items.map((item) => item.message).join('\n'),
  async () => {
    await nextTick();
    for (const key of openKeys.value) {
      const el = logRefs.get(key);
      if (el) el.scrollTop = el.scrollHeight;
    }
  },
);
</script>

<template>
  <div :id="anchorId" class="mt-4 bg-card p-2.5 first:mt-0">
    <!-- 区块标题：悬浮文字 + 贯穿分隔线（旧标题条契约） -->
    <div class="relative flex h-[30px] w-full items-center">
      <div class="absolute left-[30px] bg-card px-5 font-medium">{{ title }}</div>
      <div class="h-px w-full bg-[#b3b2b3]"></div>
    </div>

    <div class="mt-2.5 pb-1 pl-5">
      <div
        v-for="item in items"
        :key="`${title}=${item.instance_name}`"
        class="p-2.5"
      >
        <div class="flex justify-between">
          <div class="min-w-0 flex-1">
            <span :title="item.instance_name">{{ item.instance_name }}</span>
          </div>
          <div
            class="w-[90px] shrink-0 whitespace-nowrap"
            :style="{
              color: STATUS_TEXT[kind]?.[item.state]?.color,
            }"
          >
            {{ STATUS_TEXT[kind]?.[item.state]?.text ?? item.state }}
          </div>
          <div class="shrink-0 pr-[50px] text-right">
            <a
              class="flex cursor-pointer select-none items-center text-[13px]"
              @click="toggle(`${title}=${item.instance_name}`)"
            >
              查看详细{{ kind === 'upgrade' ? '升级' : '回滚' }}信息
              <IconifyIcon
                icon="lucide:chevron-down"
                class="relative ml-1 transition-transform"
                :class="
                  isOpen(`${title}=${item.instance_name}`)
                    ? '-translate-y-px rotate-180'
                    : 'translate-y-px'
                "
              />
            </a>
          </div>
        </div>
        <!-- 展开日志面板：黑底白字 300px 自滚动（旧 stepOpen 契约） -->
        <div
          class="grid transition-all duration-200 ease-in"
          :class="
            isOpen(`${title}=${item.instance_name}`)
              ? 'mt-2.5 grid-rows-[1fr]'
              : 'grid-rows-[0fr]'
          "
        >
          <div
            class="overflow-hidden"
            :class="isOpen(`${title}=${item.instance_name}`) ? '' : 'invisible'"
          >
            <div
              :ref="(el: any) => setLogRef(`${title}=${item.instance_name}`, el)"
              class="max-h-[300px] min-h-[30px] overflow-y-auto whitespace-pre-line bg-black p-2.5 text-white"
            >
              {{ item.message || '暂无数据' }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
