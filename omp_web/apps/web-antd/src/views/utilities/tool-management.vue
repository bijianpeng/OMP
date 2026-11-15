<script lang="ts" setup>
import type { UtilitiesApi } from '#/api/utilities';

import { onMounted, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Empty, Input, Pagination, Spin } from 'ant-design-vue';
import { useRouter } from 'vue-router';

import { queryToolList } from '#/api/utilities';

defineOptions({ name: 'ToolManagement' });

const router = useRouter();

/** 工具分类枚举（与后端 ToolInfo.kind 一致） */
const kindText: Record<number, string> = {
  0: '管理工具',
  1: '检查工具',
  2: '安全工具',
  3: '其他工具',
};

/** 分类页签（旧前端仅暴露 全部/管理工具/安全工具） */
const KIND_TABS: { label: string; value: null | number }[] = [
  { label: '全部', value: null },
  { label: '管理工具', value: 0 },
  { label: '安全工具', value: 2 },
];

const loading = ref(false);
const cards = ref<UtilitiesApi.ToolCard[]>([]);
/** 「共收录 N 个实用工具」仅在无条件查询时更新（旧页契约） */
const recordTotal = ref(0);
/** 分页总数（每次查询都更新，与旧页 pagination.total 一致） */
const pageTotal = ref(0);
const activeKind = ref<null | number>(null);
const searchName = ref('');
const pagination = reactive({
  current: 1,
  // 旧页按视口高度 16/12 自适应；此处按常见视口取值，首次挂载时校正
  pageSize: 16,
});

async function fetchCards() {
  loading.value = true;
  try {
    const res = await queryToolList({
      kind: activeKind.value,
      name: searchName.value || null,
      page: pagination.current,
      size: pagination.pageSize,
    });
    cards.value = res.results;
    pageTotal.value = res.count;
    if (searchName.value === '' && activeKind.value === null) {
      recordTotal.value = res.count;
    }
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

function switchKind(kind: null | number) {
  if (activeKind.value === kind) return;
  activeKind.value = kind;
  pagination.current = 1;
  fetchCards();
}

function handleSearchChange(value: string) {
  searchName.value = value;
  // 清空输入即恢复全量（与旧页 allowClear onChange 行为一致）
  if (!value) {
    pagination.current = 1;
    fetchCards();
  }
}

function handleSearch() {
  pagination.current = 1;
  fetchCards();
}

function handlePageChange(page: number) {
  pagination.current = page;
  fetchCards();
}

function goDetail(id: number) {
  router.push(`/utilitie/tool-management/tool-management-detail/${id}`);
}

onMounted(() => {
  pagination.pageSize = window.innerHeight > 955 ? 16 : 12;
  fetchCards();
});
</script>

<template>
  <Page>
    <div class="flex flex-col gap-3">
      <div class="border-b border-border pb-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <template v-for="(tab, idx) in KIND_TABS" :key="tab.label">
              <span
                class="cursor-pointer select-none border-b-2 pb-1 text-sm"
                :class="
                  activeKind === tab.value
                    ? 'border-primary font-medium text-blue-500'
                    : 'border-transparent text-muted-foreground hover:text-blue-500'
                "
                @click="switchKind(tab.value)"
              >
                {{ tab.label }}
              </span>
              <span v-if="idx < KIND_TABS.length - 1" class="text-gray-300">
                |
              </span>
            </template>
          </div>
          <Input
            :value="searchName"
            allow-clear
            placeholder="请输入工具名称"
            :style="{ width: '280px' }"
            @change="(e: any) => handleSearchChange(e.target.value)"
            @press-enter="handleSearch"
          />
        </div>
        <div class="pt-2 text-sm text-gray-500">
          共收录 {{ recordTotal }} 个实用工具
        </div>
      </div>

      <Spin :spinning="loading">
        <div
          v-if="cards.length === 0"
          class="flex h-[400px] items-center justify-center"
        >
          <Empty description="暂无使用工具" />
        </div>
        <div v-else class="flex flex-wrap gap-[1%]">
          <div
            v-for="card in cards"
            :key="card.id"
            class="group h-[145px] w-[calc((100%-3%)/4)] cursor-pointer bg-card px-2.5 pt-1.5 shadow-sm transition-all duration-200 hover:shadow-md"
            @click="goDetail(card.id)"
          >
            <div class="flex items-center gap-2.5">
              <div
                class="flex size-[50px] shrink-0 items-center justify-center overflow-hidden rounded-full border border-border bg-muted"
              >
                <img
                  v-if="card.logo"
                  :src="`/${card.logo}`"
                  class="size-[35px]"
                  alt=""
                />
                <IconifyIcon
                  v-else
                  class="size-[35px] text-blue-400"
                  icon="lucide:wrench"
                />
              </div>
              <div
                class="flex-1 truncate text-base text-foreground group-hover:text-blue-500"
                :title="card.name"
              >
                {{ card.name }}
              </div>
            </div>
            <div class="flex items-center justify-between px-1 pt-2 text-xs">
              <span class="text-gray-500">
                [ {{ kindText[card.kind] ?? card.kind }} ]
              </span>
              <span class="text-foreground">使用次数：{{ card.used_number }}</span>
            </div>
            <p
              class="mt-1 line-clamp-2 text-[13px] leading-5 text-gray-400"
              :title="card.description ?? ''"
            >
              {{ card.description || '' }}
            </p>
          </div>
        </div>
      </Spin>

      <div v-if="cards.length > 0" class="flex justify-center pb-4 pt-1">
        <Pagination
          :current="pagination.current"
          :page-size="pagination.pageSize"
          :total="pageTotal"
          @change="handlePageChange"
        />
      </div>
    </div>
  </Page>
</template>
