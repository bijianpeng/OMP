<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue/es/form';

import type { HostApi } from '#/api/hosts';

import { nextTick, reactive, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import {
  Col,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Row,
  Select,
  Switch,
  Tooltip,
} from 'ant-design-vue';

import { checkHost, createHost, updateHost } from '#/api/hosts';

defineOptions({ name: 'HostFormModal' });

const emit = defineEmits<{ success: [] }>();

/** 编辑目标主机，null 表示新增 */
const editingRow = ref<null | HostApi.HostRecord>(null);
const open = ref(false);
/** 提交中 */
const saving = ref(false);
/** 字段去重校验请求进行中（防抖窗口内多次触发合并展示） */
const checking = ref(false);

const model = reactive({
  data_folder: '/opt',
  instance_name: '',
  /** IP 输入框与端口拆两个字段，提交时合并为 ip（旧前端 IPtext 契约） */
  ip: '',
  IPtext: '',
  ntpd_server: '',
  operate_system: 'CentOS',
  password: '',
  port: 22,
  use_ntpd: true,
  username: 'root',
});

// ── 字段格式校验（照搬旧前端 verify.js 正则语义） ────────────────

const isChineseChar = (str: string) =>
  /[\u4E00-\u9FA5\uF900-\uFA2D]/.test(str);
// 表情等超出常用字符集的输入（照搬旧前端 verify.js 正则）
const isExpression = (str: string) =>
  /[^ -~ -¾⺀-꓏豈-﫿︰-﹏＀-￯\u0080-\u009F\u2000-\u201f\u2026\u2022\u20ac\r\n]/g.test(
    str,
  );
const isSpace = (str: string) => str.includes(' ');
const isValidIp = (ip: string) =>
  /^(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])\.(\d{1,2}|1\d\d|2[0-4]\d|25[0-5])$/.test(
    ip,
  );

// ── 去重校验（防抖 400/600ms，编辑态带 id 排除自身） ─────────────

const formRef = ref<FormInstance>();

let nameTimer: undefined | ReturnType<typeof setTimeout>;
let ipTimer: undefined | ReturnType<typeof setTimeout>;

async function validateInstanceName(_rule: any, value: string) {
  if (!value) return Promise.resolve();
  // 开头只支持字母、数字或"-"（首个字符过正则组）
  const start = value.slice(0, 1);
  if (!/[a-zA-Z0-9-]/.test(start)) {
    return Promise.reject('实例名称开头只支持字母、数字或"-"');
  }
  if (isExpression(value)) return Promise.reject('实例名称不支持表情');
  if (isChineseChar(value)) return Promise.reject('实例名称不支持中文');
  if (value.length <= 16 && isSpace(value)) {
    return Promise.reject('实例名称不支持空格');
  }
  return new Promise((resolve, reject) => {
    clearTimeout(nameTimer);
    nameTimer = setTimeout(async () => {
      checking.value = true;
      try {
        const usable = await checkHost({
          id: editingRow.value?.id,
          instance_name: value,
        });
        usable ? resolve('') : reject('实例名称已存在');
      } catch (error: any) {
        // 全局拦截器已提示后端 message；本地以校验失败收尾
        reject(error?.message ?? '实例名称已存在');
      } finally {
        checking.value = false;
      }
    }, 400);
  });
}

function validateIp(_rule: any, _value: string) {
  const value = model.IPtext;
  const portValue = model.port;
  if (!value || !portValue) {
    return Promise.reject('请输入IP地址或端口号');
  }
  if (!isValidIp(value)) return Promise.reject('请输入正确格式的IP地址');
  return new Promise((resolve, reject) => {
    clearTimeout(ipTimer);
    ipTimer = setTimeout(async () => {
      checking.value = true;
      try {
        const usable = await checkHost({
          id: editingRow.value?.id,
          ip: value,
        });
        usable ? resolve('') : reject('ip地址已存在');
      } catch (error: any) {
        reject(error?.message ?? 'ip地址已存在');
      } finally {
        checking.value = false;
      }
    }, 600);
  });
}

