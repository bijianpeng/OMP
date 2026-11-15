<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue/es/form';

import type { InstallationApi } from '#/api/installation';

import { onMounted, provide, reactive, shallowRef, useTemplateRef, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Button, Checkbox, Form, Input, message, Spin } from 'ant-design-vue';

import {
  createInstallPlan,
  getInstallArgsByIp,
  getInstallHostRange,
} from '#/api/installation';

import ServiceConfigItem from './components/service-config-item.vue';
import { INSTALL_CONFIG_MODEL } from './shared';

/**
 * Step3 修改配置：左侧主机范围列表（可搜索），右侧逐服务安装参数/端口
 * 配置（按 ip 懒加载 + 前端缓存，切回不重复请求）。切主机前把当前表单
 * 值合并进缓存（旧 redux getStep3ServiceChangeAction 契约）。
 * 提交 createInstallPlan：当前表单必填经 antdv 校验，其余主机走
 * 非空校验（nonNullCheck 契约，vip 豁免），失败逐字段回显。
 */
defineOptions({ name: 'InstallationStep3Config' });

const props = defineProps<{
  /** 本次流程唯一键 */
  uniqueKey: string;
}>();

const emit = defineEmits<{
  next: [];
  prev: [];
}>();

/** 服务参数请求 loading */
const loading = shallowRef(false);
const loadingIp = shallowRef(false);

/** 本次安装全部主机范围 */
const ipList = shallowRef<string[]>([]);
/** 搜索过滤后的主机列表 */
const currentIpList = shallowRef<string[]>([]);
/** 当前配置的主机 */
const checkIp = shallowRef('');

/** 搜索关键字 */
const searchIp = shallowRef('');

/** 指定本次安装服务运行用户 */
const useRunUser = shallowRef(false);
const runUser = shallowRef('');

/**
 * 各主机服务配置缓存（旧 redux step3Data 契约）：
 * ip → 服务数组（install_args/ports 的 default 即当前值）
 */
const cache = reactive<Record<string, InstallationApi.ConfigService[]>>({});

/**
 * 后端校验失败回显（旧 redux step3ErrorData 契约）：
 * ip → 服务名 → 参数 key → 失败原因
 */
const errInfo = reactive<
  Record<string, Record<string, Record<string, string>>>
>({});

const serviceFormRef = useTemplateRef<FormInstance>('serviceFormRef');
/** 扁平表单模型：键 = `${服务名}=${参数key}` */
const formModel = reactive<Record<string, any>>({});

provide(INSTALL_CONFIG_MODEL, formModel);

// ── 数据加载 ────────────────────────────────────────────────────────

onMounted(async () => {
  loadingIp.value = true;
  try {
    const result = await getInstallHostRange(props.uniqueKey);
    const list = result?.data ?? [];
    ipList.value = list;
    currentIpList.value = [...list];
    checkIp.value = list[0] ?? '';
  } catch {
    // 全局拦截器已提示
  } finally {
    loadingIp.value = false;
  }
});

/** 当前表单值合并进指定主机缓存（旧 redux 按键分发的等价实现） */
function syncFormToCache(ip: string) {
  const services = cache[ip];
  if (!services) return;
  for (const [key, value] of Object.entries(formModel)) {
    const [serviceName, argKey] = key.split('=');
    if (argKey === undefined) continue;
    const service = services.find((item) => item.name === serviceName);
    if (!service) continue;
    for (const group of ['install_args', 'ports'] as const) {
      const arg = service[group]?.find((item) => item.key === argKey);
      if (arg) arg.default = value;
    }
  }
}

/** 用缓存值重建当前表单模型（切主机时清空重建，互不串值） */
function loadFormModel(ip: string) {
  for (const key of Object.keys(formModel)) {
    delete formModel[key];
  }
  for (const service of cache[ip] ?? []) {
    for (const arg of [...service.install_args, ...service.ports]) {
      formModel[`${service.name}=${arg.key}`] = arg.default ?? '';
    }
  }
}

