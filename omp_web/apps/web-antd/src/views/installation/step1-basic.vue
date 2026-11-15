<script lang="ts" setup>
import type { FormInstance } from 'ant-design-vue/es/form';

import type { InstallationApi } from '#/api/installation';

import { computed, provide, reactive, shallowRef, useTemplateRef } from 'vue';

import { Button, Empty, Form, message } from 'ant-design-vue';

import { checkInstallInfo } from '#/api/installation';
import { useInstallationStore } from '#/store/installation';

import BasicInfoItem from './components/basic-info-item.vue';
import DependentInfoItem from './components/dependent-info-item.vue';
import SectionTitle from './components/section-title.vue';
import { INSTALL_BASIC_MODEL, INSTALL_DEPENDENT_MODEL } from './shared';

/**
 * Step1 基本信息：产品实例名称/各服务部署数量 + 依赖信息（复用实例或
 * 新装部署模式）。提交 checkInstallInfo 校验，通过后进入服务分布；
 * 校验失败逐项回写 error_msg 回显（旧 redux getStep1ChangeAction 契约）。
 *
 * 空产品分支（组件安装链路 basic=[]）：dependence[0]（jdk 基础环境）
 * 以基本信息样式展示，其余依赖在「依赖信息」区块，与旧实现一致。
 */
defineOptions({ name: 'InstallationStep1Basic' });

const props = defineProps<{
  /** 本次流程唯一键（query 直跳或入口交接） */
  uniqueKey: string;
}>();

const emit = defineEmits<{ next: [] }>();

const store = useInstallationStore();

const step1Data = computed(() => store.step1Data);

/** 是否存在产品（空产品走依赖前置展示分支） */
const hasBasic = computed(() => step1Data.value.basic.length > 0);

/** 完全没有安装数据（未从入口发起流程） */
const isEmpty = computed(
  () =>
    step1Data.value.basic.length === 0 && step1Data.value.dependence.length === 0,
);

/** 下一步可用性（入口返回 is_continue，存在 error_msg 的流程禁用）。
 *  用 computed 而非一次性快照：防未来路由开 keepAlive/实例复用时卡死 */
const isContinue = computed(() => store.step1Data.is_continue === true);

const loading = shallowRef(false);

const basicFormRef = useTemplateRef<FormInstance>('basicFormRef');
const dependentFormRef = useTemplateRef<FormInstance>('dependentFormRef');

/** 基本信息表单模型（键契约见 basic-info-item.vue 头注释） */
const basicFormModel = reactive<Record<string, any>>({});
/** 依赖信息表单模型（键契约见 render-num/render-arr/deploy-instance-row） */
const dependentFormModel = reactive<Record<string, any>>({});

provide(INSTALL_BASIC_MODEL, basicFormModel);
provide(INSTALL_DEPENDENT_MODEL, dependentFormModel);

/** 空产品分支的依赖分组：首项（基础环境）前置展示，其余进依赖信息 */
const headDependence = computed(() => step1Data.value.dependence[0]);
const restDependence = computed(() => step1Data.value.dependence.slice(1));

/**
 * 表单值 → 提交载荷（旧 dataProcessing 契约）：
 * basic 服务数量取 Number；依赖按是否复用实例拆 `${name}`（JSON 串还原）
 * 与 `${name}=num/name/vip`（数量型数字、模式型保留 key 字符串）。
 */
function buildQueryData(): {
  basic: Record<string, any>[];
  dependence: Record<string, any>[];
} {
  const basicVals = (hasBasic.value
    ? basicFormRef.value?.getFieldsValue()
    : {}) as Record<string, any>;
  const depVals = dependentFormRef.value?.getFieldsValue() as Record<
    string,
    any
  >;

  const basic = JSON.parse(
    JSON.stringify(step1Data.value.basic),
  ) as Record<string, any>[];
  const dependence = JSON.parse(
    JSON.stringify(step1Data.value.dependence),
  ) as Record<string, any>[];

  const nextBasic = basic.map((item) => {
    let clusterName = '';
    const servicesList = (item.services_list as Record<string, any>[]).map(
      (service) => {
        // 旧实现仅按 `=` 后段匹配服务名，跨产品同名服务会互相覆盖，此处收紧为全键匹配
        const key = `${item.name}=${service.name}`;
        const value = basicVals?.[key];
        return value !== undefined
          ? {
              name: service.name,
              version: service.version,
              deploy_mode: Number(value),
            }
          : { ...service };
      },
    );
    if (basicVals && basicVals[item.name] !== undefined) {
      clusterName = String(basicVals[item.name]);
    }
    return {
      name: item.name,
      version: item.version,
      cluster_name: clusterName,
      services_list: servicesList,
    };
  });

  const nextDependence = dependence.map((item) => {
    if (item.is_base_env) {
      return { ...item };
    }
    let existInstance: any = item.exist_instance;
    let deployMode: any = item.deploy_mode;
    let clusterName = '';
    let vip = '';
    let isUseExist = false;
    for (const [key, value] of Object.entries(depVals ?? {})) {
      const seg = key.split('=');
      if (seg[0] !== item.name) continue;
      if (seg.length === 1) {
        // 复用实例：`${name}` 为实例信息 JSON 串
        try {
          existInstance = JSON.parse(String(value));
          isUseExist = true;
        } catch {
          // 非法 JSON 忽略，保持原值
        }
      } else if (seg[1] === 'num') {
        clusterName = String(depVals[`${item.name}=name`] ?? '');
        vip = String(depVals[`${item.name}=vip`] ?? '');
        // 数字为部署数量，非数字为部署模式 key（single/master-slave 等）
        deployMode = Number.isNaN(Number(value)) ? value : Number(value);
      }
    }
    return {
      ...item,
      exist_instance: existInstance,
      deploy_mode: deployMode,
      cluster_name: clusterName,
      vip,
      is_use_exist: isUseExist,
    };
  });

  return { basic: nextBasic, dependence: nextDependence };
}

