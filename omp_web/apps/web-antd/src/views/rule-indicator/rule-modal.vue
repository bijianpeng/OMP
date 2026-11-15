<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue/es/form';

import type { RuleCenterApi } from '#/api/rule-center';

import { computed, nextTick, reactive, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Cascader,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Radio,
  RadioGroup,
  Select,
  Switch,
  Table,
  Textarea,
  Tooltip,
} from 'ant-design-vue';

import {
  listBuiltinsRules,
  saveQuotaRule,
  testPromSql,
} from '#/api/rule-center';
import { useEnvStore } from '#/store';

defineOptions({ name: 'RuleIndicatorModal' });

const emit = defineEmits<{ success: [] }>();

/** 当前环境上下文（指标规则写入当前环境） */
const envStore = useEnvStore();

/** 触发条件选项（与旧前端一致） */
const COMPARE_OPTIONS = ['>=', '>', '==', '!=', '<=', '<'].map((value) => ({
  label: value,
  value,
}));
/** 持续时长单位（提交时拼接：for_time = 数值 + 单位） */
const TIME_UNITS = [
  { label: '秒', value: 's' },
  { label: '分', value: 'm' },
  { label: '时', value: 'h' },
];

const open = ref(false);
const saving = ref(false);
/** 编辑目标规则，null 表示新增 */
const editingRow = ref<null | RuleCenterApi.QuotaRule>(null);
/** 规则类型：0 内置指标 / 1 自定义 PromSQL（创建后不可变更，与旧前端一致） */
const quotaType = ref<'0' | '1'>('0');
/** 持续时长单位 */
const forTimeUnit = ref('s');

const model = reactive({
  alert: '',
  builtins_quota: [] as string[],
  compare_str: '>=',
  description: '',
  expr: '',
  for_time: 60,
  severity: 'warning',
  service: '',
  status: true,
  summary: '',
  threshold_value: 30,
});

const rules: Record<string, any[]> = {
  alert: [{ message: '请输入规则名称', required: true }],
  builtins_quota: [{ message: '请选择指标', required: true }],
  expr: [{ message: '请输入PromSQL', required: true }],
  compare_str: [{ message: '请选择触发条件', required: true }],
  threshold_value: [{ message: '请选择触发阈值', required: true }],
  for_time: [
    { message: '请选择持续时长', required: true },
    {
      validator: (_rule: any, value: number) =>
        value > 0 ? Promise.resolve() : Promise.reject('只支持大于0的数字'),
    },
  ],
  service: [{ message: '请输入关联服务', required: true }],
  severity: [{ message: '请选择告警等级', required: true }],
  summary: [{ message: '请输入告警标题', required: true }],
  description: [{ message: '请输入告警消息', required: true }],
};

/** 内置指标原始数据（service → 指标列表），级联选项与提交载荷共用 */
const builtinsData = ref<Record<string, RuleCenterApi.BuiltinsRule[]>>({});
/** 级联选项（「数据分区使用率」禁选，与旧前端一致） */
const cascaderOptions = ref<any[]>([]);

async function loadCascaderOptions() {
  try {
    const data = await listBuiltinsRules();
    builtinsData.value = data ?? {};
    cascaderOptions.value = Object.keys(builtinsData.value).map((service) => ({
      children: (builtinsData.value[service] ?? []).map((item) => ({
        disabled: item.name === '数据分区使用率',
        label: item.name,
        value: item.name,
      })),
      label: service,
      value: service,
    }));
  } catch {
    // 全局拦截器已提示，级联留空
  }
}

const isEditing = computed(() => editingRow.value !== null);
/** 修改态：规则名称在 forbidden==2（禁止删除的内置规则）时禁改 */
const alertDisabled = computed(() => editingRow.value?.forbidden === 2);

/**
 * 打开弹窗：不传 record 为新增，传入为编辑（回填行数据）。
 * 持续时长拆成「数值 + 单位」（如 "300s" → 300 + s）。
 */
async function openModal(record?: RuleCenterApi.QuotaRule) {
  editingRow.value = record ?? null;
  open.value = true;
  loadCascaderOptions();
  await nextTick();
  formRef.value?.resetFields();
  quotaType.value = record ? (String(record.quota_type) as '0' | '1') : '0';
  forTimeUnit.value = record ? record.for_time.slice(-1) : 's';
  const forTime = Number.parseInt(record?.for_time ?? '60', 10);
  Object.assign(model, {
    alert: record?.alert ?? '',
    builtins_quota:
      record?.quota_type === 0 ? [record.service ?? '', record.name ?? ''] : [],
    compare_str: record?.compare_str ?? '>=',
    description: record?.description ?? '',
    expr: record?.expr ?? '',
    for_time: Number.isNaN(forTime) ? 60 : forTime,
    severity: record?.severity ?? 'warning',
    service: record?.service ?? '',
    status: record ? record.status === 1 : true,
    summary: record?.summary ?? '',
    threshold_value: record?.threshold_value ?? 30,
  });
}

