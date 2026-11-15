<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue/es/form';

import type { InstallApi } from '#/api/app-store-install';

import { computed, onUnmounted, provide, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Button, Form, FormItem, Select, Spin, Steps, Tooltip, message } from 'ant-design-vue';

import {
  executeInstall,
  queryComponentEntrance,
  queryInstallHistory,
} from '#/api/app-store-install';
import { getIpList } from '#/api/hosts';

import DependEntryRow from './components/depend-entry-row.vue';
import DependServicePanel from './components/depend-service-panel.vue';
import InstallLogSection from './components/install-log-section.vue';
import MainServicePanel from './components/main-service-panel.vue';
import SectionTitle from './components/section-title.vue';
import {
  INSTALL_FIELD_ERRORS,
  defaultInstanceName,
  findSameIpInstances,
  installArgKey,
  markReuseServices,
  parseDepInstallArgs,
  parseIpInstance,
  parameterCreate,
  portArgKey,
} from './shared';

/**
 * 组件安装向导（/application_management/app_store/component_installation/:name）。
 * 三步：基本信息（版本/集群模式 + 依赖信息）→ 部署信息（主机/实例名 + 参数）→
 * 开始安装（executeInstall 校验下发 + installHistory 2s 轮询进度）。
 * 旧实现 omp_web/src/pages/AppStore/config/ComponentInstallation.js 契约迁移。
 */
defineOptions({ name: 'ComponentInstallation' });

const route = useRoute();
const router = useRouter();

/** 路由参数 :name（组件名，vue-router 已解码） */
const name = computed(() => String(route.params.name ?? ''));

const formRef = ref<FormInstance>();
/** 扁平表单模型：键为 `install|owner|{json}` 等契约键（shared.ts） */
const formModel = reactive<Record<string, any>>({});
/** 后端校验失败回填的字段错误（扁平键 → check_msg） */
const fieldErrors = reactive<Record<string, string>>({});
provide(INSTALL_FIELD_ERRORS, fieldErrors);

const pageLoading = ref(false);
/** 开始安装请求进行中 */
const loading = ref(false);
/** 0 基本信息 1 部署信息 2 开始安装 */
const stepNum = ref(0);

const dataSource = ref<InstallApi.ComponentEntranceItem[]>([]);
const versionCurrent = ref('');
/** 依赖缺失提示后禁用「下一步」（process_continue 契约） */
const processContinue = ref(true);

const ipListSource = ref<string[]>([]);
/** IP 无既有实例时需随装基础依赖（jdk） */
const showDep = ref(false);

/** 「查看更多配置」展开状态（键：主服务名/依赖服务名/参数名） */
const isOpen = reactive<Record<string, boolean>>({ [name.value]: false });
/** Step3 日志展开状态（键：service_name） */
const isDetailOpen = reactive<Record<string, boolean>>({});

/** Step1 快照（集群模式提交时取值） */
const step1Data = ref<Record<string, any>>({});
const step3Data = ref<InstallApi.InstallHistoryItem>();

/** 需随装的依赖项（旧 install_servicesRef：多项时末项覆盖，照旧契约） */
let installDep: InstallApi.DependenceItem | null = null;
/** 复用的既有实例列表（旧 use_exist_servicesRef） */
let useExistServices: Record<string, any>[] = [];

let installTimer: null | ReturnType<typeof setTimeout> = null;
/** Step3 日志区块实例（滚动到底用） */
const logSections: InstanceType<typeof InstallLogSection>[] = [];

const current = computed(() =>
  dataSource.value.find((item) => item.app_version === versionCurrent.value),
);

const deployModeOptions = computed(() =>
  (current.value?.deploy_mode ?? []).map((item) => ({
    label: item.name,
    value: JSON.stringify(item),
  })),
);

const versionOptions = computed(() =>
  dataSource.value.map((item) => ({
    label: item.app_version,
    value: item.app_version,
  })),
);

// ── 入口数据 ────────────────────────────────────────────────────────

