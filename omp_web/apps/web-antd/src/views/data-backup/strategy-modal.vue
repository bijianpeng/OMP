<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';

import { computed, reactive, ref } from 'vue';

import { message, Form, FormItem, Input, Modal, Select, Switch, TimePicker, Tooltip } from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  createBackupStrategy,
  queryBackupCustom,
  queryCanBackupInstances,
  updateBackupStrategy,
} from '#/api/data-backup';
import type { DataBackupApi } from '#/api/data-backup';

defineOptions({ name: 'BackupStrategyModal' });

const emit = defineEmits<{ success: [] }>();

/** 星期汉字映射（索引即 crontab day_of_week 值） */
const WEEK_TEXT = [
  '星期一',
  '星期二',
  '星期三',
  '星期四',
  '星期五',
  '星期六',
  '星期日',
];

/** 保留时间选项（与旧前端一致） */
const RETAIN_DAY_OPTIONS = [
  { label: '永久保留', value: -1 },
  { label: '1天', value: 1 },
  { label: '7天', value: 7 },
  { label: '30天', value: 30 },
];

/** 月度执行日 1~28（与旧前端一致，不提供 29-31） */
const MONTH_DAY_OPTIONS = Array.from({ length: 28 }, (_, idx) => ({
  label: `${idx + 1}日`,
  value: `${idx + 1}`,
}));

const editingId = ref<null | number>(null);
const open = ref(false);
const saving = ref(false);
const loading = ref(false);

/** 可备份实例（状态正常的可备份服务实例名） */
const canBackupInstances = ref<string[]>([]);
/** 自定义参数全量（提交时由 id 反查 field_k/field_v） */
const customList = ref<DataBackupApi.BackupCustomParam[]>([]);

const formRef = ref<FormInstance>();
const formState = reactive({
  backup_custom: [] as number[],
  backup_instances: [] as string[],
  /** day | week | month */
  frequency: 'day',
  is_on: false,
  month: '1',
  retain_day: 7,
  retain_path: '/data/omp/data/backup/',
  time: dayjs('00:00', 'HH:mm'),
  week: '0',
});

const retainPathRules = [
  { message: '请输入备份路径', required: true },
  {
    validator: (_rule: unknown, value: string) =>
      !value || !/^[ ]*$/.test(value)
        ? Promise.resolve()
        : Promise.reject('请输入备份路径'),
  },
];

const backupInstancesRules = [
  {
    message: '请选择备份实例',
    required: true,
    type: 'array' as const,
  },
];

const retainDayRules = [{ message: '请选择保留策略', required: true }];

/** 已选自定义参数占用的 field_k（同名字段不允许重复选择） */
const selectedFieldKeys = computed(() =>
  customList.value
    .filter((item) => formState.backup_custom.includes(item.id))
    .map((item) => item.field_k),
);

function isCustomOptionDisabled(item: DataBackupApi.BackupCustomParam) {
  return (
    selectedFieldKeys.value.includes(item.field_k) &&
    !formState.backup_custom.includes(item.id)
  );
}

/** 组装请求体（字段与旧前端 makeRequestBody 完全一致） */
function makePayload(): DataBackupApi.StrategyPayload {
  const timeInfo = formState.time.format('HH:mm');
  return {
    backup_custom: formState.backup_custom
      .map((id) => customList.value.find((item) => item.id === id))
      .filter((item): item is DataBackupApi.BackupCustomParam => !!item)
      .map((item) => ({
        field_k: item.field_k,
        id: item.id,
        field_v: item.field_v,
      })),
    backup_instances: formState.backup_instances,
    crontab_detail: {
      // 修正旧前端遗留值 bug（与巡检策略同款）：仅按当前频率提交对应字段，其余置 '*'
      day_of_month: formState.frequency === 'month' ? formState.month : '*',
      day_of_week: formState.frequency === 'week' ? formState.week : '*',
      hour: timeInfo.split(':')[0] ?? '*',
      minute: timeInfo.split(':')[1] ?? '*',
      month_of_year: '*',
    },
    is_on: formState.is_on,
    retain_day: formState.retain_day,
    retain_path: formState.retain_path,
  };
}

