<script lang="ts" setup>
import type { HostApi } from '#/api/hosts';

import { ref } from 'vue';

import { Badge, Drawer, Spin, Timeline, Tooltip } from 'ant-design-vue';
import dayjs from 'dayjs';

import { getHostDetail } from '#/api/hosts';

defineOptions({ name: 'HostDetailDrawer' });

const open = ref(false);
const loading = ref(false);
/** 行内数据（列表快照，用于基本信息即时展示） */
const record = ref<HostApi.HostRecord>();
/** 详情接口数据（基础环境 + 操作历史） */
const detail = ref<HostApi.HostDetail>();

/** 空值统一显示 -（照搬旧页 nonEmptyProcessing 语义） */
const dash = (value?: null | number | string) =>
  value === null || value === undefined || value === '' ? '-' : String(value);

const formatTime = (value?: null | string) =>
  value ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '-';

/** Agent 状态文案与分色（照搬旧页 renderStatus：0 正常 1 重启中 2 启动失败 3 部署中 4 部署失败） */
const AGENT_STATUS: Record<
  number,
  { badge: 'default' | 'error' | 'success' | 'warning'; label: string }
> = {
  0: { badge: 'success', label: '正常' },
  1: { badge: 'warning', label: '重启中' },
  2: { badge: 'error', label: '启动失败' },
  3: { badge: 'warning', label: '部署中' },
  4: { badge: 'error', label: '部署失败' },
};

/** 主机初始化状态（照搬旧页 renderInitStatue：0 成功 1 未执行 2 执行中 3 失败） */
const INIT_STATUS: Record<
  number,
  { badge: 'default' | 'error' | 'success' | 'warning'; label: string }
> = {
  0: { badge: 'success', label: '成功' },
  1: { badge: 'default', label: '未执行' },
  2: { badge: 'warning', label: '执行中' },
  3: { badge: 'error', label: '失败' },
};

/** 旧页默认组件图标（无 logo 的基础环境兜底 SVG） */
const COMPONENT_FALLBACK_SVG = `<svg t="1634633143436" class="icon" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg" width="200" height="200"><path d="M882.521 282.988L527.534 78.127c-8.98-5.219-20.146-5.219-29.127 0L143.42 282.988c-8.98 5.219-14.563 14.806-14.563 25.244v409.842c0 10.437 5.583 20.025 14.563 25.244L498.407 948.3c4.491 2.548 9.588 3.884 14.563 3.884s10.073-1.334 14.563-3.884L882.52 743.318c8.98-5.219 14.563-14.806 14.563-25.244V308.232c0-10.437-5.583-20.025-14.563-25.244zM838.83 701.326L512.971 889.438 187.112 701.326V325.101l325.859-188.112L838.83 325.101v376.225z" p-id="2389"></path><path d="M270.124 383.476c-8.01 13.957-3.277 31.797 10.681 39.807l202.676 116.994v231.439c0 16.142 12.986 29.127 29.127 29.127s29.127-12.986 29.127-29.127V540.641l203.404-117.479c13.957-8.01 18.69-25.851 10.681-39.807s-25.851-18.69-39.807-10.681L512.973 489.91l-203.04-117.236c-13.957-8.01-31.676-3.155-39.807 10.801z" p-id="2390"></path></svg>`;

