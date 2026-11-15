<script lang="ts" setup>
import { ref, watch } from 'vue';

import { Checkbox, Modal } from 'ant-design-vue';

defineOptions({ name: 'ServiceActionModal' });

const props = defineProps<{
  /** 删除依赖提示语（后端纯文本解析），仅删除操作展示 */
  deleteMsg: null | { items: string[]; key: string };
  loading: boolean;
  /** 操作码 1/2/3/4 */
  operate: number;
  /** batch-勾选批量 single-行内单个 */
  scope: 'batch' | 'single';
  /** 目标服务数（batch 时展示） */
  targetCount: number;
}>();

const emit = defineEmits<{
  confirm: [delFile: boolean];
  'update:open': [open: boolean];
}>();

/** 服务操作：1-启动 2-停止 3-重启 4-删除（确认文案与旧页 operateObj 一致） */
const OPERATE_TEXT: Record<number, string> = {
  1: '启动',
  2: '停止',
  3: '重启',
  4: '删除',
};

const open = defineModel<boolean>('open', { default: false });

/** 同时卸载服务（旧页 deleteDimension，默认勾选） */
const deleteWithUninstall = ref(true);

// 每次打开重置勾选状态（旧页打开删除确认时 setDeleteDimension(true) 同语义）
watch(open, (val) => {
  if (val) deleteWithUninstall.value = true;
});

/** 依赖列表展开/收起（默认展示前 6 条，照搬旧页 ExpandCollapseMsg） */
const MSG_PREVIEW_COUNT = 6;
const msgExpanded = ref(false);
watch(open, (val) => {
  if (val) msgExpanded.value = false;
});

function handleOk() {
  emit('confirm', deleteWithUninstall.value);
}
</script>

<template>
  <Modal
    :confirm-loading="loading"
    :open="open"
    title="提示"
    :width="520"
    cancel-text="取消"
    destroy-on-close
    ok-text="确定"
    @cancel="open = false"
    @ok="handleOk"
  >
    <div class="py-4">
      <template v-if="scope === 'batch'">
        确定要对
        <span class="font-medium"> {{ targetCount }} </span>
        个 服务下发
        <span class="font-medium"> {{ OPERATE_TEXT[operate] ?? '' }} </span>
        操作？
      </template>
      <template v-else>
        确定要对
        <span class="font-medium">当前</span> 服务下发
        <span class="font-medium">{{ OPERATE_TEXT[operate] ?? '' }}</span>
        操作？
      </template>

      <template v-if="operate === 4 && deleteMsg">
        <div class="pt-4">
          <div>{{ deleteMsg.key }}</div>
          <div class="max-h-60 overflow-auto">
            <template v-if="msgExpanded">
              <div v-for="item in deleteMsg.items" :key="item">
                {{ item }}
              </div>
              <a @click="msgExpanded = false">收起</a>
            </template>
            <template v-else>
              <div
                v-for="item in deleteMsg.items.slice(0, MSG_PREVIEW_COUNT)"
                :key="item"
              >
                {{ item }}
              </div>
              <a
                v-if="deleteMsg.items.length > MSG_PREVIEW_COUNT"
                @click="msgExpanded = true"
              >
                ...展开
              </a>
            </template>
          </div>
        </div>
        <div class="pt-4">
          <Checkbox v-model:checked="deleteWithUninstall">
            <span class="text-sm">同时卸载服务</span>
          </Checkbox>
        </div>
      </template>
    </div>
  </Modal>
</template>
