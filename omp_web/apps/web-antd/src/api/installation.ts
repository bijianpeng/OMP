import { requestClient } from '#/api/request';

/**
 * 批量安装编排接口（/app_store/installation 四步向导）。
 *
 * 链路：batchInstallEntrance（入口，返回 unique_key）→ createInstallInfo
 * （确认选择，产出 Step1 基础数据）→ checkInstallInfo（Step1 校验）→
 * createServiceDistribution / checkServiceDistribution（Step2 服务分布）→
 * getInstallHostRange / getInstallArgsByIp / createInstallPlan（Step3 修改配置）→
 * showInstallProcess / showSingleServiceInstallLog / retryInstall（Step4 进度）。
 * 后端契约见 omp_server/app_store/new_install_view.py + new_install_serializers.py。
 */
export namespace InstallationApi {
  // ── 入口（应用商店批量安装弹窗，批 K 维护） ─────────────────────────

  /** 批量安装入口项（is_continue=false 表示已安装过不可再选） */
  export interface EntranceItem {
    is_continue: boolean;
    name: string;
    version: string[];
  }

  /** 入口响应（unique_key 由后端生成并写入 Redis 流程缓存） */
  export interface EntranceResult {
    data: EntranceItem[];
    unique_key: string;
  }

  /** 已存在实例（依赖「复用依赖」选择项，value 提交时 JSON.stringify 整项） */
  export interface ExistInstance {
    id: number;
    ip?: string;
    name: string;
    service_instance_name?: string;
    type?: string;
  }

  /** 数量型部署模式（default 初始数量 / step 步长，step=0 固定不可改） */
  export interface DeployModeCount {
    default: number;
    step: number;
  }

  /** 模式型部署模式（single / master-slave / master-master 等） */
  export interface DeployModeOption {
    key: string;
    name: string;
  }

  /** 产品内服务项（deploy_mode 恒为数量型） */
  export interface BasicService {
    deploy_mode: DeployModeCount;
    name: string;
    version: string;
    /** with 强绑定标识（tengine 亲和），随 with 目标节点部署 */
    with?: string;
    with_flag?: boolean;
  }

  /** Step1 基本信息产品项 */
  export interface BasicItem {
    error_msg?: string;
    name: string;
    services_list: BasicService[];
    version: string;
  }

  /** Step1 依赖项部署模式：数量型 或 模式选项数组（mysql 等） */
  export type DependenceDeployMode = DeployModeCount | DeployModeOption[];

  /** Step1 依赖信息服务项 */
  export interface DependenceItem {
    deploy_mode: DependenceDeployMode;
    error_msg?: string;
    /** 已存在实例（is_use_exist=true 时「复用依赖」下拉数据源） */
    exist_instance: ExistInstance[];
    is_base_env: boolean;
    is_use_exist: boolean;
    name: string;
    version: string;
  }

  /** createInstallInfo / checkInstallInfo 产出的 Step1 基础数据 */
  export interface Step1Data {
    basic: BasicItem[];
    dependence: DependenceItem[];
    is_continue: boolean;
  }

  /** checkInstallInfo 响应（校验失败时 basic/dependence 内逐项标注 error_msg） */
  export interface CheckInstallInfoResult {
    data: Step1Data;
    unique_key: string;
  }

  // ── Step2 服务分布 ────────────────────────────────────────────────

  /** 服务分布数据池项（num 剩余可分配数量 / with 自动跟随的目标服务） */
  export interface PoolItem {
    num: number;
    with?: null | string;
  }

  /** 主机行（num 为该机已安装服务数，展示用） */
  export interface HostInfo {
    ip: string;
    num: number;
  }

  /** 级联选项树节点（child 为服务名列表，含 with 服务） */
  export interface ProductInfo {
    child: string[];
    name: string;
  }

  /** with 自动跟随服务（跟随 with 指向的服务所在节点，只读展示） */
  export interface WithService {
    name?: string;
    version?: string;
    with?: null | string;
  }

