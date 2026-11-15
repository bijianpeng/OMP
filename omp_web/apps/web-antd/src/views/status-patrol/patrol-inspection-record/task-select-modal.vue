<script lang="ts" setup>
import { computed, shallowRef, watch } from 'vue';

import { Checkbox, CheckboxGroup, Modal } from 'ant-design-vue';

defineOptions({ name: 'InspectionTaskSelectModal' });

const props = defineProps<{
  /** 提交中的 loading（确认按钮转圈） */
  confirmLoading?: boolean;
  /** 勾选项（主机巡检为 IP 列表，组件巡检为组件列表） */
  options: Array<{ label: string; value: number | string }>;
  title: string;
}>();

const emit = defineEmits<{
  confirm: [values: Array<number | string>];
}>();

/** 弹窗开关（父组件 v-model:open 控制） */
const open = defineModel<boolean>('open', { default: false });

/** 勾选值；弹窗关闭时清空（对齐旧弹窗 afterClose 语义） */
const checkedValues = shallowRef<Array<number | string>>([]);
watch(open, (value) => {
  if (!value) {
    checkedValues.value = [];
  }
});

/** 全选（含半选态，对齐旧弹窗 indeterminate 逻辑） */
const allChecked = computed({
  get: () =>
    props.options.length > 0 &&
    checkedValues.value.length === props.options.length,
  set: (value: boolean) => {
    checkedValues.value = value ? props.options.map((item) => item.value) : [];
  },
});
const indeterminate = computed(
  () =>
    checkedValues.value.length > 0 &&
    checkedValues.value.length < props.options.length,
);

function handleOk() {
  emit('confirm', checkedValues.value);
}
</script>

<template>
  <Modal
    v-model:open="open"
    :confirm-loading="confirmLoading"
    :ok-button-props="{ disabled: checkedValues.length === 0 }"
    :title="title"
    @ok="handleOk"
  >
    <div class="border-b border-border pb-2.5 mb-2.5">
      <Checkbox v-model:checked="allChecked" :indeterminate="indeterminate">
        全选
      </Checkbox>
    </div>
    <CheckboxGroup
      v-model:value="checkedValues"
      class="flex flex-wrap gap-x-2.5 gap-y-3 max-h-72 overflow-y-auto"
    >
      <Checkbox v-for="item in options" :key="item.value" :value="item.value">
        {{ item.label }}
      </Checkbox>
    </CheckboxGroup>
  </Modal>
</template>
