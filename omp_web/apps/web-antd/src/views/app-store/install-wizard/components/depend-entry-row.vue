<script lang="ts" setup>
import type { DependenceItem } from '#/api/app-store-install';

import { computed, ref } from 'vue';

import { Checkbox, FormItem, Input, Select } from 'ant-design-vue';

/**
 * Step1 依赖信息行（旧 RenderComDependence 契约）：
 * - 基础环境（jdk 等）：仅展示名称/版本 + 禁用勾选「安装依赖」；
 * - 无集群且无实例：展示集群模式选择 + 非单实例时的集群名称输入；
 * - 存在实例/集群：默认「复用」+ 实例选择，取消复用切集群模式。
 *
 * 本行的选择值（集群模式/集群名称/复用实例）在旧实现中不进入
 * executeInstall 载荷（依赖复用/新装实际由第二步的 IP 判定决定），
 * 故此处用组件内局部状态承载，不挂页面共享 form。
 */
defineOptions({ name: 'DependEntryRow' });

const props = defineProps<{ data: DependenceItem }>();

/** 集群模式（旧版取 deploy_mode 首项序列化值为初始值；无可选项时置 undefined 以显示 placeholder） */
const deployMode = ref<string | undefined>(
  props.data.deploy_mode?.[0]
    ? JSON.stringify(props.data.deploy_mode[0])
    : undefined,
);

/** 是否复用已有实例 */
const isMultiplexing = ref(true);

/** 复用时选中的实例/集群标识：`single|{json}` / `cluster|{json}` */
const selectedInstance = ref('');

/** 无集群且无实例时直接走新装 UI（旧 RenderClusterDom 分支，无复用开关） */
const hasExisting = computed(
  () =>
    (props.data.cluster_info?.length ?? 0) > 0 ||
    (props.data.instance_info?.length ?? 0) > 0,
);

/** 实例/集群合并选项（旧版拼接后统一字段契约） */
const instanceOptions = computed(() => {
  const cluster = (props.data.cluster_info ?? []).map(
    (item) => `cluster|${JSON.stringify(item)}`,
  );
  const instances = (props.data.instance_info ?? []).map(
    (item) => `single|${JSON.stringify(item)}`,
  );
  const ids = [...cluster, ...instances];
  if (!selectedInstance.value && ids[0]) selectedInstance.value = ids[0];
  return ids;
});

function optionLabel(id: string): string {
  try {
    const item = JSON.parse(id.split('|')[1] ?? '{}') as Record<string, any>;
    // 集群项展示 cluster_name，实例项展示 service_instance_name
    return String(item.cluster_name ?? item.service_instance_name ?? '');
  } catch {
    return '';
  }
}

/** 非单实例模式时需填写集群名称（旧版按序列化串比对） */
const isSingleMode = computed(
  () => deployMode.value === '{"key":"single","name":"单实例"}',
);

/** 集群名称默认值：`{服务名}-{6 位随机大写字母数字}`（旧 randomNumber 契约） */
const randomName = (() => {
  const str = 'QWERTYUIOPLKJHGFDSAZXCVBNM123456790';
  let r = '';
  for (let i = 0; i < 6; i++) {
    r += str[Math.floor(Math.random() * str.length)];
  }
  return r;
})();
const clusterName = ref(`${props.data.name}-${randomName}`);
</script>

<template>
  <!-- 基础环境依赖：仅展示，固定勾选安装 -->
  <div v-if="data.is_base_env" class="mb-5 flex pr-20">
    <div class="flex-2">{{ data.name }}</div>
    <div class="flex-3">{{ data.version }}</div>
    <div class="flex-[15]"></div>
    <div class="flex-2 text-[#c2c2c2]">
      <Checkbox :checked="true" class="mr-2.5" disabled />
      安装依赖
    </div>
  </div>

  <div v-else class="mb-5 flex items-center pr-20">
    <div class="flex-2">{{ data.name }}</div>
    <div class="flex-3">{{ data.version }}</div>

    <template v-if="hasExisting && isMultiplexing">
      <!-- 复用：选择已有实例/集群（行内带冒号 label，与基本信息卡 FormItem 风格一致） -->
      <FormItem class="shrink-0" label="选择实例">
        <!-- !w 压过 antdv 自带 width:100%（Tailwind 宽度类直接打 Select 会被覆盖） -->
        <Select
          v-model:value="selectedInstance"
          class="!w-[240px]"
          :options="
            instanceOptions.map((id) => ({ label: optionLabel(id), value: id }))
          "
        />
      </FormItem>
    </template>
    <template v-else>
      <!-- 新装：集群模式 + 非单实例时的集群名称 -->
      <FormItem class="shrink-0" label="集群模式">
        <!-- 后端依赖项不下发可选项列表（旧版同款空选项下拉），保持契约 -->
        <Select
          v-model:value="deployMode"
          class="!w-[240px]"
          :options="
            data.deploy_mode.map((item) => ({
              label: item.name,
              value: JSON.stringify(item),
            }))
          "
          :placeholder="
            data.deploy_mode?.length ? '请选择集群模式' : '暂无可选集群模式'
          "
        />
      </FormItem>
      <FormItem v-if="!isSingleMode" class="ml-8 shrink-0" label="集群名称">
        <Input v-model:value="clusterName" class="!w-[240px]" />
      </FormItem>
      <div v-else class="ml-8 w-[240px]"></div>
    </template>

    <template v-if="hasExisting">
      <div class="flex-[3]">存在实例,是否复用？</div>
      <div class="flex-2 text-sm">
        <Checkbox v-model:checked="isMultiplexing" class="mr-2.5">
          复用
        </Checkbox>
      </div>
    </template>
  </div>
</template>