/** 依赖缺失阻断提示（process_continue=false 时禁下一步） */
function checkProcessContinue(item?: InstallApi.ComponentEntranceItem) {
  if (item && item.process_continue === false) {
    processContinue.value = false;
    message.warning(item.process_message ?? '');
    return false;
  }
  processContinue.value = true;
  return true;
}

async function fetchData() {
  pageLoading.value = true;
  try {
    const data = await queryComponentEntrance(name.value);
    dataSource.value = data ?? [];
    // 详情页「安装」携带的版本（F3 衔接：?version=），未命中时兜底首条
    const queryVersion = String(route.query.version ?? '');
    const initial =
      dataSource.value.find((item) => item.app_version === queryVersion) ??
      dataSource.value[0];
    // 旧实现仅校验首个版本的安装可用性，切换版本时再校验选中版本
    checkProcessContinue(initial);
    versionCurrent.value = initial?.app_version ?? '';
    formModel.version = initial?.app_version ?? '';
    formModel.clusterMode = JSON.stringify(initial?.deploy_mode?.[0] ?? {});
  } catch {
    // 全局拦截器已提示
  } finally {
    pageLoading.value = false;
  }
}

function onVersionChange(value: string) {
  versionCurrent.value = value;
  checkProcessContinue(
    dataSource.value.find((item) => item.app_version === value),
  );
}

// ── 依赖随装判定（旧 jdkHandleInitData 契约） ───────────────────────

/**
 * 逐项判定依赖是否需随装：IP 无既有实例（is_base_env 且 instance_info
 * 无同 IP 项）时装入 installDep 并设依赖表单默认值；末项覆盖前项为旧实现
 * 原行为（实际场景 app_dependence 仅 jdk 一项）。
 */
function initDependence(deps: InstallApi.DependenceItem[] = [], ip: string) {
  for (const dep of deps) {
    const same = findSameIpInstances(dep, ip);
    if (Array.isArray(same) && same.length === 0) {
      showDep.value = true;
      installDep = { ...dep };
      useExistServices = [];
      isOpen[dep.name] = isOpen[dep.name] ?? false;
      for (const item of dep.app_install_args ?? []) {
        isOpen[item.name] = false;
        formModel[installArgKey(dep.name, item)] = item.default ?? '';
      }
      for (const item of dep.app_port ?? []) {
        isOpen[item.name] = false;
        formModel[portArgKey(dep.name, item)] = item.default ?? '';
      }
      formModel[`${dep.name}|ip`] = ip;
      formModel[`${dep.name}|instanceName`] =
        defaultInstanceName(dep.name, ip);
    } else {
      showDep.value = false;
      useExistServices = same ? [same[0] as Record<string, any>] : [];
      installDep = null;
    }
  }
}

async function fetchIpList() {
  try {
    const data = await getIpList();
    ipListSource.value = data ?? [];
    const firstIp = ipListSource.value[0] ?? '';
    formModel.ip = firstIp;
    formModel.instanceName = defaultInstanceName(name.value, firstIp);
    initDependence(current.value?.app_dependence, firstIp);
  } catch {
    // 全局拦截器已提示
  }
}

/** Step0 → Step1：设主服务参数默认值 + 快照 Step1 数据 + 拉主机列表 */
function goStep2() {
  const cur = current.value;
  const owner = cur?.app_name ?? '';
  for (const item of cur?.app_install_args ?? []) {
    formModel[installArgKey(owner, item)] = item.default ?? '';
  }
  for (const item of cur?.app_port ?? []) {
    formModel[portArgKey(owner, item)] = item.default ?? '';
  }
  step1Data.value = { ...formModel };
  fetchIpList();
  stepNum.value = 1;
}

/** 主服务切换主机：实例名重置 + 依赖随装重判定（旧 onChange 契约） */
function onMainIpChange(ip: string) {
  formModel.instanceName = defaultInstanceName(name.value, ip);
  initDependence(current.value?.app_dependence, ip);
}

// ── 提交安装 ────────────────────────────────────────────────────────

