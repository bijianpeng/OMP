<script lang="ts" setup>
import type { InstallationApi } from '#/api/installation';

import { computed } from 'vue';

import { Cascader, Tag, Tooltip } from 'ant-design-vue';

import { expandPaths, isWithService, productOfService } from '../shared';
import HasInstallService from './has-install-service.vue';

/**
 * Step2 单主机服务分布卡片：级联多选（产品 → 服务）+ 已选/已安装计数。
 *
 * 数据池契约（旧 redux dataSource）：勾选服务使 pool[服务].num -1（下限 0），
 * 取消勾选 +1；with 强绑定服务在选项中 disabled、不可手选，当其跟随目标
 * 在本机被勾选时自动加入本机选中值（pool 同步 -1，由父级 change 处理）。
 * antdv Cascader 全选某产品时按 SHOW_PARENT 策略折叠为 [产品名] 单段路径，
 * 服务集合经 expandPaths 展开（旧 dealColumnsData 契约）。
 */
defineOptions({ name: 'InstallationServiceDistributionItem' });

const props = defineProps<{
  /** 本机校验失败提示（checkServiceDistribution 回显） */
  errorMsg?: string;
  host: InstallationApi.HostInfo;
  installService: InstallationApi.InstallServiceMap;
  pool: Record<string, InstallationApi.PoolItem>;
  products: InstallationApi.ProductInfo[];
  /** 本机选中值（级联路径数组，受控） */
  selected: string[][];
}>();

const emit = defineEmits<{ change: [paths: string[][]] }>();

/** 本机已选服务集合（含折叠值展开） */
const selectedServices = computed(() =>
  expandPaths(props.selected, props.products, props.pool),
);

/** 级联选项（与 antdv CascaderOptionType 结构一致） */
interface DistOption {
  children: DistOption[];
  disabled: boolean;
  label: string;
  value: string;
}

/** 级联选项：数据池耗尽（num=0 且非本机已选）的服务剔除，with 服务禁选 */
const options = computed<DistOption[]>(() => {
  const selectedNames = selectedServices.value;
  return props.products.map((node) => ({
    children: node.child
      .filter(
        (name) =>
          isWithService(name, props.pool) ||
          props.pool[name]?.num !== 0 ||
          selectedNames.includes(name),
      )
      .map(
        (name): DistOption => ({
          children: [],
          disabled: isWithService(name, props.pool),
          label: name,
          value: name,
        }),
      ),
    disabled: false,
    label: node.name,
    value: node.name,
  }));
});
</script>

<template>
  <div class="mb-10 w-[45%]">
    <div class="flex items-center justify-center">
      <div class="relative flex items-center">
        <div
          class="absolute text-[red]"
          :class="errorMsg ? 'top-[40px] h-5' : 'top-[25px] h-0'"
          style="transition: all 0.1s ease-in"
        >
          {{ errorMsg }}
        </div>
        <!-- 旧实现经 FormItem label 承载 IP 标题，此处无校验需求改为纯展示 -->
        <span class="pr-2.5 text-sm">{{ host.ip }}</span>
        <Cascader
          :allow-clear="false"
          class="w-[240px]"
          expand-trigger="hover"
          max-tag-count="responsive"
          multiple
          :options="options"
          placeholder="请选择"
          :value="selected"
          @change="(paths: any) => emit('change', paths as string[][])"
        >
          <template #tagRender="{ label }">
            <Tag>{{ pool[String(label)] ? label : `${label}-集合` }}</Tag>
          </template>
        </Cascader>
      </div>
      <div class="pl-4">
        <div class="text-[13px]">
          选择服务数:
          <Tooltip
            :mouse-enter-delay="0.3"
            overlay-class-name="installation-svc-tooltip"
            placement="right"
            color="white"
          >
            <template #title>
              <div class="h-[330px] min-w-[300px] p-[5px] text-black/85">
                <div class="border-b border-border pb-[5px] text-[14px]">
                  已选服务
                </div>
                <div class="h-[300px] overflow-y-auto">
                  <div
                    v-for="name in selectedServices"
                    :key="name"
                    class="pt-[5px] text-[14px]"
                  >
                    {{ productOfService(name, products) ?? '-' }} / {{ name }}
                  </div>
                </div>
              </div>
            </template>
            <a v-if="selectedServices.length > 0">
              {{ selectedServices.length }}个
            </a>
            <span v-else>0个</span>
          </Tooltip>
        </div>
        <div class="text-xs">
          已安装服务数:
          <HasInstallService
            v-if="host.num !== 0"
            :installed="installService[host.ip] ?? []"
          >
            {{ host.num }}个
          </HasInstallService>
          <span v-else>0个</span>
        </div>
      </div>
    </div>
  </div>
</template>
