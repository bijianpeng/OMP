<script lang="ts" setup>
import type { UtilitiesApi } from '#/api/utilities';

import { computed, h, onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Button, Spin, Table, Tooltip } from 'ant-design-vue';
import { useRoute, useRouter } from 'vue-router';

import { queryToolDetail } from '#/api/utilities';
import { renderMarkdown } from '#/utils/markdown';

defineOptions({ name: 'ToolDetails' });

const route = useRoute();
const router = useRouter();

/** 工具分类枚举 */
const kindText: Record<number, string> = {
  0: '管理工具',
  1: '检查工具',
  2: '安全工具',
  3: '其他工具',
};

/** 脚本参数类型枚举 */
const argTypeText: Record<string, string> = {
  file: '文件',
  input: '单行文本',
  select: '单选',
};

const loading = ref(false);
const info = ref<UtilitiesApi.ToolDetail>();

/** 下载链接统一补根路径前缀（tar_url / template sub_url 为相对路径） */
function download(url: string) {
  const fileName = url.split('/').pop() ?? url;
  const link = document.createElement('a');
  link.href = `/${url}`;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
}

const argColumns = [
  { title: '名称', dataIndex: 'name', key: 'name', align: 'center' as const },
  {
    title: '类型',
    dataIndex: 'type',
    key: 'type',
    align: 'center' as const,
    customRender: ({ text }: { text: string }) => text ? argTypeText[text] ?? text : '-',
  },
  {
    title: '默认值',
    dataIndex: 'default',
    key: 'default',
    align: 'center' as const,
    customRender: ({ text }: { text: any }) =>
      typeof text === 'object' && text !== null ? '-' : text || '-',
  },
  {
    title: '必填字段',
    dataIndex: 'required',
    key: 'required',
    align: 'center' as const,
    customRender: ({ text }: { text: boolean }) => (text ? '是' : '否'),
  },
];

const templateColumns = [
  { title: '名称', dataIndex: 'name', key: 'name', align: 'center' as const, width: 300 },
  {
    title: '操作',
    dataIndex: 'sub_url',
    key: 'sub_url',
    align: 'center' as const,
    width: 100,
    customRender: ({ record }: { record: { sub_url: string } }) =>
      h('a', { onClick: () => download(record.sub_url) }, '下载'),
  },
];

const readmeHtml = computed(() => renderMarkdown(info.value?.readme_info));

async function queryInfo() {
  loading.value = true;
  try {
    info.value = await queryToolDetail(route.params.id as string);
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

function goBack() {
  router.back();
}

/** 跳转工具执行页 */
function goExecution() {
  router.push(`/utilitie/tool-management/tool-execution/${route.params.id}`);
}

onMounted(() => {
  queryInfo();
});
</script>

<template>
  <Page>
    <Spin :spinning="loading">
      <div class="flex gap-4 border-b border-border pb-4">
        <div
          class="flex size-[80px] shrink-0 items-center justify-center overflow-hidden bg-muted"
        >
          <img
            v-if="info?.logo"
            :src="`/${info.logo}`"
            class="size-[65px]"
            alt=""
          />
          <IconifyIcon v-else class="size-[65px] text-blue-400" icon="lucide:wrench" />
        </div>
        <div class="min-w-0 flex-1">
          <div class="text-lg font-medium text-foreground">
            {{ info?.name || '-' }}
          </div>
          <div class="pt-1 text-sm text-gray-400">
            {{ info?.description || '-' }}
          </div>
          <div class="flex gap-4 pt-2">
            <Button type="primary" @click="goExecution">
              执行
            </Button>
            <Button
              v-if="info?.tar_url"
              @click="download(info.tar_url)"
            >
              下载
            </Button>
          </div>
        </div>
        <div class="shrink-0 self-start">
          <Button @click="goBack">返回</Button>
        </div>
      </div>

      <div class="mt-4 flex gap-10 pb-2 text-sm">
        <div class="flex items-center gap-2">
          <span class="text-gray-500">工具类别</span>
          <span>{{ info ? kindText[info.kind] ?? info.kind : '-' }}</span>
        </div>
        <div class="flex items-center gap-2">
          <Tooltip
            placement="right"
            title="实用工具操作的目标对象类型，可以是主机或者具体服务"
          >
            <span class="text-gray-500">
              执行对象
              <IconifyIcon class="inline align-[-2px]" icon="lucide:circle-help" />
            </span>
          </Tooltip>
          <span>
            {{
              info
                ? info.target_name === 'host'
                  ? '主机'
                  : info.target_name
                : '-'
            }}
          </span>
        </div>
      </div>

      <div class="mt-2">
        <div class="border-b border-border pb-1 text-base text-foreground">
          执行参数
        </div>
        <div class="mt-2 border border-border">
          <Table
            :columns="argColumns"
            :data-source="info?.script_args ?? []"
            :loading="loading"
            :pagination="false"
            row-key="key"
            size="middle"
          />
        </div>
      </div>

      <div v-if="info?.templates?.length" class="mt-4">
        <div class="border-b border-border pb-1 text-base text-foreground">
          下载示例文件
        </div>
        <div class="mt-2 border border-border">
          <Table
            :columns="templateColumns"
            :data-source="info.templates"
            :pagination="false"
            row-key="name"
            size="middle"
          />
        </div>
      </div>

      <div class="mt-4">
        <div class="flex items-center gap-2 text-base">
          <IconifyIcon class="text-blue-500" icon="lucide:file-text" />
          <span class="text-foreground">README.md</span>
        </div>
        <div
          class="mt-2 border border-border bg-card p-5 text-sm leading-6 text-foreground [&_.md-code]:overflow-auto [&_.md-code]:bg-gray-950 [&_.md-code]:p-3 [&_.md-code]:text-gray-100 [&_.md-hr]:my-3 [&_.md-hr]:border-border [&_.md-h1]:text-xl [&_.md-h2]:text-lg [&_.md-h3]:text-base [&_.md-h4]:text-sm [&_.md-list]:my-2 [&_.md-list_.md-list]:my-0.5 [&_.md-list]:list-inside [&_.md-list]:list-disc [&_.md-list_ol.md-list]:list-decimal [&_.md-p]:my-1.5 [&_.md-quote]:my-2 [&_.md-quote]:border-l-4 [&_.md-quote]:border-border [&_.md-quote]:pl-3 [&_.md-quote]:text-gray-500 [&_.md-table]:w-full [&_.md-table_td]:border [&_.md-table_td]:border-border [&_.md-table_td]:px-2 [&_.md-table_td]:py-1 [&_.md-table_th]:border [&_.md-table_th]:border-border [&_.md-table_th]:bg-muted [&_.md-table_th]:px-2 [&_.md-table_th]:py-1 [&_.md-inline-code]:rounded [&_.md-inline-code]:bg-muted [&_.md-inline-code]:px-1"
          v-html="readmeHtml"
        />
      </div>
    </Spin>
  </Page>
</template>
