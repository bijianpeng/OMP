<script lang="ts" setup>
import { onMounted, reactive } from 'vue';

import { Page } from '@vben/common-ui';

import { Button, Card, message } from 'ant-design-vue';

import { useVbenForm, z } from '#/adapter/form';
import {
  createPatrolStrategy,
  queryInspectionEmailSetting,
  queryPatrolStrategy,
  updateInspectionEmailSetting,
  updatePatrolStrategy,
} from '#/api/patrol-strategy';
import { useEnvStore } from '#/store';

defineOptions({ name: 'PatrolStrategy' });

/** 任务类型只支持「深度分析」（后端 job_type=0），与旧前端一致 */
const TASK_TYPE_OPTIONS = [{ label: '深度分析', value: 0 }];
/** 星期选项值与旧前端一致：0=星期一 ... 6=星期日，后端 transfer_week 负责换算 */
const WEEK_OPTIONS = [
  '星期一',
  '星期二',
  '星期三',
  '星期四',
  '星期五',
  '星期六',
  '星期日',
].map((label, idx) => ({ label, value: `${idx}` }));
const MONTH_DAY_OPTIONS = Array.from({ length: 28 }, (_, idx) => ({
  label: `${idx + 1}日`,
  value: `${idx + 1}`,
}));
const FREQUENCY_OPTIONS = [
  { label: '每天', value: 'day' },
  { label: '每周', value: 'week' },
  { label: '每月', value: 'month' },
];

/** 当前环境上下文（巡检任务与推送设置随当前环境读写） */
const envStore = useEnvStore();

/** 当前是否存在巡检任务：存在走更新 PUT，不存在走创建 POST（旧前端语义） */
const crontabState = reactive({ hasTask: false, saving: false });
const pushState = reactive({ saving: false });

const [CrontabForm, crontabFormApi] = useVbenForm({
  commonConfig: {
    componentProps: { style: { width: '240px' } },
    // 固定 labelCol 宽度 + 左对齐：auto 模式下带 help/必填星号的行与裸 label 行
    // 右对齐基准不一（label 右移错位），左对齐后星号亦紧贴文字
    labelClass: 'justify-start pr-2',
    labelWidth: '128px',
  },
  schema: [
    {
      component: 'Select',
      componentProps: { options: TASK_TYPE_OPTIONS, placeholder: '请选择巡检任务类型' },
      defaultValue: 0,
      fieldName: 'type',
      help: '当前版本只支持“深度分析”类型的巡检任务设置',
      label: '任务类型',
    },
    {
      component: 'Input',
      componentProps: { maxLength: 16, placeholder: '例如：深度分析' },
      defaultValue: '深度分析',
      fieldName: 'name',
      help: '任务名称显示在“报告列表”及“报告内容”中，系统自动补充日期信息',
      label: '任务名称',
      rules: z.string().trim().min(1, { message: '请输入巡检任务名称' }),
    },
    {
      component: 'Switch',
      componentProps: { style: { width: 'auto' } },
      defaultValue: false,
      fieldName: 'isOpen',
      help: '开启定时巡检后，将在设定的时间，自动执行巡检任务',
      label: '定时巡检',
    },
    {
      component: 'Select',
      componentProps: { options: FREQUENCY_OPTIONS },
      defaultValue: 'day',
      dependencies: {
        resolve: ({ values }) => ({ if: Boolean(values.isOpen) }),
        triggerFields: ['isOpen'],
      },
      fieldName: 'frequency',
      label: '定时策略',
    },
    {
      component: 'Select',
      componentProps: { options: WEEK_OPTIONS },
      defaultValue: '0',
      dependencies: {
        resolve: ({ values }) => ({
          if: Boolean(values.isOpen) && values.frequency === 'week',
        }),
        triggerFields: ['frequency', 'isOpen'],
      },
      fieldName: 'week',
      label: '',
    },
    {
      component: 'Select',
      componentProps: { options: MONTH_DAY_OPTIONS },
      defaultValue: '1',
      dependencies: {
        resolve: ({ values }) => ({
          if: Boolean(values.isOpen) && values.frequency === 'month',
        }),
        triggerFields: ['frequency', 'isOpen'],
      },
      fieldName: 'month',
      label: '',
    },
    {
      component: 'TimePicker',
      componentProps: { allowClear: false, format: 'HH:mm', valueFormat: 'HH:mm' },
      defaultValue: '00:00',
      dependencies: {
        resolve: ({ values }) => ({ if: Boolean(values.isOpen) }),
        triggerFields: ['isOpen'],
      },
      fieldName: 'time',
      label: '',
    },
  ],
  showDefaultActions: false,
});