  /** createServiceDistribution 响应 */
  export interface DistributionResult {
    data: {
      /** 数据池：服务名 → {num 剩余数, with 跟随目标} */
      all: Record<string, PoolItem>;
      host: HostInfo[];
      product: ProductInfo[];
      with_services: WithService[];
    };
    unique_key: string;
  }

  /** listServiceByIp 响应：ip → 已安装服务实例 */
  export type InstallServiceMap = Record<
    string,
    { ip: string; service__app_name: string; service_instance_name: string }[]
  >;

  /** checkServiceDistribution 响应（error_lst 按主机标注失败原因） */
  export interface CheckDistributionResult {
    data: Record<string, string[]>;
    error_lst: { error_msg: string; ip: string }[];
    is_continue: boolean;
  }

  // ── Step3 修改配置 ────────────────────────────────────────────────

  /** 安装参数/端口项（editable=false 只读，dir_key 标记数据分区字段） */
  export interface ConfigArg {
    default?: null | number | string;
    dir_key?: boolean | null | string;
    editable?: boolean;
    key: string;
    name: string;
    /** 校验失败标记（createInstallPlan 失败回传时出现） */
    check_flag?: boolean;
    error_msg?: string;
  }

  /** 某主机上某服务的配置项 */
  export interface ConfigService {
    install_args: ConfigArg[];
    instance_name?: string;
    name: string;
    ports: ConfigArg[];
  }

  /** getInstallArgsByIp 响应（err_msg 为后端数据异常提示，正常时无） */
  export interface ArgsByIpResult {
    data: ConfigService[];
    err_msg?: string;
    error_msg?: string;
    unique_key: string;
  }

  /** createInstallPlan 响应（失败时 data 内服务参数逐项带 check_flag/error_msg） */
  export interface InstallPlanResult {
    data: Record<string, ConfigService[]>;
    error_lst?: { [ip: string]: string }[];
    error_msg?: string;
    is_continue: boolean;
    run_user?: string;
    unique_key: string;
  }

  // ── Step4 开始安装 ────────────────────────────────────────────────

  /** 安装明细项（status：0 等待 1 进行中 2 成功 3 失败） */
  export interface ProcessDetailItem {
    ip: string;
    status: number;
  }

  /** showInstallProcess 响应（detail 按应用名分组；postAction 为安装后动作） */
  export interface InstallProcess {
    detail: Record<string, ProcessDetailItem[]>;
    percentage: number;
    status: number;
  }

  /** showSingleServiceInstallLog 响应 */
  export interface SingleServiceLog {
    log: string;
  }
}

// ── 入口 ──────────────────────────────────────────────────────────────

/** 批量安装入口（product_name 可选过滤；无主机时后端抛错全局提示） */
export function getBatchInstallEntrance(productName?: string) {
  return requestClient.get<InstallationApi.EntranceResult>(
    '/api/appStore/batchInstallEntrance/',
    { params: { product_name: productName ?? null } },
  );
}

/** 服务批量安装-确认选择（产出 Step1 基础数据；unique_key 由入口下发） */
export function createInstallInfo(data: {
  high_availability: boolean;
  install_product: { name: string; version: string }[];
  unique_key: string;
}) {
  return requestClient.post<InstallationApi.CheckInstallInfoResult>(
    '/api/appStore/createInstallInfo/',
    data,
  );
}

/** 组件批量安装-确认选择（unique_key 由本接口生成返回） */
export function createComponentInstallInfo(data: {
  high_availability: boolean;
  install_component: { name: string; version: string }[];
}) {
  return requestClient.post<InstallationApi.CheckInstallInfoResult>(
    '/api/appStore/createComponentInstallInfo/',
    data,
  );
}

// ── Step1 基本信息 ────────────────────────────────────────────────────

/** Step1 基础信息校验（通过 is_continue 放行；失败回传逐项 error_msg 回显） */
export function checkInstallInfo(data: {
  data: {
    basic: Record<string, any>[];
    dependence: Record<string, any>[];
  };
  unique_key: string;
}) {
  return requestClient.post<InstallationApi.CheckInstallInfoResult>(
    '/api/appStore/checkInstallInfo/',
    data,
  );
}