/** 校验失败/后端校验不通过时展开全部面板（暴露出错字段） */
function openAllPanels() {
  for (const key of Object.keys(isOpen)) {
    isOpen[key] = true;
  }
  const firstDep = current.value?.app_dependence?.[0];
  if (firstDep) isOpen[firstDep.name] = true;
}

/** 后端校验失败：逐字段回填 check_msg（键编码与渲染侧一致） */
function applyCheckErrors(data: InstallApi.ExecuteInstallResult) {
  openAllPanels();
  const existFirst = data.use_exist_services?.[0];
  if (existFirst && existFirst.check_flag === false) {
    message.warning(existFirst.check_msg ?? '');
  }
  data.install_services?.forEach((item, idx) => {
    if (item.check_flag === false && item.check_msg) {
      fieldErrors[idx === 0 ? 'instanceName' : `${item.name}|instanceName`] =
        item.check_msg;
    }
    item.app_port?.forEach((port) => {
      if (port.check_flag === false) {
        fieldErrors[portArgKey(item.name, port)] = port.check_msg ?? '';
      }
    });
    item.app_install_args?.forEach((arg) => {
      if (arg.check_flag === false) {
        fieldErrors[installArgKey(item.name, arg)] = arg.check_msg ?? '';
      }
    });
  });
}