async function loadIpConfig(ip: string) {
  if (!ip) return;
  if (!cache[ip]) {
    loading.value = true;
    try {
      const result = await getInstallArgsByIp({
        ip,
        unique_key: props.uniqueKey,
      });
      if (result?.data) {
        cache[ip] = result.data;
      } else {
        message.warning(result?.err_msg ?? result?.error_msg ?? '参数查询失败');
      }
    } catch {
      // 全局拦截器已提示
    } finally {
      loading.value = false;
    }
  }
  loadFormModel(ip);
}

// 切主机：先落缓存再加载新值（旧点击时逐键分发 redux 契约，
// 顺带修复旧搜索切换不落缓存的遗漏）
watch(checkIp, (ip, oldIp) => {
  if (oldIp) syncFormToCache(oldIp);
  loadIpConfig(ip);
});

// ── 主机搜索 ────────────────────────────────────────────────────────

function handleSearch() {
  if (searchIp.value) {
    const result = ipList.value.filter((ip) => ip.includes(searchIp.value));
    currentIpList.value = result;
    if (result.length > 0) {
      checkIp.value = result[0] ?? '';
    }
  } else {
    currentIpList.value = [...ipList.value];
    checkIp.value = ipList.value[0] ?? '';
  }
}

function handleSearchChange(value: string) {
  searchIp.value = value;
  if (!value) {
    currentIpList.value = [...ipList.value];
    checkIp.value = ipList.value[0] ?? '';
  }
}

// ── 提交 ────────────────────────────────────────────────────────────

/** 非空校验（旧 nonNullCheck 契约）：校验其它主机的缓存数据，vip 豁免 */
function nonNullCheck() {
  const result: Record<string, Record<string, Record<string, string>>> = {};
  const data = { ...cache };
  // 当前页字段由 antdv 校验覆盖，其余主机走此处
  delete data[checkIp.value];
  for (const [ip, services] of Object.entries(data)) {
    for (const service of services) {
      for (const arg of [...service.install_args, ...service.ports]) {
        if (!arg.default && arg.key !== 'vip') {
          const ipEntry = (result[ip] = result[ip] ?? {});
          const svcEntry = (ipEntry[service.name] = ipEntry[service.name] ?? {});
          svcEntry[arg.key] = `请输入${arg.name}`;
        }
      }
    }
  }
  return result;
}

/** 后端校验失败明细 → errInfo 结构（旧 getErrorInfo 契约） */
function buildErrorInfo(
  data: InstallationApi.InstallPlanResult['data'],
): Record<string, Record<string, Record<string, string>>> {
  const result: Record<string, Record<string, Record<string, string>>> = {};
  for (const [ip, services] of Object.entries(data ?? {})) {
    for (const service of services) {
      for (const arg of [...service.install_args, ...service.ports]) {
        if (arg.check_flag === false && arg.error_msg) {
          const ipEntry = (result[ip] = result[ip] ?? {});
          const svcEntry = (ipEntry[service.name] = ipEntry[service.name] ?? {});
          svcEntry[arg.key] = arg.error_msg;
        }
      }
    }
  }
  return result;
}