// ── Step2 服务分布 ────────────────────────────────────────────────────

/** 生成服务分布源数据（数据池/主机/级联树/with 服务） */
export function createServiceDistribution(uniqueKey: string) {
  return requestClient.post<InstallationApi.DistributionResult>(
    '/api/appStore/createServiceDistribution/',
    { unique_key: uniqueKey },
  );
}

/** 全量已安装服务（按 ip 分组，「已安装服务数」悬浮明细） */
export function listServiceByIp() {
  return requestClient.get<InstallationApi.InstallServiceMap>(
    '/api/appStore/listServiceByIp/',
  );
}

/** Step2 服务分布校验（数量校验失败后端抛错；主机校验失败回传 error_lst） */
export function checkServiceDistribution(data: {
  data: Record<string, string[]>;
  unique_key: string;
}) {
  return requestClient.post<InstallationApi.CheckDistributionResult>(
    '/api/appStore/checkServiceDistribution/',
    data,
  );
}

// ── Step3 修改配置 ────────────────────────────────────────────────────

/** 本次安装涉及的主机范围（ip 列表） */
export function getInstallHostRange(uniqueKey: string) {
  return requestClient.get<{ data: string[]; unique_key: string }>(
    '/api/appStore/getInstallHostRange/',
    { params: { unique_key: uniqueKey } },
  );
}

/** 某主机上待安装服务的参数/端口（前端按 ip 缓存，切回不重复请求） */
export function getInstallArgsByIp(params: { ip: string; unique_key: string }) {
  return requestClient.get<InstallationApi.ArgsByIpResult>(
    '/api/appStore/getInstallArgsByIp/',
    { params },
  );
}

/** 开始安装：校验并生成部署计划（失败回传逐字段 check_flag 明细） */
export function createInstallPlan(data: {
  data: Record<string, Record<string, any>[]>;
  run_user?: string;
  unique_key: string;
}) {
  return requestClient.post<InstallationApi.InstallPlanResult>(
    '/api/appStore/createInstallPlan/',
    data,
  );
}

// ── Step4 开始安装进度 ────────────────────────────────────────────────

/** 安装进度查询（status 0/1/4 时前端 5s 轮询） */
export function showInstallProcess(uniqueKey: string) {
  return requestClient.get<InstallationApi.InstallProcess>(
    '/api/appStore/showInstallProcess/',
    { params: { unique_key: uniqueKey } },
  );
}

/** 单服务安装日志（app_name + ip 定位，轮询/展开时拉取） */
export function showSingleServiceInstallLog(params: {
  app_name: string;
  ip: string;
  unique_key: string;
}) {
  return requestClient.get<InstallationApi.SingleServiceLog>(
    '/api/appStore/showSingleServiceInstallLog/',
    { params },
  );
}

// ── 顶层类型 re-export ──────────────────────────────────────────────
// vue-tsc 无法从 namespace 深层类型生成组件 props 元数据，
// 组件 props 一律引用以下顶层别名。

export type BasicItem = InstallationApi.BasicItem;
export type BasicService = InstallationApi.BasicService;
export type ConfigArg = InstallationApi.ConfigArg;
export type ConfigService = InstallationApi.ConfigService;
export type DependenceDeployMode = InstallationApi.DependenceDeployMode;
export type DependenceItem = InstallationApi.DependenceItem;
export type EntranceItem = InstallationApi.EntranceItem;
export type HostInfo = InstallationApi.HostInfo;
export type InstallProcess = InstallationApi.InstallProcess;
export type ProcessDetailItem = InstallationApi.ProcessDetailItem;
export type ProductInfo = InstallationApi.ProductInfo;
export type PoolItem = InstallationApi.PoolItem;
export type Step1Data = InstallationApi.Step1Data;
export type WithService = InstallationApi.WithService;