defineExpose({ open: openModal });

// ── 测试查询 ──────────────────────────────────────────────────────

const testOpen = ref(false);
const testLoading = ref(false);
const testRows = ref<{ metric: string; value: string }[]>([]);

/** 测试 PromSQL：展示格式与旧前端一致（{__name__}{其余标签 JSON 首个冒号转 =}） */
async function handleTestPromSql() {
  const expr = model.expr.trim();
  if (!expr) {
    message.warning('请输入PromSQL');
    return;
  }
  testLoading.value = true;
  try {
    const data = await testPromSql(expr);
    testRows.value = (data ?? []).map((item) => {
      const name = item.metric?.__name__ ?? '';
      const labels = { ...item.metric };
      delete labels.__name__;
      return {
        metric: `${name}${JSON.stringify(labels).replace(/:/, '=')}`,
        value: item.value?.[1] ?? '-',
      };
    });
    testOpen.value = true;
  } catch {
    // 全局拦截器已提示
  } finally {
    testLoading.value = false;
  }
}

// ── 提交 ─────────────────────────────────────────────────────────

const formRef = ref<FormInstance>();

async function handleSubmit() {
  const valid = await formRef.value
    ?.validate()
    .then(() => true)
    .catch(() => false);
  if (!valid) return;

  const payload: RuleCenterApi.QuotaRulePayload = {
    alert: model.alert,
    compare_str: model.compare_str,
    env_id: envStore.currentEnvId!,
    for_time: `${model.for_time}${forTimeUnit.value}`,
    quota_type: Number(quotaType.value),
    severity: model.severity,
    // 占位，按规则类型在下方分支覆盖
    status: 0,
    threshold_value: model.threshold_value,
  };
  if (quotaType.value === '0') {
    // 内置指标：载荷携带 {description,name,expr,service}；修改态弹窗不展示
    // 启用状态开关，沿用库内状态（与旧前端一致）
    const [service = '', name = ''] = model.builtins_quota;
    const found = (builtinsData.value[service] ?? []).find(
      (item: RuleCenterApi.BuiltinsRule) => item.name === name,
    );
    if (!found) {
      message.error('所选内置指标不存在，请重新选择');
      return;
    }
    payload.builtins_quota = {
      description: found.description,
      // 禁选指标「数据分区使用率」被修改时保留库内表达式，避免被模板表达式覆盖（旧前端语义）
      expr:
        editingRow.value?.name === '数据分区使用率'
          ? (editingRow.value.expr ?? found.expr)
          : found.expr,
      name: found.name,
      service: found.service,
    };
    payload.status = editingRow.value
      ? editingRow.value.status
      : model.status
        ? 1
        : 0;
    payload.service = found.service;
  } else {
    payload.description = model.description;
    payload.expr = model.expr;
    payload.service = model.service;
    payload.status = model.status ? 1 : 0;
    payload.summary = model.summary;
  }
  if (editingRow.value) {
    payload.id = editingRow.value.id;
  }

  saving.value = true;
  try {
    await saveQuotaRule(payload);
    message.success(editingRow.value ? '修改操作下发成功' : '添加操作下发成功');
    open.value = false;
    emit('success');
  } catch {
    // 全局拦截器已提示（如「同一指标规则级别重复添加」）
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal
    :confirm-loading="saving"
    :open="open"
    :title="editingRow ? '修改指标规则' : '添加指标规则'"
    :width="800"
    cancel-text="取消"
    destroy-on-close
    ok-text="确定"
    @cancel="open = false"
    @ok="handleSubmit"
  >
    <Form
      ref="formRef"
      :label-col="{ span: 5 }"
      :model="model"
      :rules="rules"
      :wrapper-col="{ span: 18 }"
    >
      <FormItem
        label="规则名称"
        name="alert"
        tooltip="指标规则的名称，方便识别"
      >
        <div class="max-w-[520px]">
          <!-- 限宽挂包裹 div：antdv 样式未入 @layer，宽度类直接打组件上会被 width:100% 覆盖 -->
          <Input
            v-model:value="model.alert"
            :disabled="alertDisabled"
            placeholder="请输入规则名称"
          />
        </div>
      </FormItem>
      <FormItem label="规则类型">
        <!-- 旧前端契约：规则类型仅创建时可选择，修改态禁改 -->
        <RadioGroup v-model:value="quotaType" :disabled="isEditing">
          <Radio.Button value="0">内置指标</Radio.Button>
          <Radio.Button value="1">自定义PromSQL</Radio.Button>
        </RadioGroup>
        <Tooltip title="内置PromSQL指标方便使用，也可以添加自定义PromSQL规则">
          <IconifyIcon class="ml-2 inline align-[-2px]" icon="lucide:circle-help" />
        </Tooltip>
      </FormItem>

      <FormItem
        v-if="quotaType === '0'"
        label="选择指标"
        name="builtins_quota"
        tooltip="选择需要监控的指标"
      >
        <div class="max-w-[520px]">
          <Cascader
            v-model:value="model.builtins_quota"
            :disabled="isEditing"
            :options="cascaderOptions"
            placeholder="请选择指标"
          />
        </div>
      </FormItem>
      <FormItem v-else label="PromSQL" name="expr">
        <div class="flex max-w-[520px] items-center gap-2">
          <Input v-model:value="model.expr" placeholder="请输入PromSQL" />
          <Button :loading="testLoading" type="primary" @click="handleTestPromSql">
            测试查询
          </Button>
        </div>
      </FormItem>

      <FormItem label="触发条件" name="compare_str">
        <div class="max-w-[520px]">
          <Select
            v-model:value="model.compare_str"
            :options="COMPARE_OPTIONS"
            placeholder="请选择触发条件"
          />
        </div>
      </FormItem>
      <FormItem
        label="触发阈值"
        name="threshold_value"
        tooltip="只支持大于等于0的数字"
      >
        <div class="max-w-[520px]">
          <InputNumber v-model:value="model.threshold_value" :min="0" style="width: 100%" />
        </div>
      </FormItem>
      <FormItem
        label="持续时长"
        name="for_time"
        tooltip="通在持续时长内均匹配规则后会触发告警"
      >
        <div class="max-w-[520px]">
          <InputNumber v-model:value="model.for_time" :min="0" style="width: 100%">
            <template #addonAfter>
              <Select
                v-model:value="forTimeUnit"
                :bordered="false"
                :options="TIME_UNITS"
                style="width: 72px"
              />
            </template>
          </InputNumber>
        </div>
      </FormItem>

      <FormItem
        v-if="quotaType === '1'"
        label="关联服务"
        name="service"
        tooltip="输入关联服务后，该指标的告警会归类于该服务名，如“mysql”，如需关联到主机，请填写“node”"
      >
        <div class="max-w-[520px]">
          <Input v-model:value="model.service" placeholder="请输入关联服务" />
        </div>
      </FormItem>

      <FormItem label="告警等级" name="severity">
        <RadioGroup v-model:value="model.severity">
          <Radio value="warning">警告</Radio>
          <Radio value="critical">严重</Radio>
        </RadioGroup>
      </FormItem>

      <!-- 内置指标修改态不展示启用状态开关（提交沿用库内状态，与旧前端一致） -->
      <FormItem
        v-if="!(quotaType === '0' && isEditing)"
        label="启用状态"
        name="status"
      >
        <Switch v-model:checked="model.status" />
      </FormItem>

      <template v-if="quotaType === '1'">
        <FormItem
          label="告警标题"
          name="summary"
          tooltip="标题中可配置Prometheus中的标签，如 {{ $labels.instance }}"
        >
          <div class="max-w-[520px]">
            <Input v-model:value="model.summary" placeholder="请输入告警标题" />
          </div>
        </FormItem>
        <FormItem
          label="告警消息"
          name="description"
          tooltip="消息中可配Prometheus中的标签，如 {{ $labels.instance }}"
        >
          <div class="max-w-[520px]">
            <Textarea
              v-model:value="model.description"
              :rows="4"
              placeholder="请输入告警消息"
            />
          </div>
        </FormItem>
      </template>
    </Form>

    <Modal
      :footer="null"
      :open="testOpen"
      :width="900"
      destroy-on-close
      title="PromSQL查询结果"
      @cancel="testOpen = false"
    >
      <div class="border border-border">
        <Table
          :columns="[
            { dataIndex: 'metric', key: 'metric', title: '指标' },
            { dataIndex: 'value', key: 'value', title: '值', width: 120 },
          ]"
          :data-source="testRows"
          :pagination="false"
          :scroll="{ x: 800 }"
          :show-header="false"
          size="small"
        />
      </div>
    </Modal>
  </Modal>
</template>
