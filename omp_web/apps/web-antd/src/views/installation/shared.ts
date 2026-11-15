import type { InjectionKey } from 'vue';

import type { InstallationApi } from '#/api/installation';

import { inject } from 'vue';

/**
 * 批量安装向导共享工具。
 *
 * 服务分布的选中值是级联路径数组（[[产品名, 服务名], ...]），
 * 全选某产品时 antdv 级联按 SHOW_PARENT 策略折叠为 [[产品名]]（vc-cascader
 * conductCheck：父选中时值只保留父键），因此服务名集合必须经 expandPaths 展开；
 * with 强绑定服务在选项中 disabled、无法被勾选，折叠值只可能包含可勾选服务，
 * 展开时同样只取非 with 子项（与 conductCheck 的填充范围一致）。
 */

/**
 * 表单模型注入键：扁平键值模型与外层 `<Form :model>` 同源，行组件经
 * inject 直写（props 下传会被 vue/no-mutating-props 拦截）。
 * 键契约见各行组件头注释。
 */
export const INSTALL_BASIC_MODEL: InjectionKey<Record<string, any>> =
  Symbol('installationBasicModel');

export const INSTALL_DEPENDENT_MODEL: InjectionKey<Record<string, any>> =
  Symbol('installationDependentModel');

export const INSTALL_CONFIG_MODEL: InjectionKey<Record<string, any>> =
  Symbol('installationConfigModel');

/** 注入必需依赖，缺失时明确报错（调用方须在父级 provide） */
export function injectModel(
  key: InjectionKey<Record<string, any>>,
): Record<string, any> {
  const model = inject(key);
  if (!model) {
    throw new Error(
      `installation form model "${String(key.description)}" 未提供`,
    );
  }
  return model;
}

/** 随机大写字母串（旧 randomNumber 只取大写字母，数字段实际不可达，此处直接取 A-Z） */
export function randomCode(length = 6): string {
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  let result = '';
  for (let i = 0; i < length; i += 1) {
    result += letters[Math.floor(Math.random() * letters.length)] ?? 'A';
  }
  return result;
}

/**
 * 展开级联选中值为服务名集合：
 * - 两段路径取末段（服务名）；
 * - 单段路径（SHOW_PARENT 折叠值）展开为该产品下全部非 with 子服务。
 */
export function expandPaths(
  paths: string[][] | undefined,
  productTree: InstallationApi.ProductInfo[],
  pool: Record<string, InstallationApi.PoolItem>,
): string[] {
  const result: string[] = [];
  for (const path of paths ?? []) {
    const [head, leaf] = path;
    if (leaf) {
      result.push(leaf);
    } else {
      const node = productTree.find((item) => item.name === head);
      if (!node) continue;
      for (const child of node.child) {
        // with 服务在选项中 disabled，父级勾选不会覆盖到它
        if (!isWithService(child, pool)) {
          result.push(child);
        }
      }
    }
  }
  return result;
}

/** 服务是否被 with 强绑定（数据池 with 字段非空即为跟随项） */
export function isWithService(
  serviceName: string,
  pool: Record<string, InstallationApi.PoolItem>,
): boolean {
  return Boolean(pool[serviceName]?.with);
}

/** 服务名 → 所属产品名（级联树反查，自动跟随项补路径用） */
export function productOfService(
  serviceName: string,
  productTree: InstallationApi.ProductInfo[],
): string | undefined {
  return productTree.find((item) => item.child.includes(serviceName))?.name;
}
