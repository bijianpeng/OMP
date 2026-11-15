<script lang="ts" setup>
import { Modal } from 'ant-design-vue';

defineOptions({ name: 'HostActionModal' });

const props = defineProps<{
  /**
   * 确认文案句式：
   * agent——确定要重启 N台 主机 主机Agent？
   * maintain-batch——确定要对 N台 主机下发 开启维护模式 操作？
   * maintain-single——确定要对 当前 主机下发 关闭维护模式 操作？
   * command——确定要对 N台 主机 执行删除命令？
   */
  kind: 'agent' | 'command' | 'maintain-batch' | 'maintain-single';
  /** 动作词：重启/重装、开启维护模式/关闭维护模式、执行初始化/执行删除命令 */
  action: string;
  /** agent 句式的操作对象：主机Agent/监控Agent */
  target?: string;
  /** 目标主机数（maintain-single 句式展示「当前」） */
  count?: number;
  /** 任务下发中 */
  loading?: boolean;
}>();

const emit = defineEmits<{
  confirm: [];
  'update:open': [open: boolean];
}>();

const open = defineModel<boolean>('open', { default: false });

function handleOk() {
  emit('confirm');
}
// props 仅模板消费，避免 lint 误报未使用
void props;
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
      <template v-if="kind === 'agent'">
        确定要
        <span class="font-medium">{{ action }}</span>
        <span class="font-medium"> {{ count ?? 0 }}台 </span>
        主机
        <span class="font-medium">{{ target }}</span> ？
      </template>
      <template v-else-if="kind === 'maintain-batch'">
        确定要对
        <span class="font-medium"> {{ count ?? 0 }}台 </span>
        主机下发
        <span class="font-medium">{{ action }}</span>
        操作？
      </template>
      <template v-else-if="kind === 'maintain-single'">
        确定要对
        <span class="font-medium">当前</span>
        主机下发
        <span class="font-medium">{{ action }}</span>
        操作？
      </template>
      <template v-else>
        确定要对
        <span class="font-medium"> {{ count ?? 0 }}台 </span>
        主机
        <span class="font-medium">{{ action }}</span> ？
      </template>
    </div>
  </Modal>
</template>
