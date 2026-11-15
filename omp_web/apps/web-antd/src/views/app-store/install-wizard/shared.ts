import type { InjectionKey } from 'vue';

import type { ArgItem, InstallApi } from '#/api/app-store-install';

/**
 * 组件/应用安装向导共享工具。
 *
 * 表单键编码是提交契约的核心：参数/端口表单项的 name 为
 * `install|{owner}|{json}` / `port|{owner}|{json}` 三段扁平字符串
 * （json 段 JSON.stringify 无空格），提交时按下标拆段还原。
 * install 段仅路径参数含真值 dir_key（后端 make_app_install_args 只给
 * default 含 {data_path} 的参数打标记）、port 段不含（旧实现契约，
 * 两侧序列化一致才能对上）。非路径参数不得注入 `dir_key: null`：
 * 后端曾按"键存在"判定路径参数，会把 run_user 拼成路径。
 */

/** 后端校验失败回填的字段错误（扁平键 → check_msg），provide/inject 下发 */
export const INSTALL_FIELD_ERRORS: InjectionKey<Record<string, string>> =
  Symbol('installFieldErrors');

type ArgLike = ArgItem & { default?: null | number | string };

/**
 * install 参数表单键（json 段仅当 arg 自带真值 dir_key 才含该键，
 * 保持与后端提交契约一致：dir_key 是路径参数标记，非路径参数
 * 不携带该键——值为 null 的 dir_key 会被后端误判为路径参数）
 */
export function installArgKey(owner: string, arg: ArgLike): string {
  return `install|${owner}|${JSON.stringify(
    arg.dir_key
      ? { dir_key: arg.dir_key, key: arg.key, name: arg.name }
      : { key: arg.key, name: arg.name },
  )}`;
}

/** port 表单键（json 段不含 dir_key，旧实现契约） */
export function portArgKey(owner: string, arg: ArgLike): string {
  return `port|${owner}|${JSON.stringify({ key: arg.key, name: arg.name })}`;
}

/**
 * 从表单扁平值中收集指定服务的参数/端口数组。
 * 键形如 `${type}|${owner}|{json}`：json 段展开 + default 覆写为用户输入。
 */
export function parameterCreate(
  values: Record<string, any>,
  type: 'install' | 'port',
  owner: string,
): Array<ArgItem & { default: any }> {
  const arr: Array<ArgItem & { default: any }> = [];
  for (const key of Object.keys(values)) {
    const seg = key.split('|');
    if (seg.length === 3 && seg[0] === type && seg[1] === owner) {
      arr.push({
        ...(JSON.parse(seg[2] ?? '') as ArgItem),
        default: values[key],
      });
    }
  }
  return arr;
}

/** 解析依赖服务的 install 输入：{ json段: 用户输入 } */
export function parseDepInstallArgs(
  values: Record<string, any>,
  owner: string,
): Record<string, any> {
  const result: Record<string, any> = {};
  for (const key of Object.keys(values)) {
    const seg = key.split('|');
    if (seg.length === 3 && seg[0] === 'install' && seg[1] === owner) {
      result[seg[2] ?? ''] = values[key];
    }
  }
  return result;
}

/** 解析依赖服务的 ip/instanceName（两段键 `{owner}|ip` / `{owner}|instanceName`） */
export function parseIpInstance(
  values: Record<string, any>,
  owner: string,
): { instanceName?: string; ip?: string } {
  const result: { instanceName?: string; ip?: string } = {};
  for (const key of Object.keys(values)) {
    const seg = key.split('|');
    if (seg.length === 2 && seg[0] === owner) {
      result[seg[1] as 'instanceName' | 'ip'] = values[key];
    }
  }
  return result;
}

/** 实例名默认值：`{owner}-{IP 倒数第二段}-{末段}`（旧契约） */
export function defaultInstanceName(owner: string, ip: string): string {
  const seg = ip.split('.');
  return `${owner}-${seg[seg.length - 2]}-${seg[seg.length - 1]}`;
}

/**
 * 旧 hasSameIp 语义（保留原判定形态）：
 * 依赖为基础环境且存在实例信息时返回同 IP 实例数组（可能为空数组），
 * 否则返回 false（调用方以 `.length === 0` 区分复用/新装）。
 */
export function findSameIpInstances(
  dep: InstallApi.DependenceItem,
  ip: string,
): false | InstallApi.InstanceInfo[] {
  return (
    dep.is_base_env &&
    dep.instance_info &&
    dep.instance_info.filter((b) => b.ip === ip)
  );
}

/** 复用服务项统一带 type:"single" 后提交（旧契约） */
export function markReuseServices(
  services: Record<string, any>[],
): Record<string, any>[] {
  return services.map((item) => ({ ...item, type: 'single' }));
}