const [PushForm, pushFormApi] = useVbenForm({
  commonConfig: {
    componentProps: { style: { width: '240px' } },
    // 与巡检设置表单保持同一 labelCol 基准
    labelClass: 'justify-start pr-2',
    labelWidth: '128px',
  },
  schema: [
    {
      component: 'Switch',
      componentProps: { style: { width: 'auto' } },
      defaultValue: false,
      fieldName: 'pushIsOpen',
      label: '启用',
    },
    {
      component: 'Input',
      componentProps: {
        placeholder: '例如: emailname@163.com',
        style: { width: '360px' },
      },
      dependencies: {
        resolve: ({ values }) => ({ if: Boolean(values.pushIsOpen) }),
        triggerFields: ['pushIsOpen'],
      },
      fieldName: 'email',
      label: '巡检报告接收人',
      rules: z
        .string()
        .min(1, { message: '请输入接收人邮箱' })
        .email({ message: '请输入正确格式的邮箱' }),
    },
  ],
  showDefaultActions: false,
});

/** 查询巡检任务并回填（解析规则与旧前端一致） */
async function loadCrontab() {
  try {
    const data = await queryPatrolStrategy(0);
    crontabState.hasTask = Boolean(data.job_name);
    const detail = data.crontab_detail;
    const values: Record<string, any> = {
      isOpen: !data.is_start_crontab, // 0=开启（历史约定）
      name: data.job_name,
      type: data.job_type,
    };
    // 频率还原顺序与旧前端一致：周 → 月 → 天（天 = 两者均未指定）
    if (detail) {
      if (detail.day_of_week !== '*') {
        values.frequency = 'week';
        values.week = detail.day_of_week;
        values.time = `${detail.hour}:${detail.minute}`;
      }
      if (detail.day !== '*') {
        values.frequency = 'month';
        values.month = detail.day;
        values.time = `${detail.hour}:${detail.minute}`;
      }
      if (detail.day === '*' && detail.day_of_week === '*') {
        values.frequency = 'day';
        values.time = `${detail.hour}:${detail.minute}`;
      }
    }
    await crontabFormApi.setValues(values);
  } catch {
    // 任务不存在（后端 404）时保持表单默认值，走创建分支
    crontabState.hasTask = false;
  }
}

/** 保存巡检策略 */
async function saveCrontab() {
  const { valid } = await crontabFormApi.validate();
  if (!valid) return;
  const values = await crontabFormApi.getValues();
  const [hour, minute] = String(values.time ?? '00:00').split(':');
  const payload = {
    crontab_detail: {
      // 修正旧前端遗留值 bug：仅按当前频率提交对应字段，其余置 "*"
      day: values.frequency === 'month' ? (values.month as string) : '*',
      day_of_week:
        values.frequency === 'week' ? (values.week as string) : '*',
      hour: hour ?? '*',
      minute: minute ?? '*',
      month: '*',
    },
    env: envStore.currentEnvId!,
    // 0=开启定时（历史约定）
    is_start_crontab: values.isOpen ? 0 : 1,
    job_name: values.name as string,
    job_type: 0,
  };
  crontabState.saving = true;
  try {
    if (crontabState.hasTask) {
      await updatePatrolStrategy(0, payload);
      message.success('更新巡检策略成功');
    } else {
      await createPatrolStrategy(payload);
      message.success('新增巡检策略成功');
    }
    await loadCrontab();
  } catch {
    // 全局拦截器已提示错误信息
  } finally {
    crontabState.saving = false;
  }
}

/** 查询推送设置并回填 */
async function loadPush() {
  try {
    const data = await queryInspectionEmailSetting();
    await pushFormApi.setValues({
      email: data.to_users ?? undefined,
      pushIsOpen: Boolean(data.send_email),
    });
  } catch {
    // 保持默认值
  }
}

/** 保存推送设置 */
async function savePush() {
  const { valid } = await pushFormApi.validate();
  if (!valid) return;
  const values = await pushFormApi.getValues();
  pushState.saving = true;
  try {
    await updateInspectionEmailSetting({
      env_id: envStore.currentEnvId!,
      send_email: Boolean(values.pushIsOpen),
      to_users: (values.email as string) || null,
    });
    message.success('更新巡检报告推送设置成功');
    await loadPush();
  } catch {
    // 全局拦截器已提示错误信息
  } finally {
    pushState.saving = false;
  }
}

onMounted(() => {
  loadCrontab();
  loadPush();
});
</script>

<template>
  <Page
    content-class="flex flex-col gap-4 overflow-y-auto pb-2 lg:flex-row lg:items-start"
  >
    <Card class="min-w-0 flex-1" title="巡检设置">
      <CrontabForm />
      <div class="mt-4">
        <Button :loading="crontabState.saving" type="primary" @click="saveCrontab">
          保存
        </Button>
      </div>
    </Card>

    <Card class="min-w-0 flex-1" title="巡检报告推送设置">
      <PushForm />
      <div class="mt-4">
        <Button :loading="pushState.saving" type="primary" @click="savePush">
          保存
        </Button>
      </div>
    </Card>
  </Page>
</template>