async function handleInstall() {
  try {
    await serviceFormRef.value?.validate();
  } catch {
    message.warning('校验未通过，请检查');
    return;
  }
  const emptyCheck = nonNullCheck();
  if (Object.keys(emptyCheck).length > 0) {
    message.warning('校验未通过，请检查');
    // 整体替换语义（对齐旧 redux）：先清残留再写入本次校验结果
    Object.keys(errInfo).forEach((key) => delete errInfo[key]);
    Object.assign(errInfo, emptyCheck);
    return;
  }
  loading.value = true;
  try {
    // 当前表单值先落缓存，再按主机范围组完整载荷（未访问主机空数组）
    syncFormToCache(checkIp.value);
    const data: Record<string, Record<string, any>[]> = {};
    for (const ip of ipList.value) {
      data[ip] = cache[ip] ?? [];
    }
    const result = await createInstallPlan({
      unique_key: props.uniqueKey,
      run_user: runUser.value,
      data,
    });
    if (result) {
      if (result.is_continue) {
        emit('next');
      } else {
        message.warning(result.error_msg || '校验未通过，请检查');
        Object.keys(errInfo).forEach((key) => delete errInfo[key]);
        Object.assign(errInfo, buildErrorInfo(result.data));
      }
    }
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

function argErrorsOf(serviceName: string) {
  return errInfo[checkIp.value]?.[serviceName];
}
</script>

<template>
  <!-- 运行用户 -->
  <div class="mt-5 flex shrink-0 items-center bg-card py-2.5 pl-[30px] pr-2.5">
    <div class="w-[220px]">
      <Checkbox
        :checked="useRunUser"
        @change="(e: any) => { useRunUser = e.target.checked; if (!e.target.checked) runUser = ''; }"
      >
        指定本次安装服务运行用户
      </Checkbox>
    </div>
    <Input
      v-model:value="runUser"
      :disabled="!useRunUser"
      placeholder="请输入本次安装服务运行的非root用户"
      style="width: 300px"
    />
  </div>

  <!-- 主机列表 + 服务配置（满高内部滚动） -->
  <div class="mt-4 flex min-h-0 flex-1 bg-card">
    <div class="flex w-[240px] shrink-0 flex-col">
      <div class="p-[15px_5px_10px]">
        <Input
          v-model:value="searchIp"
          allow-clear
          placeholder="搜索IP地址"
          @blur="handleSearch"
          @change="(e: any) => handleSearchChange(e.target.value)"
          @press-enter="handleSearch"
        >
          <template v-if="!searchIp" #suffix>
            <IconifyIcon class="text-[#b6b6b6]" icon="lucide:search" />
          </template>
        </Input>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto">
        <Spin :spinning="loadingIp">
          <template v-if="currentIpList.length === 0">
            <div class="h-[100px]"></div>
          </template>
          <template v-else>
            <div
              v-for="ip in currentIpList"
              :key="ip"
              class="flex cursor-pointer justify-between"
            >
              <div
                class="flex-1 py-[5px] pl-[30px]"
                :class="checkIp === ip ? 'bg-[#edf8fe] dark:bg-primary/15' : ''"
                :style="{
                  color: errInfo[ip]
                    ? 'red'
                    : checkIp === ip
                      ? '#4986f7'
                      : undefined,
                }"
                @click="checkIp = ip"
              >
                {{ ip }}
              </div>
              <div
                v-if="errInfo[ip]"
                class="w-[30px] py-[5px] text-[red]"
                :class="checkIp === ip ? 'bg-[#edf8fe] dark:bg-primary/15' : ''"
              >
                <IconifyIcon icon="lucide:circle-alert" />
              </div>
            </div>
          </template>
        </Spin>
      </div>
    </div>

    <div class="min-h-0 min-w-0 flex-1 overflow-y-auto border-l border-border">
      <Spin :spinning="loading" tip="数据加载中...">
        <div v-if="(cache[checkIp] ?? []).length === 0" class="h-[300px]"></div>
        <Form
          v-else
          ref="serviceFormRef"
          :model="formModel"
          :label-col="{ span: 8 }"
          name="config"
        >
          <ServiceConfigItem
            v-for="item in cache[checkIp]"
            :key="item.name"
            :arg-errors="argErrorsOf(item.name)"
            :service="item"
          />
        </Form>
      </Spin>
    </div>
  </div>

  <div class="mt-5 flex shrink-0 items-center justify-between bg-card py-6 pl-6 pr-8">
    <div>分布主机数量: {{ ipList.length }}台</div>
    <div>
      <Button html-type="button" type="primary" @click="emit('prev')">
        上一步
      </Button>
      <Button
        class="ml-2.5"
        :loading="loading"
        html-type="button"
        type="primary"
        @click="handleInstall"
      >
        开始安装
      </Button>
    </div>
  </div>
</template>
