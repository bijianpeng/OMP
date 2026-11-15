import { requestClient } from '#/api/request';

/**
 * 组件/应用安装向导接口。
 *
 * 与 app-store.ts 拆分：本文件只承载安装编排链路
 * （入口数据 → executeInstall 校验下发 → installHistory 进度轮询），
 * 商店卡片/详情/扫描发布接口见 app-store.ts（批 J 维护）。
 *
 * 组件入口（app_* 前缀字段）与应用入口（pro_* 前缀）结构平行，
 * 依赖项（组件 app_dependence 与应用 dependence_services_info）同构。
 */
export namespace InstallApi {
  /** 部署模式项（value 提交时 JSON.stringify 整项） */
  export interface DeployMode {
    key: string;
    name: string;
  }

  /** 安装参数/端口项（dir_key 标记数据分区字段如 "{data_path}"，port 提交键不含它） */
  export interface ArgItem {
    default?: null | number | string;
    dir_key?: null | boolean | string;
    key: string;
    name: string;
  }

  /** 已安装实例（use_exist_services 复用项来源） */
  export interface InstanceInfo {
    id: number;
    ip: string;
    service_instance_name: string;
  }

  export interface ClusterInfo {
    cluster_name: string;
    id: number;
  }

  /** 依赖服务解析项（后端 SerDependenceParseUtils.run_ser 输出） */
  export interface DependenceItem {
    app_install_args: ArgItem[];
    app_port: ArgItem[];
    cluster_info: ClusterInfo[];
    deploy_mode: DeployMode[];
    instance_info: InstanceInfo[];
    is_base_env: boolean;
    is_in_hub?: boolean;
    is_pack_exist: boolean;
    name: string;
    process_continue: boolean;
    process_message?: string;
    version: string;
  }

  /** 组件安装入口项（每版本一条） */
  export interface ComponentEntranceItem {
    app_dependence: DependenceItem[];
    app_install_args: ArgItem[];
    app_name: string;
    app_port: ArgItem[];
    app_version: string;
    deploy_mode: DeployMode[];
    process_continue: boolean;
    process_message?: string;
  }

  /** 应用安装入口：产品内包含的服务项 */
  export interface ProServiceItem {
    app_dependence?: DependenceItem[];
    app_install_args: ArgItem[];
    app_port: ArgItem[];
    deploy_mode: DeployMode[];
    name: string;
    process_continue: boolean;
    process_message?: string;
    version: string;
  }

  /** 应用安装入口项（每版本一条） */
  export interface ProductEntranceItem {
    dependence_services_info: DependenceItem[];
    pro_name: string;
    pro_services: ProServiceItem[];
    pro_version: string;
  }

  /** executeInstall 单服务载荷（default 为用户输入，后端逐项校验回传 check 明细） */
  export interface InstallServicePayload {
    app_install_args: Array<ArgItem & { default?: any }>;
    app_port: Array<ArgItem & { default?: any }>;
    /** 应用安装不传（组件安装传 JSON.parse 后的部署模式对象） */
    deploy_mode?: DeployMode;
    ip: string;
    name: string;
    service_instance_name: string;
    version: string;
  }

  /** executeInstall 载荷（install_type：0 组件 / 1 应用） */
  export interface ExecuteInstallPayload {
    /**
     * 后端 ListField<DictField> 接受任意键：主服务为 InstallServicePayload
     * 形态；依赖项沿旧契约整项展开（保留 cluster_info 等），仅覆写执行字段。
     */
    install_services: Record<string, any>[];
    install_type: 0 | 1;
    use_exist_services: Record<string, any>[];
  }

  /** 校验结果项（is_valid_flag=false 时逐字段回填用） */
  export type Checkable<T> = T & {
    check_flag?: boolean;
    check_msg?: string;
  };

  export type CheckableArgItem = Checkable<ArgItem & { default?: any }>;

  /** executeInstall 响应单服务项（载荷回传 + 逐字段 check 明细） */
  export interface InstallServiceResult extends InstallServicePayload {
    app_install_args: CheckableArgItem[];
    app_port: CheckableArgItem[];
    check_flag?: boolean;
    check_msg?: string;
  }

  /** executeInstall 响应 */
  export interface ExecuteInstallResult {
    install_services: null | InstallServiceResult[];
    is_valid_flag: boolean;
    is_valid_msg?: string;
    operation_uuid?: string;
    use_exist_services: null | Checkable<Record<string, any>>[];
  }

  /** 单服务安装明细（日志五阶段拼接） */
  export interface InstallDetailItem {
    ip: string;
    log: string;
    service_instance_name: string;
    service_name: string;
    status: number;
  }

  /** 安装进度（install_status：0 待安装 1 安装中 2 成功 3 失败 4 注册中） */
  export interface InstallHistoryItem {
    detail_lst: InstallDetailItem[];
    install_args?: Record<string, any>;
    install_log?: string;
    install_status: number;
    install_status_msg: string;
    operation_uuid: string;
  }
}

/** 组件安装入口（app_name 精确匹配，返回各发布版本） */
export function queryComponentEntrance(appName: string) {
  return requestClient.get<InstallApi.ComponentEntranceItem[]>(
    '/api/appStore/componentEntrance/',
    { params: { app_name: appName } },
  );
}

/** 应用（产品）安装入口（pro_name 精确匹配，返回各发布版本） */
export function queryProductEntrance(proName: string) {
  return requestClient.get<InstallApi.ProductEntranceItem[]>(
    '/api/appStore/productEntrance/',
    { params: { pro_name: proName } },
  );
}

/** 执行安装（先校验载荷，is_valid_flag=false 时回传逐字段 check 明细） */
export function executeInstall(data: InstallApi.ExecuteInstallPayload) {
  return requestClient.post<InstallApi.ExecuteInstallResult>(
    '/api/appStore/executeInstall/',
    data,
  );
}

/** 安装进度查询（install_status 为 0/1 时前端 2s 轮询） */
export function queryInstallHistory(operationUuid: string) {
  return requestClient.get<InstallApi.InstallHistoryItem[]>(
    '/api/appStore/installHistory/',
    { params: { operation_uuid: operationUuid } },
  );
}

// ── 顶层类型 re-export ──────────────────────────────────────────────
// vue-tsc 无法从 namespace 深层类型生成组件 props 元数据，
// 组件 props 一律引用以下顶层别名。

export type ArgItem = InstallApi.ArgItem;
export type ComponentEntranceItem = InstallApi.ComponentEntranceItem;
export type DependenceItem = InstallApi.DependenceItem;
export type ExecuteInstallResult = InstallApi.ExecuteInstallResult;
export type InstallDetailItem = InstallApi.InstallDetailItem;
export type InstallHistoryItem = InstallApi.InstallHistoryItem;
export type ProductEntranceItem = InstallApi.ProductEntranceItem;
export type ProServiceItem = InstallApi.ProServiceItem;