/** 打开弹窗：不传为新增，传入为编辑（按行数据回填） */
async function openModal(record?: DataBackupApi.BackupSetting) {
  editingId.value = record?.id ?? null;
  open.value = true;
  loading.value = true;
  try {
    const [instances, custom] = await Promise.all([
      queryCanBackupInstances(),
      queryBackupCustom(),
    ]);
    canBackupInstances.value = instances;
    customList.value = custom;
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
  if (record) {
    const crontab = record.crontab_detail;
    const frequency =
      crontab.day_of_month !== '*'
        ? 'month'
        : crontab.day_of_week !== '*'
          ? 'week'
          : 'day';
    Object.assign(formState, {
      backup_custom: record.backup_custom.map((item) => item.id),
      backup_instances: [...record.backup_instances],
      frequency,
      is_on: record.is_on,
      month: crontab.day_of_month,
      retain_day: record.retain_day,
      retain_path: record.retain_path,
      time: dayjs(`${crontab.hour}:${crontab.minute}`, 'HH:mm'),
      week: crontab.day_of_week,
    });
  } else {
    Object.assign(formState, {
      backup_custom: [],
      backup_instances: [],
      frequency: 'day',
      is_on: false,
      month: '1',
      retain_day: 7,
      retain_path: '/data/omp/data/backup/',
      time: dayjs('00:00', 'HH:mm'),
      week: '0',
    });
  }
  formRef.value?.clearValidate();
}

defineExpose({ open: openModal });

function close() {
  open.value = false;
}

async function handleSubmit() {
  try {
    await formRef.value?.validate();
  } catch {
    return;
  }
  saving.value = true;
  try {
    const payload = makePayload();
    if (editingId.value === null) {
      await createBackupStrategy(payload);
      message.success('添加备份策略成功');
    } else {
      await updateBackupStrategy(editingId.value, payload);
      message.success('修改备份策略成功');
    }
    close();
    emit('success');
  } catch {
    // 全局拦截器已提示（如 retain_path 读写权限校验失败）
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal
    :confirm-loading="saving"
    :open="open"
    :title="editingId === null ? '添加备份策略' : '编辑备份策略'"
    :width="660"
    cancel-text="取消"
    destroy-on-close
    ok-text="确定"
    @cancel="close"
    @ok="handleSubmit"
  >
    <Form ref="formRef" :model="formState" layout="vertical">
      <FormItem
        label="备份实例"
        :rules="backupInstancesRules"
        name="backup_instances"
      >
        <Select
          v-model:value="formState.backup_instances"
          max-tag-count="responsive"
          :options="
            canBackupInstances.map((name) => ({ label: name, value: name }))
          "
          allow-clear
          mode="multiple"
          placeholder="选择实例"
        />
      </FormItem>
      <FormItem label="备份路径" :rules="retainPathRules" name="retain_path">
        <Input v-model:value="formState.retain_path" placeholder="请输入备份路径" />
      </FormItem>
      <FormItem label="备份保留" :rules="retainDayRules" name="retain_day">
        <Select
          v-model:value="formState.retain_day"
          :options="RETAIN_DAY_OPTIONS"
          :style="{ width: '120px' }"
        />
      </FormItem>
      <FormItem label="定时备份">
        <div class="flex items-center gap-2">
          <Switch v-model:checked="formState.is_on" />
          <Tooltip title="开启定时后，将自动执行定时任务">
            <span class="text-gray-400">?</span>
          </Tooltip>
        </div>
      </FormItem>
      <FormItem label="定时策略">
        <div class="flex items-center gap-2.5">
          <Select
            v-model:value="formState.frequency"
            :options="[
              { label: '每天', value: 'day' },
              { label: '每周', value: 'week' },
              { label: '每月', value: 'month' },
            ]"
            :style="{ width: '100px' }"
          />
          <Select
            v-if="formState.frequency === 'week'"
            v-model:value="formState.week"
            :options="
              WEEK_TEXT.map((label, idx) => ({ label, value: `${idx}` }))
            "
            :style="{ width: '120px' }"
          />
          <Select
            v-if="formState.frequency === 'month'"
            v-model:value="formState.month"
            :options="MONTH_DAY_OPTIONS"
            :style="{ width: '120px' }"
          />
          <TimePicker
            v-model:value="formState.time"
            :allow-clear="false"
            format="HH:mm"
          />
        </div>
      </FormItem>
      <FormItem label="自定义参数" name="backup_custom">
        <Select
          v-model:value="formState.backup_custom"
          max-tag-count="responsive"
          mode="multiple"
          placeholder="选择自定义参数"
          allow-clear
        >
          <template v-for="item in customList" :key="item.id">
            <Select.Option
              :disabled="isCustomOptionDisabled(item)"
              :value="item.id"
            >
              <span class="mr-2.5 font-semibold text-blue-600">
                [{{ item.field_k }}]
              </span>
              {{ item.field_v }}
            </Select.Option>
          </template>
        </Select>
      </FormItem>
    </Form>
  </Modal>
</template>
