<script lang="ts" setup>
import type { AppStoreApi } from '#/api/app-store';

import { h, ref, shallowRef, watch } from 'vue';

import { Cascader, message, Modal } from 'ant-design-vue';

import { deletePackages, listDeletablePackages } from '#/api/app-store';

/**
 * 商店安装包删除弹窗（更多菜单「删除」入口）：按当前 tab 拉取可删包列表，
 * 级联多选（名称|版本拆分展示）后提交删除；有已安装实例时后端整批拒绝。
 * 旧实现 omp_web/src/pages/AppStore/config/DeleteServerModal.js 迁移。
 */
defineOptions({ name: 'DeleteServerModal' });

const props = defineProps<{
  /** 当前商店 tab：component 基础组件 / service 应用服务（后者传 product） */
  tabKey: 'component' | 'service';
}>();

const emit = defineEmits<{ refresh: [] }>();

const open = defineModel<boolean>('open', { default: false });

/** type 参数：组件传 component，其余（服务 tab）传 product（旧契约） */
const deleteType = () => (props.tabKey === 'component' ? 'component' : 'product');

const loading = shallowRef(false);
/** 全量选项数据（提交时按 name 汇总 versions） */
const initData = ref<AppStoreApi.DeletablePackage[]>([]);
/** 级联选中值（[name, version] 路径数组） */
const resApp = ref<string[][]>([]);

/** "名称|版本" 复合串拆分展示：左名称 + 右浮版本（旧契约） */
function splitLabel(text: string) {
  if (text.includes('|')) {
    const [left, right] = text.split('|');
    return h('span', [
      left,
      h(
        'span',
        { style: { float: 'right', marginLeft: '20px' } },
        right,
      ),
    ]);
  }
  return text;
}

interface CascaderOption {
  children?: CascaderOption[];
  label: ReturnType<typeof splitLabel>;
  value: string;
}

const options = shallowRef<CascaderOption[]>([]);

async function queryData() {
  loading.value = true;
  try {
    const data = await listDeletablePackages(deleteType());
    initData.value = data.data;
    options.value = data.data.map((e) => ({
      label: splitLabel(e.name),
      value: e.name,
      children: e.versions.map((i) => ({
        label: splitLabel(i),
        value: i,
      })),
    }));
  } catch {
    // 全局拦截器已提示
  } finally {
    loading.value = false;
  }
}

watch(open, (value) => {
  if (value) {
    resApp.value = [];
    queryData();
  }
});

/** 组装删除载荷：整名删除（仅选一层不存在）与按版本部分删除（旧契约） */
function buildPayload(): AppStoreApi.DeletablePackage[] {
  const allList: string[] = [];
  const someList: Record<string, string[]> = {};
  for (const e of resApp.value) {
    if (e.length === 1) {
      allList.push(e[0]!);
    } else {
      someList[e[0]!] = [...(someList[e[0]!] ?? []), e[1]!];
    }
  }
  const resData: AppStoreApi.DeletablePackage[] = [];
  for (const e of initData.value) {
    if (allList.includes(e.name)) {
      resData.push(e);
    } else if (someList[e.name]) {
      resData.push({ name: e.name, versions: someList[e.name]! });
    }
  }
  return resData;
}

async function handleOk() {
  if (resApp.value.length === 0) {
    message.info('请先选择要删除的服务');
    return;
  }
  loading.value = true;
  try {
    await deletePackages({ data: buildPayload(), type: deleteType() });
    message.success('删除成功');
    open.value = false;
  } catch {
    // 全局拦截器已提示（存在已安装实例等后端校验失败）
  } finally {
    loading.value = false;
  }
}

/** 关闭后清空选中并刷新商店列表（旧 afterClose 契约） */
function handleAfterClose() {
  resApp.value = [];
  emit('refresh');
}
</script>

<template>
  <Modal
    v-model:open="open"
    :confirm-loading="loading"
    :ok-text="loading ? '稍候' : '删除'"
    :title="`删除${tabKey === 'component' ? '基础组件' : '自研服务'}`"
    :width="480"
    cancel-text="取消"
    destroy-on-close
    @after-close="handleAfterClose"
    @ok="handleOk"
  >
    <div class="mb-5 ml-2.5">
      选择服务：
      <Cascader
        v-model:value="resApp"
        :options="options"
        class="ml-1.5"
        multiple
        max-tag-count="responsive"
        :placeholder="tabKey === 'component' ? '选择基础组件' : '选择自研服务'"
        :style="{ width: '300px' }"
      />
    </div>
  </Modal>
</template>
