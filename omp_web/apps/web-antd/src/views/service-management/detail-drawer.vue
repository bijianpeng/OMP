<script lang="ts" setup>
import type { ServiceApi } from '#/api/services';

import { ref } from 'vue';

import { Badge, Drawer, Spin, Timeline } from 'ant-design-vue';
import dayjs from 'dayjs';

import { getServiceDetail } from '#/api/services';

defineOptions({ name: 'ServiceDetailDrawer' });

const emit = defineEmits<{ viewInstallLog: [id: number] }>();

const open = ref(false);
const loading = ref(false);
/** 行内数据（列表快照，用于基本信息即时展示） */
const record = ref<ServiceApi.ServiceRecord>();
/** 详情接口数据（安装信息 + 操作历史） */
const detail = ref<ServiceApi.ServiceDetail>();

/** 空值统一显示 -（照搬旧页 nonEmptyProcessing 语义） */
const dash = (value?: null | number | string) =>
  value === null || value === undefined || value === '' ? '-' : String(value);

const formatTime = (value?: null | string) =>
  value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';

async function openDrawer(row: ServiceApi.ServiceRecord) {
  record.value = row;
  detail.value = undefined;
  open.value = true;
  loading.value = true;
  try {
    detail.value = await getServiceDetail(row.id);
  } catch {
    // 全局拦截器已提示错误信息；抽屉保留列表行数据
  } finally {
    loading.value = false;
  }
}

defineExpose({ open: openDrawer });
</script>

<template>
  <Drawer
    :open="open"
    :title="`服务详情 - ${record?.service_instance_name ?? ''}`"
    width="calc(100% - 200px)"
    destroy-on-close
    placement="right"
    :body-style="{ padding: 0 }"
    :header-style="{ background: 'hsl(var(--background-deep))' }"
    @close="open = false"
  >
    <Spin :spinning="loading" class="block h-full">
      <!-- 抽屉内容区铺页面级底色，让白卡片（bg-card）在浅色下浮起有层次 -->
      <div class="flex h-full gap-5 bg-background-deep p-6">
        <!-- 左列：基本信息 + 安装信息 -->
        <div class="flex w-2/5 flex-col gap-5">
          <div class="flex-1 overflow-auto rounded bg-card p-5">
            <div class="pb-4 text-[15px] font-medium">基本信息</div>
            <div
              v-for="field in [
                { label: '实例名称', value: dash(record?.service_instance_name) },
                { label: '服务名称', value: dash(record?.app_name) },
                { label: '版本', value: dash(record?.app_version) },
                { label: '服务分类', value: dash(record?.label_name) },
                { label: '集群模式', value: dash(record?.cluster_type) },
                { label: 'IP地址', value: dash(record?.ip) },
              ]"
              :key="field.label"
              class="flex border-b border-border py-2"
            >
              <div class="w-2/5 text-left">{{ field.label }}</div>
              <div class="w-3/5 text-left">{{ field.value }}</div>
            </div>
          </div>

          <div class="flex-1 overflow-auto rounded bg-card p-5">
            <div
              class="flex items-center justify-between pb-4 text-[15px] font-medium"
            >
              安装信息
              <a
                class="text-[13px] font-normal"
                @click="detail && emit('viewInstallLog', detail.id)"
              >
                查看安装记录
              </a>
            </div>
            <div
              v-for="field in [
                { label: '安装目录', value: dash(detail?.install_info?.base_dir) },
                { label: '数据目录', value: dash(detail?.install_info?.data_dir) },
                { label: '日志目录', value: dash(detail?.install_info?.log_dir) },
                { label: '端口号', value: dash(detail?.install_info?.service_port) },
                { label: '用户名', value: dash(detail?.install_info?.username) },
                { label: '密码', value: dash(detail?.install_info?.password) },
                { label: '安装时间', value: formatTime(detail?.created) },
              ]"
              :key="field.label"
              class="flex border-b border-border py-2"
            >
              <div class="w-2/5 text-left">{{ field.label }}</div>
              <div class="w-3/5 break-all text-left">{{ field.value }}</div>
            </div>
          </div>
        </div>

        <!-- 右列：历史记录（self-start 收缩内容高，避免空态被等高拉伸出大片留白） -->
        <div class="max-h-full flex-1 self-start overflow-auto rounded bg-card p-5">
          <div class="pb-5 text-[15px] font-medium">历史记录</div>
          <Timeline v-if="detail?.history?.length">
            <Timeline.Item
              v-for="(item, index) in detail.history"
              :key="`${item.created}-${index}`"
            >
              <template #dot>
                <Badge
                  :status="item.result === 'success' ? 'success' : 'error'"
                />
              </template>
              <p class="text-gray-500">
                [{{ item.username }}] {{ item.description }}
              </p>
              <p class="text-gray-500">{{ formatTime(item.created) }}</p>
            </Timeline.Item>
          </Timeline>
          <div v-else class="text-gray-400">暂无历史记录</div>
        </div>
      </div>
    </Spin>
  </Drawer>
</template>

<style scoped>
/* antdv Spin 不透传 class（模板里的 h-full 到不了根），且内层容器高度
   auto 会阻断高度链（双栏 h-full + 卡片 flex-1 内滚的满高布局失效，
   抽屉出纵向滚动条）。根元素自带本组件 scope id，直接类选择器置满高；
   内层容器经 :deep 贯通之（其祖先即带 scope id 的根，可命中） */
.ant-spin-nested-loading {
  height: 100%;
}
:deep(.ant-spin-container) {
  height: 100%;
}
</style>
