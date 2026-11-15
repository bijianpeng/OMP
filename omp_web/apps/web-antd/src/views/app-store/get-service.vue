<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { ServiceApi } from '#/api/services';

import { computed, onUnmounted, reactive, ref, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Checkbox,
  CheckboxGroup,
  Collapse,
  CollapsePanel,
  Empty,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Result,
  Select,
  Spin,
  Steps,
  Switch,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  executeManagedServices,
  scanManagedServices,
} from '#/api/services';
import { useGetServiceStore } from '#/store/get-service';

/**
 * 服务纳管页（/application_management/get-service，三步向导：
 * 基本信息 → 扫描结果 → 服务纳管完成）。入口数据经 useGetServiceStore
 * 交接（商店「服务纳管」弹窗写入，旧 location.state 契约）。
 * Step1 提交扫描校验（appConfCheck 无 uuid），Step2 提交纳管执行
 * （appConfCheck 带 uuid）。
 * 旧实现 omp_web/src/pages/AppStore/config/GetService.js 迁移。
 */
defineOptions({ name: 'GetService' });

const router = useRouter();
const getServiceStore = useGetServiceStore();

/** 纳管初始数据（入口弹窗交接；直访为空时展示空状态，与旧版一致） */
const serviceData = computed(() => getServiceStore.serviceData);

/** 0 基本信息 1 扫描结果 2 完成 */
const stepNum = ref(0);

// ── Step1：主机范围 + 服务参数 ─────────────────────────────────────

/** 可选主机列表（ip → agent 目录） */
const ipList = computed(() => Object.keys(serviceData.value?.ips ?? {}));

/** 选中主机 */
const selectedIps = ref<string[]>([]);

const loading = shallowRef(false);
/** 扫描中对话框 */
const ingVisible = ref(false);

/** 服务参数表单模型：键 `${服务名}-base_dir` 等（旧契约） */
const formModel = reactive<Record<string, any>>({});

/** 服务参数表单键（三个目录字段带「数据分区」前缀装饰与提示） */
const DIR_KEYS = ['base_dir', 'data_dir', 'log_dir'] as const;

function isDirKey(key: string): boolean {
  return (DIR_KEYS as readonly string[]).includes(key);
}

/** 字段展示名（旧表单 label 契约） */
function fieldLabel(key: string): string {
  switch (key) {
    case 'base_dir': {
      return '安装目录';
    }
    case 'data_dir': {
      return '数据目录';
    }
    case 'log_dir': {
      return '日志目录';
    }
    case 'run_user': {
      return '运行用户';
    }
    default: {
      return '服务端口';
    }
  }
}

/** 字段占位文案（数据目录/日志目录旧版同为「请输入数据目录」） */
function fieldPlaceholder(key: string): string {
  return key === 'base_dir'
    ? '请输入安装目录'
    : key === 'run_user'
      ? '请输入运行用户'
      : key === 'service_port'
        ? '请输入服务端口'
        : '请输入数据目录';
}

/** Step1 服务面板展开项：产品按默认版本展开子服务（旧契约） */
const panelItems = computed(() => {
  const items: {
    errInfo?: string;
    itemData: Record<string, any>;
    productName?: string;
  }[] = [];
  for (const item of serviceData.value?.service ?? []) {
    if (item.child) {
      const children = (item.child[item.version[0]!] ?? []) as Record<
        string,
        any
      >[];
      for (const child of children) {
        items.push({ errInfo: item.error, itemData: child, productName: item.name });
      }
    } else {
      items.push({ errInfo: item.error, itemData: item as Record<string, any> });
    }
  }
  return items;
});

// 初始化表单默认值：后端下发参数剥 "{data_path}" 前缀展示（旧契约）
for (const { itemData } of panelItems.value) {
  for (const key of [...DIR_KEYS, 'run_user', 'service_port']) {
    const raw = itemData[key];
    formModel[`${itemData.name}-${key}`] = isDirKey(key)
      ? String(raw ?? '').replace('{data_path}', '')
      : (raw ?? '');
  }
}

/** 目录提交值：非空加 "{data_path}" 前缀（旧 getPathValue 契约） */
function getPathValue(name: string, dirType: string) {
  const value = formModel[`${name}-${dirType}`];
  return value ? `{data_path}${value}` : '';
}

function toggleAllIps(e: any) {
  selectedIps.value = e.target.checked ? [...ipList.value] : [];
}

