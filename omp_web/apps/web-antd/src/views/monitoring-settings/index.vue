<script lang="ts" setup>
import type { Rule } from 'ant-design-vue/es/form';

import { onMounted, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';

import { Button, Card, Form, FormItem, Input, message, Switch } from 'ant-design-vue';

import {
  queryAlertPushSetting,
  queryMonitorUrls,
  updateAlertPushSetting,
  updateMonitorUrls,
} from '#/api/promemonitor';
import { useEnvStore } from '#/store';

defineOptions({ name: 'MonitoringSettings' });

/**
 * 配置表单页模板基准：
 * - Page 不加 min-h-0/overflow-hidden（表单页允许整页滚动，与列表页三层铁律的差异点）
 * - 分组用 Card（title 即分组标题），组内 antdv Form 垂直布局 + 底部保存按钮
 * - 提交走 Form @finish（校验通过才触发）；失败由 requestClient 抛错、
 *   全局拦截器提示，表单状态不动（保留用户输入）
 */

/** URL 合法字符白名单（与旧前端一致：RFC 3986 unreserved + reserved） */
const URL_LEGAL_PATTERN = /^[a-zA-Z0-9\-_.~!*'();:@&=+$,/?#[\]]*$/;

/** 监控地址校验：空值放行（必填交给 required 规则） */
function validateMonitorUrl(title: string) {
  return (_rule: Rule, value: string) =>
    !value || URL_LEGAL_PATTERN.test(value)
      ? Promise.resolve()
      : Promise.reject(`${title}地址存在非法字符`);
}

// ── 监控平台配置 ────────────────────────────────────────────────

const monitorLoading = ref(false);
const monitorSaving = ref(false);
const monitorModel = reactive({
  alertmanager: '',
  grafana: '',
  prometheus: '',
});
/** name → 记录 id（提交 multiple_update 必需） */
const monitorIds = reactive<Record<string, number>>({});

const monitorRules: Record<string, Rule[]> = {
  alertmanager: [
    { message: '请输入 Alert Manager 地址', required: true },
    { validator: validateMonitorUrl('Alert Manager') },
  ],
  grafana: [
    { message: '请输入 Grafana 地址', required: true },
    { validator: validateMonitorUrl('Grafana') },
  ],
  prometheus: [
    { message: '请输入 Prometheus 地址', required: true },
    { validator: validateMonitorUrl('Prometheus') },
  ],
};

async function loadMonitorUrls() {
  monitorLoading.value = true;
  try {
    const data = await queryMonitorUrls();
    for (const item of data) {
      monitorIds[item.name] = item.id;
      if (item.name in monitorModel) {
        monitorModel[item.name] = item.monitor_url ?? '';
      }
    }
  } catch {
    // 全局拦截器已提示
  } finally {
    monitorLoading.value = false;
  }
}

async function saveMonitorUrls() {
  monitorSaving.value = true;
  try {
    await updateMonitorUrls(
      Object.keys(monitorModel).map((name) => ({
        id: monitorIds[name],
        monitor_url: monitorModel[name],
      })),
    );
    message.success('更新监控平台配置成功');
    await loadMonitorUrls();
  } catch {
    // 失败保留表单状态，全局拦截器已提示
  } finally {
    monitorSaving.value = false;
  }
}

// ── 告警邮件推送 ────────────────────────────────────────────────

/** 当前环境上下文（推送设置随当前环境读写） */
const envStore = useEnvStore();

const pushLoading = ref(false);
const pushSaving = ref(false);
const pushModel = reactive({ email: '', pushIsOpen: false });

const pushRules: Record<string, Rule[]> = {
  email: [
    { message: '请输入接收人邮箱', required: true },
    { message: '请输入正确格式的邮箱', type: 'email' },
  ],
};

async function loadPushSetting() {
  pushLoading.value = true;
  try {
    const data = await queryAlertPushSetting();
    pushModel.pushIsOpen = data?.email?.used ?? false;
    pushModel.email = data?.email?.server_url ?? '';
  } catch {
    // 全局拦截器已提示
  } finally {
    pushLoading.value = false;
  }
}

async function savePushSetting() {
  pushSaving.value = true;
  try {
    await updateAlertPushSetting({
      // 关闭推送时保留已存邮箱，仅翻转 used（与旧前端 preserve 语义一致）
      env_id: envStore.currentEnvId!,
      server_url: pushModel.email || '',
      used: pushModel.pushIsOpen,
      way_name: 'email',
    });
    message.success('更新监控推送设置成功');
    await loadPushSetting();
  } catch {
    // 失败保留表单状态，全局拦截器已提示
  } finally {
    pushSaving.value = false;
  }
}

onMounted(() => {
  loadMonitorUrls();
  loadPushSetting();
});
</script>

<template>
  <Page>
    <div class="flex flex-col gap-4 lg:flex-row lg:items-start">
      <Card class="min-w-0 flex-1" title="监控平台配置" :loading="monitorLoading">
        <Form
          :model="monitorModel"
          :rules="monitorRules"
          layout="vertical"
          @finish="saveMonitorUrls"
        >
          <!-- 限宽挂包裹 div：antdv 样式未入 @layer，宽度类直接打组件上会被 width:100% 覆盖 -->
          <FormItem label="Prometheus地址" name="prometheus">
            <div class="max-w-[480px]">
              <Input
                v-model:value="monitorModel.prometheus"
                addon-before="Http://"
                placeholder="请输入 Prometheus 地址"
              />
            </div>
          </FormItem>
          <FormItem label="Grafana地址" name="grafana">
            <div class="max-w-[480px]">
              <Input
                v-model:value="monitorModel.grafana"
                addon-before="Http://"
                placeholder="请输入 Grafana 地址"
              />
            </div>
          </FormItem>
          <FormItem label="Alert Manager地址" name="alertmanager">
            <div class="max-w-[480px]">
              <Input
                v-model:value="monitorModel.alertmanager"
                addon-before="Http://"
                placeholder="请输入 Alert Manager 地址"
              />
            </div>
          </FormItem>
          <Button type="primary" html-type="submit" :loading="monitorSaving">
            保存
          </Button>
        </Form>
      </Card>

      <Card class="min-w-0 flex-1" title="告警邮件" :loading="pushLoading">
        <Form
          :model="pushModel"
          :rules="pushRules"
          layout="vertical"
          @finish="savePushSetting"
        >
          <FormItem label="邮件推送" name="pushIsOpen">
            <Switch v-model:checked="pushModel.pushIsOpen" />
          </FormItem>
          <!-- 关闭时不渲染即不参与校验，提交仅翻转 used -->
          <FormItem v-if="pushModel.pushIsOpen" label="接收人" name="email">
            <div class="max-w-[480px]">
              <Input
                v-model:value="pushModel.email"
                placeholder="例如: emailname@163.com"
              />
            </div>
          </FormItem>
          <Button type="primary" html-type="submit" :loading="pushSaving">
            保存
          </Button>
        </Form>
      </Card>
    </div>
  </Page>
</template>