async function openDrawer(row: HostApi.HostRecord) {
  record.value = row;
  detail.value = undefined;
  open.value = true;
  loading.value = true;
  try {
    detail.value = await getHostDetail(row.id);
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
    :title="`主机详情 - ${record?.ip ?? ''}`"
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
        <!-- 左列：基本信息 -->
        <div class="w-2/5 overflow-auto rounded bg-card p-5">
          <div class="pb-4 text-[15px] font-medium">基本信息</div>
          <div
            v-for="field in [
              { label: '实例名称', value: dash(record?.instance_name) },
              { label: 'HOSTNAME', value: dash(record?.host_name) },
              { label: 'IP地址', value: dash(record?.ip) },
              { label: 'SSH端口', value: dash(record?.port) },
              { label: '用户名', value: dash(record?.username) },
              { label: '系统', value: dash(record?.operate_system) },
              { label: 'CPU', value: record?.cpu == null ? '-' : `${record.cpu} c` },
              { label: '内存', value: record?.memory == null ? '-' : `${record.memory} G` },
              { label: '创建时间', value: formatTime(record?.created) },
              { label: '维护模式', value: record?.is_maintenance ? '是' : '否' },
            ]"
            :key="field.label"
            class="flex border-b border-border py-2"
          >
            <div class="w-2/5 text-left">{{ field.label }}</div>
            <div class="w-3/5 break-all text-left">{{ field.value }}</div>
          </div>
          <!-- 硬盘：多分区逐行展示（照搬旧页 disk 对象遍历） -->
          <div class="flex border-b border-border py-2">
            <div class="w-2/5 text-left">硬盘</div>
            <div class="w-3/5 text-left">
              <template v-if="record?.disk && Object.keys(record.disk).length">
                <div
                  v-for="(size, mount) in record.disk"
                  :key="mount"
                  class="flex justify-between"
                >
                  <span class="w-2/3">
                    <Tooltip :title="String(mount)">
                      <span class="block truncate">{{ mount }}</span>
                    </Tooltip>
                  </span>
                  <span class="w-1/3 text-right">{{ size }} G</span>
                </div>
              </template>
              <template v-else>-</template>
            </div>
          </div>
          <!-- 主机初始化（详情面板保留展示；badge 分色照搬旧页 renderInitStatue） -->
          <div class="flex border-b border-border py-2">
            <div class="w-2/5 text-left">主机初始化</div>
            <div class="w-3/5 text-left">
              <span
                v-if="INIT_STATUS[record?.init_status ?? -1]"
                class="inline-flex items-center gap-1.5"
              >
                <Badge
                  :status="INIT_STATUS[record?.init_status ?? -1]?.badge"
                />
                <span>{{ INIT_STATUS[record?.init_status ?? -1]?.label }}</span>
              </span>
              <template v-else>-</template>
            </div>
          </div>
        </div>

        <!-- 右列：Agent 状态 + 部署组件 + 历史记录 -->
        <div class="flex min-w-0 flex-1 flex-col">
          <div class="flex gap-5">
            <div class="w-[49%] rounded bg-card p-5">
              <div class="pb-4 text-[15px] font-medium">Agent状态</div>
              <div
                v-for="agent in [
                  { label: '主机Agent', value: record?.host_agent },
                  { label: '监控Agent', value: record?.monitor_agent },
                ]"
                :key="agent.label"
                class="flex py-3"
              >
                <div class="w-1/2">{{ agent.label }}</div>
                <div class="w-1/2">
                  <span
                    v-if="AGENT_STATUS[agent.value ?? -1]"
                    class="inline-flex items-center gap-1.5"
                  >
                    <Badge :status="AGENT_STATUS[agent.value ?? -1]?.badge" />
                    <span>{{ AGENT_STATUS[agent.value ?? -1]?.label }}</span>
                  </span>
                  <template v-else>-</template>
                </div>
              </div>
            </div>

            <div class="w-[49%] rounded bg-card p-5">
              <div class="pb-4 text-[15px] font-medium">部署组件信息</div>
              <div class="flex py-3">
                <div class="w-1/2">部署组件</div>
                <div class="w-1/2">{{ record?.service_num ?? '-' }} 个</div>
              </div>
              <div class="flex py-3">
                <div class="w-1/2">基础环境</div>
                <div class="flex min-w-0 flex-wrap flex-1 gap-1">
                  <template
                    v-if="detail?.deployment_information?.length"
                  >
                    <Tooltip
                      v-for="(item, index) in detail.deployment_information"
                      :key="`${item.service__app_name}-${index}`"
                      :title="`${item.service__app_name} ${item.service__app_version}`"
                    >
                      <!-- 后端返回的是平台自维护的 logo SVG 字符串（内网数据，照搬旧页 v-html 契约） -->
                      <span
                        class="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full border border-blue-200 p-0.5"
                        v-html="
                          item.service__app_logo || COMPONENT_FALLBACK_SVG
                        "
                      ></span>
                    </Tooltip>
                  </template>
                  <template v-else>无</template>
                </div>
              </div>
            </div>
          </div>

          <!-- 历史记录 -->
          <div class="mt-5 min-h-0 flex-1 overflow-auto rounded bg-card p-5">
            <div class="pb-4 text-[15px] font-medium">历史记录</div>
            <Timeline v-if="detail?.history?.length">
              <Timeline.Item
                v-for="(item, index) in detail.history"
                :key="`${item.id}-${index}`"
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