/** 组装服务载荷：产品按所选版本的子项平铺目录参数（旧契约） */
function buildServicePayload() {
  const resArr: Record<string, any>[] = [];
  for (const element of serviceData.value?.service ?? []) {
    const args = (name: string) => ({
      base_dir: getPathValue(name, 'base_dir'),
      data_dir: getPathValue(name, 'data_dir'),
      log_dir: getPathValue(name, 'log_dir'),
      run_user: formModel[`${name}-run_user`],
      service_port: formModel[`${name}-service_port`],
    });
    if (element.child) {
      const version = element.version[0]!;
      resArr.push({
        child: {
          [version]: (element.child[version] ?? []).map((i) => ({
            ...i,
            ...args(i.name),
          })),
        },
        name: element.name,
        version: element.version,
      });
    } else {
      resArr.push({ ...element, ...args(element.name) });
    }
  }
  return resArr;
}

/** 扫描结果（Step2 数据） */
const checkServiceData = shallowRef<ServiceApi.ConfCheckResult>();
/** 关联集群选择：服务名 → {is_use_exist, exist_instance}（旧契约） */
const serviceConnectionData = reactive<Record<string, { exist_instance: string[]; is_use_exist: boolean }>>({});

/** 扫描服务（Step1 → Step2） */
async function startScan() {
  loading.value = true;
  ingVisible.value = true;
  // 仅携带选中的主机（旧契约）
  const ipsRes: Record<string, string> = {};
  for (const ip of selectedIps.value) {
    ipsRes[ip] = serviceData.value!.ips[ip]!;
  }
  try {
    const data = await scanManagedServices({
      ips: ipsRes,
      is_continue: serviceData.value?.is_continue ?? false,
      service: buildServicePayload(),
    });
    checkServiceData.value = data;
    // 默认关联首个可用集群实例（旧契约）
    for (const element of data.ser_info) {
      serviceConnectionData[element.name] = {
        exist_instance:
          element.exist_instance.length === 0 ? [] : [element.exist_instance[0]!],
        is_use_exist: element.is_use_exist,
      };
    }
    stepNum.value = 1;
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
    ingVisible.value = false;
  }
}

// ── Step2：扫描结果 ────────────────────────────────────────────────

const step2Loading = shallowRef(false);

/** IP 列筛选（按扫描行 ip 包含匹配，旧契约） */
const ipFilters = computed(() =>
  ipList.value.map((i) => ({ text: i, value: i })),
);

const step2Columns: TableColumnsType = [
  {
    title: '服务名称',
    dataIndex: 'name',
    key: 'name',
    align: 'center' as const,
    width: 200,
  },
  {
    title: '扫描到该服务的IP',
    dataIndex: 'ip',
    key: 'ip',
    align: 'center' as const,
    width: 300,
    filters: ipFilters.value,
    onFilter: (value: any, record: any) => record.ip.indexOf(value) !== -1,
  },
  {
    title: '关联集群',
    dataIndex: 'is_use_exist',
    key: 'is_use_exist',
    align: 'center' as const,
    width: 80,
  },
  {
    title: '可选集群实例',
    dataIndex: 'exist_instance',
    key: 'exist_instance',
    align: 'center' as const,
    width: 260,
  },
  {
    title: '校验结果',
    dataIndex: 'check',
    key: 'check',
    align: 'center' as const,
    width: 100,
  },
  {
    title: '错误信息',
    dataIndex: 'error',
    key: 'error',
    align: 'center' as const,
  },
];

/** 纳管执行（Step2 → 完成） */
async function addService() {
  step2Loading.value = true;
  const serInfo = (checkServiceData.value?.ser_info ?? []).map((element) => ({
    error: element.error,
    exist_instance: serviceConnectionData[element.name]?.exist_instance ?? [],
    ip: element.ip,
    is_use_exist: serviceConnectionData[element.name]?.is_use_exist ?? false,
    name: element.name,
  }));
  try {
    const data = await executeManagedServices({
      ser_info: serInfo,
      uuid: checkServiceData.value?.uuid ?? '',
    });
    if (data.is_error) {
      message.warning(data.message);
    } else {
      stepNum.value = 2;
    }
  } catch {
    // 全局拦截器已提示
  } finally {
    step2Loading.value = false;
  }
}

function goBack() {
  router.back();
}

function goServiceManagement() {
  router.push('/application_management/service_management');
}

// 离开纳管流程时清空交接数据（避免残留旧流程）
onUnmounted(() => {
  getServiceStore.$reset();
});
</script>