const rules: Record<string, any[]> = {
  instance_name: [
    { message: '请输入实例名称', required: true },
    { validator: validateInstanceName },
  ],
  operate_system: [{ message: '请选择系统平台', required: true }],
  data_folder: [
    { message: '请输入数据分区', required: true },
    {
      validator: (_rule: any, value: string) => {
        if (!value) return Promise.resolve();
        if (!value.startsWith('/')) {
          return Promise.reject('数据分区开头必须为"/"');
        }
        // 只支持字母、数字、"/"、"-"和"_"
        return /[^a-zA-Z0-9_\-/]/.test(value) || isChineseChar(value)
          ? Promise.reject('数据分区只支持字母、数字、"/"、"-"和"_"')
          : Promise.resolve();
      },
    },
  ],
  ip: [{ validator: validateIp }],
  username: [
    { message: '请输入用户名', required: true },
    {
      validator: (_rule: any, value: string) => {
        if (!value) return Promise.resolve();
        const start = value.slice(0, 1);
        // 开头只支持数字、字母或"_"
        if (/[^a-zA-Z0-9_]/.test(start)) {
          return Promise.reject('用户名开头只支持数字、字母、或"_"');
        }
        return /[^a-zA-Z0-9_-]/.test(value) || isChineseChar(value)
          ? Promise.reject('用户名只支持数字、字母、"-"或"_"')
          : Promise.resolve();
      },
    },
  ],
  password: [
    { message: '请输入密码', required: true },
    {
      validator: (_rule: any, value: string) => {
        if (!value) return Promise.resolve();
        if (isExpression(value)) return Promise.reject('密码不支持输入表情');
        if (isChineseChar(value)) return Promise.reject('密码不支持中文');
        if (value.length < 8) return Promise.reject('密码长度为8到64位');
        return isSpace(value) ? Promise.reject('密码不支持空格') : Promise.resolve();
      },
    },
  ],
  ntpd_server: [
    { message: '请输入时间同步服务器', required: true },
    {
      validator: (_rule: any, value: string) => {
        if (!value) return Promise.resolve();
        return isValidIp(value)
          ? Promise.resolve()
          : Promise.reject('请输入正确格式的IP地址');
      },
    },
  ],
};

/**
 * 打开弹窗：不传 record 为新增，传入为编辑（回填行数据；密码 base64 解码）。
 */
async function openModal(record?: HostApi.HostRecord) {
  editingRow.value = record ?? null;
  open.value = true;
  clearTimeout(nameTimer);
  clearTimeout(ipTimer);
  await nextTick();
  formRef.value?.resetFields();
  Object.assign(model, {
    data_folder: record?.data_folder ?? '/opt',
    instance_name: record?.instance_name ?? '',
    ip: record?.ip ?? '',
    IPtext: record?.ip ?? '',
    ntpd_server: record?.ntpd_server ?? '',
    operate_system: record?.operate_system ?? 'CentOS',
    password: record?.password ? atob(record.password) : '',
    port: record?.port ?? 22,
    use_ntpd: record ? Boolean(record.use_ntpd) : true,
    username: record?.username ?? 'root',
  });
}

defineExpose({ open: openModal });