/** 校验失败回显：按 name 合并 error_msg 进 store（旧 getStep1ChangeAction） */
function applyCheckErrors(result: InstallationApi.Step1Data) {
  store.setStep1Data({
    basic: step1Data.value.basic.map((item) => {
      const matched = result.basic.find(
        (i) => i.error_msg && i.name === item.name,
      );
      return matched?.error_msg
        ? { ...item, error_msg: matched.error_msg }
        : item;
    }),
    dependence: step1Data.value.dependence.map((item) => {
      const matched = result.dependence.find(
        (i) => i.error_msg && i.name === item.name,
      );
      return matched?.error_msg
        ? { ...item, error_msg: matched.error_msg }
        : item;
    }),
    is_continue: step1Data.value.is_continue,
  });
}

async function handleNext() {
  try {
    await Promise.all([
      dependentFormRef.value?.validate(),
      hasBasic.value ? basicFormRef.value?.validate() : null,
    ]);
  } catch {
    message.warning('校验未通过');
    return;
  }
  loading.value = true;
  try {
    const result = await checkInstallInfo({
      unique_key: props.uniqueKey,
      data: buildQueryData(),
    });
    if (result?.data) {
      if (result.data.is_continue) {
        emit('next');
      } else {
        message.warning('校验未通过');
        applyCheckErrors(result.data);
      }
    }
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <!-- 满高容器下的滚动层：内容超出视口时内部滚动 -->
  <div v-if="isEmpty" class="min-h-0 flex-1 overflow-y-auto">
    <Empty
      class="mt-10"
      description="暂无安装数据，请从应用商店「更多」菜单发起批量安装"
    />
  </div>
  <template v-else>
    <div class="min-h-0 flex-1 overflow-y-auto">
    <template v-if="hasBasic">
    <!-- 基本信息 -->
    <section class="mt-5 bg-card p-2.5">
      <SectionTitle title="基本信息" />
      <div class="pb-10 pl-5 pt-2.5">
        <Form ref="basicFormRef" :model="basicFormModel" name="basic">
          <BasicInfoItem
            v-for="item in step1Data.basic"
            :key="item.name"
            :data="item"
          />
        </Form>
      </div>
    </section>

    <!-- 依赖信息 -->
    <section class="mt-5 bg-card p-2.5">
      <SectionTitle title="依赖信息" />
      <div class="pb-10 pl-5 pt-2.5">
        <Form
          ref="dependentFormRef"
          :model="dependentFormModel"
          layout="vertical"
          name="dependent"
        >
          <DependentInfoItem
            v-for="item in step1Data.dependence"
            :key="item.name"
            :data="item"
          />
        </Form>
      </div>
    </section>

    </template>

    <!-- 空产品分支（组件安装链路）：依赖首项前置到基本信息，单一 Form 覆盖两个区块 -->
  <Form
    v-else
    ref="dependentFormRef"
    :model="dependentFormModel"
    layout="vertical"
    name="dependent"
  >
    <section class="mt-5 bg-card p-2.5">
      <SectionTitle title="基本信息" />
      <div class="pb-10 pl-5 pt-2.5">
        <DependentInfoItem
          v-if="headDependence"
          :key="headDependence.name"
          :data="headDependence"
          is-base-env
        />
      </div>
    </section>

    <section class="mt-5 bg-card p-2.5">
      <SectionTitle title="依赖信息" />
      <div class="pb-10 pl-5 pt-2.5">
        <p v-if="restDependence.length === 0" class="pl-1">无</p>
        <template v-else>
          <DependentInfoItem
            v-for="item in restDependence"
            :key="item.name"
            :data="item"
          />
        </template>
      </div>
    </section>

    </Form>
    </div>

    <!-- 步骤操作条（滚动层外常驻底部，内容滚动时始终可见） -->
    <div class="mt-5 flex shrink-0 justify-end bg-card py-6 pr-20">
      <Button
        :disabled="!isContinue"
        :loading="loading"
        html-type="button"
        type="primary"
        @click="handleNext"
      >
        下一步
      </Button>
    </div>
  </template>
</template>