async function submitInstall() {
  let values: Record<string, any>;
  try {
    await formRef.value?.validate();
  } catch {
    openAllPanels();
    return;
  }
  values = { ...formModel };
  // 清上一轮后端校验回填的字段错误（旧版 validate 后自动清除的等价行为）
  for (const key of Object.keys(fieldErrors)) {
    delete fieldErrors[key];
  }
  loading.value = true;
  try {
    const cur = current.value;
    const owner = cur?.app_name ?? '';
    // 依赖需随装时补充其 ip/实例名/参数（app_port 恒空数组，旧契约）
    const installServices: Record<string, any>[] = [];
    if (installDep) {
      const dep = installDep;
      const depArgs = parseDepInstallArgs(values, dep.name);
      const ipInstance = parseIpInstance(values, dep.name);
      installServices.push({
        ...dep,
        app_install_args: (dep.app_install_args ?? []).map((item) => ({
          ...item,
          default: depArgs[installArgKey(dep.name, item)],
        })),
        app_port: [],
        ip: ipInstance.ip ?? '',
        service_instance_name: ipInstance.instanceName ?? '',
      });
    }
    const result = await executeInstall({
      install_services: [
        {
          name: owner,
          version: versionCurrent.value,
          ip: values.ip,
          app_install_args: parameterCreate(values, 'install', owner),
          app_port: parameterCreate(values, 'port', owner),
          service_instance_name: values.instanceName,
          deploy_mode: JSON.parse(step1Data.value.clusterMode ?? '{}'),
        },
        ...installServices,
      ],
      install_type: 0,
      use_exist_services: markReuseServices(useExistServices),
    });
    if (result && result.install_services) {
      if (!result.is_valid_flag) {
        applyCheckErrors(result);
      } else {
        queryInstallationInfo(result.operation_uuid ?? '');
        stepNum.value = 2;
      }
    }
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

// ── Step3 进度轮询（2s，install_status 0/1 时继续） ─────────────────

function scrollLogs() {
  for (const section of logSections) {
    section?.scrollToBottom();
  }
}

function queryInstallationInfo(operateId: string) {
  queryInstallHistory(operateId)
    .then((data) => {
      const item = data?.[0];
      if (!item) return;
      step3Data.value = item;
      // 仅首轮初始化展开状态（保留用户已展开项）
      if (!installTimer) {
        for (const detail of item.detail_lst ?? []) {
          isDetailOpen[detail.service_name] =
            isDetailOpen[detail.service_name] ?? false;
        }
      }
      if (item.install_status === 0 || item.install_status === 1) {
        installTimer = setTimeout(() => {
          installTimer = null;
          queryInstallationInfo(operateId);
        }, 2000);
      }
      scrollLogs();
    })
    .catch(() => {
      // 全局拦截器已提示
      scrollLogs();
    });
}

function finish() {
  router.push('/application_management/service_management');
}

function goBack() {
  router.back();
}

/**
 * 完全重置向导状态。KeepAlive 按组件名缓存，同组件不同 :name 的 tab
 * 共享实例（setup 不重跑），路由参数变化时必须重置并重新拉数据，
 * 对齐旧实现「每次进入页面均为全新安装流程」的行为。
 */
function resetState() {
  if (installTimer) {
    clearTimeout(installTimer);
    installTimer = null;
  }
  dataSource.value = [];
  versionCurrent.value = '';
  processContinue.value = true;
  stepNum.value = 0;
  ipListSource.value = [];
  showDep.value = false;
  installDep = null;
  useExistServices = [];
  step1Data.value = {};
  step3Data.value = undefined;
  for (const key of Object.keys(formModel)) {
    delete formModel[key];
  }
  for (const key of Object.keys(fieldErrors)) {
    delete fieldErrors[key];
  }
  for (const key of Object.keys(isOpen)) {
    delete isOpen[key];
  }
  isOpen[name.value] = false;
  for (const key of Object.keys(isDetailOpen)) {
    delete isDetailOpen[key];
  }
  logSections.length = 0;
}

watch(
  () => route.params.name,
  (newName, oldName) => {
    if (newName && newName !== oldName) {
      resetState();
      fetchData();
    }
  },
);

onUnmounted(() => {
  if (installTimer) clearTimeout(installTimer);
});

fetchData();
</script>

<template>
  <Page>
    <!-- 满高纵向布局：包裹层 min-h-full（Page 内容区经 h-full/flex-1 链为视口
         定高）+ 中段 flex-1，内容不足一屏时操作条贴内容区可视底部；内容超高时
         主区滚动，操作条 sticky 钉底（包含块为满高包裹层） -->
    <div class="flex min-h-full flex-col">
    <!-- 顶部导航条：返回 + 名称 + 步骤条 -->
    <div
      class="flex h-[50px] shrink-0 items-center justify-between bg-card pl-5 pr-[50px]"
    >
      <div class="flex items-center text-base">
        <Tooltip title="返回">
          <Button
            class="border-0 bg-transparent px-1 shadow-none"
            size="small"
            @click="goBack"
          >
            <template #icon>
              <IconifyIcon class="text-base" icon="lucide:arrow-left" />
            </template>
          </Button>
        </Tooltip>
        <span class="pl-3">{{ name }}</span>
      </div>
      <!-- antdv Steps 根元素自带无层级 width:100%，Tailwind 宽度类会被压过，需内联 style -->
      <Steps
        :current="stepNum"
        :style="{ width: '480px' }"
        size="small"
      >
        <Steps.Step title="基本信息" />
        <Steps.Step title="部署信息" />
        <Steps.Step title="开始安装" />
      </Steps>
      <div class="w-[40px]"></div>
    </div>

    <!-- 中段 flex-1：内容不足一屏时撑开把操作条压到可视底部（antdv Spin 不透传
         class 到根元素，flex-1 需包在外层 div 上） -->
    <div class="flex-1">
    <Spin :spinning="pageLoading">
      <!-- 整页单一 Form 上下文：承载全部扁平键字段与校验（step3 无表单不包裹） -->
      <Form v-if="stepNum < 2" ref="formRef" :model="formModel">
        <!-- 第一步：基本信息 + 依赖信息 -->
        <div v-if="stepNum === 0">
          <section class="mt-5 bg-card p-2.5">
            <SectionTitle title="基本信息" />
            <div class="flex items-center gap-6 pb-10 pl-5 pt-2.5">
              <FormItem label="选择版本" name="version">
                <Select
                  v-model:value="formModel.version"
                  class="!w-[200px]"
                  :options="versionOptions"
                  @change="(v: any) => onVersionChange(String(v))"
                />
              </FormItem>
              <FormItem label="集群模式" name="clusterMode">
                <Select
                  v-model:value="formModel.clusterMode"
                  class="!w-[200px]"
                  :options="deployModeOptions"
                />
              </FormItem>
            </div>
          </section>

          <section class="mt-5 bg-card p-2.5">
            <SectionTitle title="依赖信息" />
            <div class="pb-10 pl-5 pt-2.5">
              <p v-if="(current?.app_dependence ?? []).length === 0">无</p>
              <template v-else>
                <!-- 列头与 DependEntryRow 数据行同宽（flex-2/flex-3/flex-[15]/flex-2），风格对齐商店详情页依赖表 -->
                <div
                  class="flex pr-20 text-muted-foreground text-sm"
                >
                  <div class="flex-2">依赖名称</div>
                  <div class="flex-3">版本</div>
                  <div class="flex-[15]"></div>
                  <div class="flex-2"></div>
                </div>
                <DependEntryRow
                  v-for="item in current?.app_dependence"
                  :key="item.name"
                  :data="item"
                />
              </template>
            </div>
          </section>
        </div>

        <!-- 第二步：部署信息（主服务 + 依赖随装） -->
        <div v-else>
          <MainServicePanel
            :args="current?.app_install_args"
            :form-model="formModel"
            :ip-list="ipListSource"
            :open="!!isOpen[name]"
            :owner="current?.app_name ?? ''"
            :ports="current?.app_port"
            :title="name"
            @ip-change="onMainIpChange"
            @toggle="isOpen[name] = !isOpen[name]"
          />

          <template v-if="showDep">
            <DependServicePanel
              v-for="dep in current?.app_dependence"
              :key="dep.name"
              :dep="dep"
              :form-model="formModel"
              :ip-list="ipListSource"
              :open="!!isOpen[dep.name]"
              @toggle="isOpen[dep.name] = !isOpen[dep.name]"
            />
          </template>
        </div>
      </Form>

      <!-- 第三步：安装进度日志（无表单上下文） -->
      <template v-else>
        <InstallLogSection
          v-for="(item, idx) in step3Data?.detail_lst"
          :key="item.service_instance_name"
          :ref="(el: any) => (logSections[idx] = el)"
          :item="item"
          :open="!!isDetailOpen[item.service_name]"
          @toggle="isDetailOpen[item.service_name] = !isDetailOpen[item.service_name]"
        />
      </template>
    </Spin>
    </div>

    <!-- 步骤操作条（Spin 与 Form 之外，避免加载遮罩与 form 事件链干扰交互；
         不足一屏时由满高 flex 布局贴底，超高滚动时 sticky 钉底始终可见） -->
    <div v-if="stepNum === 0" class="sticky bottom-0 z-10 mt-5 flex shrink-0 justify-between border-t border-border bg-card py-6 pl-6 pr-20">
      <div></div>
      <Button
        :disabled="!processContinue"
        html-type="button"
        type="primary"
        @click="goStep2"
      >
        下一步
      </Button>
    </div>
    <div v-else-if="stepNum === 1" class="sticky bottom-0 z-10 mt-5 flex shrink-0 justify-between border-t border-border bg-card py-6 pl-6 pr-10">
      <div class="flex items-center">分布主机数量: 1台</div>
      <div>
        <Button class="mr-[15px]" html-type="button" type="primary" @click="stepNum = 0">
          上一步
        </Button>
        <Button :loading="loading" html-type="button" type="primary" @click="submitInstall">
          开始安装
        </Button>
      </div>
    </div>
    <div v-else class="sticky bottom-0 z-10 mt-5 flex shrink-0 justify-between border-t border-border bg-card py-6 pl-6 pr-20">
      <div class="flex items-center">
        {{ step3Data?.install_status_msg }}
        <IconifyIcon
          v-if="
            step3Data &&
            (step3Data.install_status === 0 || step3Data.install_status === 1)
          "
          class="ml-2.5 animate-spin text-xl"
          icon="lucide:loader-circle"
        />
      </div>
      <Button html-type="button" type="primary" @click="finish">完成</Button>
    </div>
    </div>
  </Page>
</template>