async function handleSubmit() {
  const valid = await formRef.value
    ?.validate()
    .then(() => true)
    .catch(() => false);
  if (!valid) return;

  const payload: HostApi.HostFormPayload = {
    data_folder: model.data_folder,
    instance_name: model.instance_name,
    ip: model.IPtext,
    // 旧前端契约：port 以字符串提交
    port: `${model.port}`,
    password: model.password,
    username: model.username,
    operate_system: model.operate_system,
    use_ntpd: model.use_ntpd,
  };
  if (model.use_ntpd && model.ntpd_server) {
    payload.ntpd_server = model.ntpd_server;
  }
  saving.value = true;
  try {
    if (editingRow.value) {
      await updateHost(editingRow.value.id, payload);
      message.success('更新主机信息成功');
    } else {
      await createHost(payload);
      message.success('添加主机成功');
    }
    open.value = false;
    emit('success');
  } catch {
    // 全局拦截器已提示（如 IP/实例名已被占用）
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal
    :confirm-loading="saving || checking"
    :ok-text="checking ? '校验中' : '确定'"
    :open="open"
    :title="editingRow ? '修改主机信息' : '创建主机信息'"
    :width="600"
    cancel-text="取消"
    destroy-on-close
    @cancel="open = false"
    @ok="handleSubmit"
  >
    <Form
      ref="formRef"
      :label-col="{ span: 6 }"
      :model="model"
      :rules="rules"
      :wrapper-col="{ span: 16 }"
    >
      <FormItem label="实例名称" name="instance_name">
        <div class="max-w-[420px]">
          <!-- 限宽挂包裹 div：antdv 样式未入 @layer，宽度类直接打组件上会被 width:100% 覆盖 -->
          <Input
            v-model:value="model.instance_name"
            :maxlength="16"
            placeholder="请输入实例名称"
          />
        </div>
      </FormItem>

      <FormItem label="系统平台" name="operate_system">
        <div class="max-w-[420px]">
          <Select
            v-model:value="model.operate_system"
            :options="[
              { label: 'CentOS', value: 'CentOS' },
              { label: 'RedHat', value: 'RedHat' },
            ]"
            placeholder="请选择系统平台"
          />
        </div>
      </FormItem>

      <FormItem
        label="数据分区"
        name="data_folder"
        extra="应用组件默认安装到数据分区,请确保具有足够空间"
      >
        <div class="max-w-[420px]">
          <Input
            v-model:value="model.data_folder"
            :maxlength="255"
            placeholder="请输入数据分区"
          />
        </div>
      </FormItem>

      <FormItem label="IP地址" name="ip">
        <!-- 内层 noStyle FormItem 各自接管控件收集，外层仅承载组合校验（旧版同构） -->
        <Row :gutter="8">
          <Col :span="15">
            <FormItem name="IPtext" no-style>
              <Input
                v-model:value="model.IPtext"
                :disabled="Boolean(editingRow)"
                placeholder="例如: 192.168.10.10"
              />
            </FormItem>
          </Col>
          <Col class="flex items-center justify-center" :span="1">:</Col>
          <Col :span="7">
            <FormItem name="port" no-style>
              <InputNumber
                v-model:value="model.port"
                :max="65535"
                :min="1"
                class="w-full"
                @change="formRef?.validateFields(['ip']).catch(() => {})"
              />
            </FormItem>
          </Col>
        </Row>
      </FormItem>

      <FormItem label="用户名" name="username">
        <div class="max-w-[420px]">
          <Input v-model:value="model.username" :maxlength="16" placeholder="请输入用户名">
            <template v-if="editingRow" #suffix>
              <Tooltip title="请使用root或具有sudo免密码权限的用户">
                <IconifyIcon
                  class="align-[-2px] text-gray-400"
                  icon="lucide:circle-help"
                />
              </Tooltip>
            </template>
          </Input>
        </div>
      </FormItem>

      <FormItem label="密码" name="password">
        <div class="max-w-[420px]">
          <Input.Password
            v-model:value="model.password"
            :maxlength="64"
            :visibility-toggle="false"
            placeholder="请输入密码"
          />
        </div>
      </FormItem>

      <FormItem
        label="安装时间同步服务"
        name="use_ntpd"
        extra="开启后，将对纳管主机安装ntpdate服务"
      >
        <Switch v-model:checked="model.use_ntpd" />
      </FormItem>

      <FormItem
        v-if="model.use_ntpd"
        label="时间同步服务器"
        name="ntpd_server"
      >
        <div class="max-w-[420px]">
          <Input
            v-model:value="model.ntpd_server"
            placeholder="例如: 192.168.10.10"
          />
        </div>
      </FormItem>

      <FormItem v-if="!editingRow" :colon="false">
        <!-- 纳管普通用户时的初始化脚本指引（旧前端 username extra 契约） -->
        <p class="text-xs text-gray-500">
          使用
          <span class="font-semibold">普通用户</span>
          纳管主机时，为确保正常安装服务，请
          <a href="/api/hosts/hostInit/" target="_blank">下载</a>
          主机初始化脚本，并手动执行
        </p>
      </FormItem>
    </Form>
  </Modal>
</template>
