<script lang="ts" setup>
import type { InstallationApi } from '#/api/installation';

import { computed, onMounted, reactive, shallowRef } from 'vue';

import { Alert, Button, message, Spin } from 'ant-design-vue';

import {
  checkServiceDistribution,
  createServiceDistribution,
  listServiceByIp,
} from '#/api/installation';

import ServiceDistributionItem from './components/service-distribution-item.vue';
import { expandPaths, productOfService } from './shared';

/**
 * Step2 服务分布：按主机级联多选待安装服务（产品 → 服务）。
 * 数据池 pool（服务名 → 剩余数量/with 目标）驱动全局分配约束：
 * - 勾选 num -1 / 取消 +1（下限 0），数量耗尽的服务从其它主机选项中剔除；
 * - with 强绑定服务禁选，其跟随目标在本机被勾选时自动跟随（pool 同步）；
 * 提交 checkServiceDistribution 数量校验，通过后进入修改配置。
 */
defineOptions({ name: 'InstallationStep2Distribution' });

const props = defineProps<{
  /** 本次流程唯一键 */
  uniqueKey: string;
}>();

const emit = defineEmits<{
  next: [];
  prev: [];
}>();

const loading = shallowRef(false);

/** 主机行（ip + 已安装服务数） */
const hostList = shallowRef<InstallationApi.HostInfo[]>([]);
/** 级联选项树（产品 → 服务名） */
const productTree = shallowRef<InstallationApi.ProductInfo[]>([]);
/** with 自动跟随服务（只读提示条） */
const withServices = shallowRef<InstallationApi.WithService[]>([]);
/**
 * 数据池（旧 redux dataSource 契约）：服务名 → {num 剩余可分配数, with 目标}
 */
const pool = reactive<Record<string, InstallationApi.PoolItem>>({});
/** 各主机选中值（级联路径数组，受控） */
const selections = reactive<Record<string, string[][]>>({});
/** 已安装服务映射（ip → 实例列表，「已安装服务数」悬浮明细） */
const installService = shallowRef<InstallationApi.InstallServiceMap>({});
/** 校验失败列表（按 ip 回显） */
const errorList = shallowRef<
  InstallationApi.CheckDistributionResult['error_lst']
>([]);

/** 未分配服务数（数据池 num 总和） */
const unassignedCount = computed(() =>
  Object.values(pool).reduce((prev, cur) => prev + cur.num, 0),
);

/** 已分配主机数（选中值非空的主机） */
const assignedHostCount = computed(
  () => Object.values(selections).filter((paths) => paths.length > 0).length,
);

onMounted(async () => {
  loading.value = true;
  try {
    const [dist, installed] = await Promise.all([
      createServiceDistribution(props.uniqueKey),
      listServiceByIp().catch(() => ({})),
    ]);
    const distData = dist?.data;
    if (distData) {
      hostList.value = distData.host ?? [];
      productTree.value = distData.product ?? [];
      withServices.value = distData.with_services ?? [];
      for (const [name, item] of Object.entries(distData.all ?? {})) {
        pool[name] = { ...item };
      }
    }
    installService.value = installed ?? {};
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
});

/** 数据池数量调整（下限 0，旧 handleDataSourceData 契约） */
function adjustPoolNum(serviceName: string, delta: number) {
  const item = pool[serviceName];
  if (!item) return;
  const next = item.num + delta;
  item.num = next <= 0 ? 0 : next;
}

/** 展开级联路径为服务名集合（旧 dealColumnsData 契约） */
function expandPathsOf(paths: string[][]): string[] {
  return expandPaths(paths, productTree.value, pool);
}

/**
 * 主机选中值变更（旧 onClick 全套分检的等价实现）：
 * 对比展开后的服务集合差集同步数据池数量，并为新增服务的 with
 * 跟随项自动补选中值（handleWithData 契约）。
 */
function handleDistributionChange(ip: string, newPaths: string[][]) {
  const before = new Set(expandPathsOf(selections[ip] ?? []));
  const after = new Set(expandPathsOf(newPaths));
  const added = [...after].filter((name) => !before.has(name));
  const removed = [...before].filter((name) => !after.has(name));

  for (const name of added) adjustPoolNum(name, -1);
  for (const name of removed) adjustPoolNum(name, +1);

  // with 跟随项：目标在本机新增 → 自动加入；目标被移除 → 自动移除
  const nextPaths = [...newPaths];
  for (const [name, item] of Object.entries(pool)) {
    if (!item.with) continue;
    const idx = nextPaths.findIndex((path) => path[1] === name);
    if (after.has(item.with) && idx === -1) {
      adjustPoolNum(name, -1);
      nextPaths.push([productOfService(name, productTree.value) ?? '', name]);
    } else if (!after.has(item.with) && idx !== -1) {
      nextPaths.splice(idx, 1);
      adjustPoolNum(name, +1);
    }
  }
  selections[ip] = nextPaths;
}

/** 提交载荷：ip → 服务名列表（旧 dataProcessing 契约，空主机不提交） */
function buildQueryData(): Record<string, string[]> {
  const result: Record<string, string[]> = {};
  for (const [ip, paths] of Object.entries(selections)) {
    const services = expandPathsOf(paths);
    if (services.length > 0) {
      result[ip] = services;
    }
  }
  return result;
}

async function handleNext() {
  loading.value = true;
  try {
    const result = await checkServiceDistribution({
      unique_key: props.uniqueKey,
      data: buildQueryData(),
    });
    if (result) {
      if (result.is_continue) {
        emit('next');
      } else {
        message.warning('校验未通过');
        errorList.value = result.error_lst ?? [];
      }
    }
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

function errorMsgOf(ip: string) {
  return errorList.value.find((item) => item.ip === ip)?.error_msg;
}
</script>

<template>
  <section class="mt-5 min-h-0 flex-1 overflow-y-auto bg-card p-2.5 pb-[30px]">
    <Spin :spinning="loading">
      <div class="flex">
        <div class="mt-2.5 pb-[30px] pl-5">
          主机总数: {{ hostList.length }}台
        </div>
        <div class="ml-10 mt-2.5 pb-[30px]">
          未分配服务: {{ unassignedCount }}个
        </div>
      </div>
      <Alert
        v-if="withServices.length > 0"
        class="mx-[30px] mb-4"
        show-icon
        type="info"
      >
        <template #message>
          以下服务将自动跟随 tengine 部署到 tengine 所在节点，无需手动选择
        </template>
        <template #description>
          {{ withServices.map((item) => item.name).join('、') }}
        </template>
      </Alert>
      <div class="flex flex-wrap px-[30px]">
        <ServiceDistributionItem
          v-for="host in hostList"
          :key="host.ip"
          :error-msg="errorMsgOf(host.ip)"
          :host="host"
          :install-service="installService"
          :pool="pool"
          :products="productTree"
          :selected="selections[host.ip] ?? []"
          @change="(paths: any) => handleDistributionChange(host.ip, paths as string[][])"
        />
      </div>
    </Spin>
  </section>

  <div class="mt-5 flex shrink-0 items-center justify-between bg-card py-6 pl-6 pr-8">
    <div>已分配主机数量: {{ assignedHostCount }}台</div>
    <div>
      <Button html-type="button" type="primary" @click="emit('prev')">
        上一步
      </Button>
      <Button
        class="ml-2.5"
        :disabled="unassignedCount !== 0"
        :loading="loading"
        html-type="button"
        type="primary"
        @click="handleNext"
      >
        下一步
      </Button>
    </div>
  </div>
</template>