<template>
  <Page>
    <!-- 满高纵向布局：包裹层 min-h-full（Page 内容区为视口定高）+ 各步骤
         内容区 flex-1，内容不足一屏时操作条贴内容区可视底部；内容超高时
         主区滚动，操作条 sticky 钉底（包含块为满高包裹层） -->
    <div class="flex min-h-full flex-col">
    <!-- 顶部导航条：返回 + 标题 + 步骤条 -->
    <div class="flex h-[50px] shrink-0 items-center justify-between bg-card pl-5 pr-[50px]">
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
        <span class="whitespace-nowrap pl-3">服务纳管</span>
      </div>
      <!-- antdv Steps 根元素自带无层级 width:100%，Tailwind 宽度类会被压过，需内联 style -->
      <Steps :current="stepNum" :style="{ width: '600px', minWidth: 0 }" size="small">
        <Steps.Step title="基本信息" />
        <Steps.Step title="扫描结果" />
        <Steps.Step title="服务纳管" />
      </Steps>
      <div class="w-[40px]"></div>
    </div>

    <!-- 第一步：选择主机范围 + 服务参数 -->
    <template v-if="stepNum === 0">
      <div class="mt-5 flex items-center bg-card py-2.5 pl-[30px]">
        <IconifyIcon class="mr-2.5 text-base text-[#2e7cee]" icon="lucide:circle-alert" />
        请选择本次纳管的主机范围，填写服务相关信息
      </div>

      <!-- 中段 flex-1：内容不足一屏时撑开把操作条压到可视底部（antdv Spin 不
           透传 class 到根元素，flex-1 需包在外层 div 上） -->
      <div class="flex-1">
      <Spin :spinning="loading">
        <div class="mt-[15px] flex bg-card">
          <!-- 左侧：主机选择 -->
          <div class="w-[240px] shrink-0">
            <div class="px-2.5 pb-2.5 pt-[15px]">
              <p class="ml-5">
                选择主机 :
                <Checkbox
                  class="float-right"
                  :checked="selectedIps.length > 0 && selectedIps.length === ipList.length"
                  :disabled="ipList.length === 0"
                  @change="toggleAllIps"
                >
                  全选
                </Checkbox>
              </p>
              <div v-if="ipList.length === 0" class="ml-[30px] text-[#a7abb7]">
                暂无可选的主机
              </div>
              <CheckboxGroup
                v-else
                v-model:value="selectedIps"
                class="ml-[30px]"
              >
                <div v-for="ip in ipList" :key="ip" class="leading-[32px]">
                  <Checkbox :value="ip">{{ ip }}</Checkbox>
                </div>
              </CheckboxGroup>
            </div>
          </div>

          <!-- 右侧：服务参数表单（无待配置服务时展示空态引导） -->
          <div class="min-w-0 flex-1 border-l border-border overflow-y-auto pt-2.5">
            <Empty
              v-if="panelItems.length === 0"
              class="mt-16"
              description="请在左侧选择主机"
            />
            <Form v-else :model="formModel">
              <div v-for="panel in panelItems" :key="panel.itemData.name" class="p-2.5 pb-0">
                <Collapse :bordered="false" default-active-key="1" expand-icon-position="start">
                  <CollapsePanel
                    key="1"
                    class="bg-muted"
                  >
                    <template #header>
                      <span
                        v-if="panel.productName"
                        class="mr-3 text-[#4986f7]"
                      >[ {{ panel.productName }} ]</span>
                      <span>{{ panel.itemData.name }}</span>
                      <span v-if="panel.errInfo" class="ml-5 text-red-500">
                        {{ panel.errInfo }}
                      </span>
                    </template>
                    <template #extra>
                      {{ typeof panel.itemData.version === 'string' ? panel.itemData.version : panel.itemData.version[0] }}
                    </template>
                    <div v-for="key in [...DIR_KEYS, 'run_user', 'service_port']" :key="key" class="mt-2.5 w-[600px]">
                      <FormItem
                        :label="fieldLabel(key)"
                        :name="`${panel.itemData.name}-${key}`"
                      >
                        <Input
                          v-model:value="formModel[`${panel.itemData.name}-${key}`]"
                          :placeholder="fieldPlaceholder(key)"
                        >
                          <template v-if="isDirKey(key)" #addonBefore>
                            <span class="text-[#b1b1b1]">/ 数据分区</span>
                          </template>
                          <template v-if="isDirKey(key)" #suffix>
                            <Tooltip title="数据分区：主机所设置的数据分区">
                              <IconifyIcon class="text-muted-foreground" icon="lucide:info" />
                            </Tooltip>
                          </template>
                        </Input>
                      </FormItem>
                    </div>
                  </CollapsePanel>
                </Collapse>
              </div>
            </Form>
          </div>
        </div>
      </Spin>
      </div>

      <!-- 步骤操作条（不足一屏时由满高 flex 布局贴底，超高滚动时 sticky 钉底） -->
      <div class="sticky bottom-0 z-10 mt-5 flex shrink-0 items-center justify-between border-t border-border bg-card py-4 pl-5 pr-[30px]">
        <div class="pl-1">分布主机: {{ selectedIps.length }} 台</div>
        <Button
          :disabled="!serviceData?.is_continue || selectedIps.length === 0"
          :loading="loading"
          type="primary"
          @click="startScan"
        >
          扫描服务
        </Button>
      </div>

      <!-- 扫描中对话框 -->
      <Modal :open="ingVisible" :footer="null" title="服务纳管" :width="600" @cancel="ingVisible = false">
        <div class="m-5 flex items-center">
          <IconifyIcon class="mr-4 text-base animate-spin" icon="lucide:loader-circle" />
          正在按照服务相关信息，对指定服务器进行扫描，请稍后...
        </div>
      </Modal>
    </template>

    <!-- 第二步：扫描结果 -->
    <template v-else-if="stepNum === 1">
      <div class="mt-5 flex items-center bg-card py-2.5 pl-[30px]">
        <IconifyIcon class="mr-2.5 text-base text-[#2e7cee]" icon="lucide:circle-alert" />
        扫描结果如下
      </div>

      <div class="mt-[15px] w-full flex-1 bg-card p-5">
        <Table
          :columns="step2Columns"
          :data-source="checkServiceData?.ser_info ?? []"
          :pagination="{ pageSize: 10 }"
          bordered
          class="w-full"
        >
          <template #bodyCell="{ column, record, text }">
            <template v-if="column.key === 'ip'">
              <span v-if="typeof text === 'string'">{{ text }}</span>
              <span v-else-if="text.length === 0">-</span>
              <span v-else>
                <Tag v-for="item in text" :key="item">{{ item }}</Tag>
              </span>
            </template>
            <template v-else-if="column.key === 'is_use_exist'">
              <!-- 无可用实例的行禁在关闭态（旧 disabled=!record.is_use_exist 契约） -->
              <Switch
                v-model:checked="serviceConnectionData[record.name]!.is_use_exist"
                :disabled="!record.is_use_exist"
              />
            </template>
            <template v-else-if="column.key === 'exist_instance'">
              <span v-if="record.exist_instance.length === 0">无可用实例</span>
              <Select
                v-else
                :disabled="!serviceConnectionData[record.name]?.is_use_exist"
                :options="record.exist_instance.map((e: string) => ({ label: e, value: e }))"
                :value="serviceConnectionData[record.name]?.exist_instance?.[0]"
                @change="
                  (value: any) => {
                    serviceConnectionData[record.name]!.exist_instance = [String(value)];
                  }
                "
              />
            </template>
            <template v-else-if="column.key === 'check'">
              <IconifyIcon
                v-if="record.error"
                class="text-base text-[#f74d50]"
                icon="lucide:circle-x"
              />
              <IconifyIcon v-else class="text-base text-[#52c41b]" icon="lucide:circle-check" />
            </template>
            <template v-else-if="column.key === 'error'">
              {{ text || '-' }}
            </template>
          </template>
        </Table>
      </div>

      <div class="sticky bottom-0 z-10 mt-5 flex shrink-0 justify-end gap-2.5 border-t border-border bg-card py-4 pr-[30px]">
        <Button type="primary" @click="stepNum = 0">上一步</Button>
        <Button
          :disabled="!checkServiceData?.is_continue"
          :loading="step2Loading"
          type="primary"
          @click="addService"
        >
          纳管
        </Button>
      </div>
    </template>

    <!-- 第三步：完成 -->
    <Result
      v-else
      class="bg-card pt-[10%]"
      status="success"
      title="服务纳管执行成功"
    >
      <template #extra>
        <Button @click="goBack">返回</Button>
        <Button type="primary" @click="goServiceManagement">查看服务</Button>
      </template>
    </Result>
    </div>
  </Page>
</template>
