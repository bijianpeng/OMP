import { requestClient } from '#/api/request';

/**
 * 应用商店接口。组件（app_* 前缀）与应用服务（pro_* 前缀）字段结构平行，
 * 类型按可选字段合一，消费端按当前 tabKey 取对应前缀。
 */
export namespace AppStoreApi {
  /** 商店卡片（components/services 列表项，前后缀随类型而异） */
  export interface StoreCard {
    app_description?: null | string;
    /** logo 为后端下发的 SVG 字符串（v-html 渲染），可能为空 */
    app_logo?: null | string;
    app_name?: null | string;
    app_version?: null | string;
    instance_number?: null | number;
    pro_description?: null | string;
    pro_logo?: null | string;
    pro_name?: null | string;
    pro_version?: null | string;
  }

  /** 服务实例信息（组件实例与服务实例字段不同，合一可选） */
  export interface InstanceInfo {
    app_name?: null | string;
    app_version?: null | string;
    created?: null | string;
    host_ip?: null | string;
    instance_name?: null | string;
    mode?: null | string;
    /** 端口对象数组，展示取各项 default 拼接 */
    service_port?: null | { default?: null | number }[];
    version?: null | string;
  }

  /** 详情版本项（同一版本重复发布会合并 instances_info） */
  export interface VersionItem {
    app_dependence?: null | string;
    app_description?: null | string;
    app_instances_info?: InstanceInfo[];
    /** 类别标签数组，展示 join(',') */
    app_labels?: null | string[];
    app_logo?: null | string;
    app_name?: null | string;
    app_operation_user?: null | string;
    app_package_md5?: null | string;
    app_version?: null | string;
    created?: null | string;
    pro_dependence?: null | string;
    pro_description?: null | string;
    pro_instances_info?: InstanceInfo[];
    pro_labels?: null | string[];
    pro_logo?: null | string;
    pro_name?: null | string;
    pro_operation_user?: null | string;
    pro_package_md5?: null | string;
    pro_services?: {
      created?: null | string;
      md5?: null | string;
      name?: null | string;
      version?: null | string;
    }[];
    pro_version?: null | string;
  }

  /** 组件/应用详情（versions 为各发布记录） */
  export interface StoreDetail {
    app_name?: null | string;
    pro_name?: null | string;
    versions: VersionItem[];
  }

  /** 安装包校验/发布结果行（package_status 见 STATUS_TEXT） */
  export interface PackageResult {
    error_msg?: null | string;
    package_name?: null | string;
    package_status: number;
  }

  /** 扫描结果（stage_status 值域见 scan-server-modal 内注释） */
  export interface ScanResult {
    message?: null | string;
    /** 各安装包校验/发布明细（与 package_names_lst 下标对应） */
    package_detail?: {
      message?: null | string;
      status: number;
    }[];
    /** 扫描命令下发返回的包名（结果查询时回传） */
    package_names?: null | string[];
    package_names_lst?: null | string[];
    stage_status: string;
    /** 扫描命令下发返回的操作唯一键 */
    uuid?: null | string;
  }

  /** 可删除包项：产品类型 name/versions 为 "名称|版本" 复合串（展示时拆分） */
  export interface DeletablePackage {
    name: string;
    versions: string[];
  }
}

/** 组件查询（app_name 模糊 / type 标签筛选） */
export function queryComponents(params: {
  app_name?: null | string;
  page: number;
  size: number;
  type?: null | string;
}) {
  return requestClient.get<{ count: number; results: AppStoreApi.StoreCard[] }>(
    '/api/appStore/components/',
    { params },
  );
}

/** 应用服务查询（pro_name 模糊 / type 标签筛选） */
export function queryServices(params: {
  page: number;
  pro_name?: null | string;
  size: number;
  type?: null | string;
}) {
  return requestClient.get<{ count: number; results: AppStoreApi.StoreCard[] }>(
    '/api/appStore/services/',
    { params },
  );
}

/** 商店标签列表（label_type：0 组件 / 1 服务） */
export function queryLabels(params: { label_type: 0 | 1 }) {
  return requestClient.get<string[]>('/api/appStore/labels/', { params });
}

/** 基础组件详情 */
export function queryComponentDetail(appName: string) {
  return requestClient.get<AppStoreApi.StoreDetail>(
    '/api/appStore/componentDetail/',
    { params: { app_name: appName } },
  );
}

/** 应用服务详情 */
export function queryServiceDetail(proName: string) {
  return requestClient.get<AppStoreApi.StoreDetail>(
    '/api/appStore/serviceDetail/',
    { params: { pro_name: proName } },
  );
}

/** 删除已上传安装包（发布中断 / 单个文件移除时调用） */
export function removePackages(data: {
  package_names: string[];
  uuid: number | string;
}) {
  return requestClient.post('/api/appStore/remove/', data);
}

/** 安装包校验结果（package_status=2 校验中时前端 2s 轮询） */
export function queryPackVerificationResults(operationUuid: number | string) {
  return requestClient.get<AppStoreApi.PackageResult[]>(
    '/api/appStore/pack_verification_results/',
    { params: { operation_uuid: operationUuid } },
  );
}

/** 发布命令下发（成功后转 publish 结果轮询） */
export function publishPackages(uuid: number | string) {
  return requestClient.post('/api/appStore/publish/', { uuid });
}

/** 发布结果查询（GET 同路径，package_status=2/5 时前端 2s 轮询） */
export function queryPublishResults(operationUuid: number | string) {
  return requestClient.get<AppStoreApi.PackageResult[]>(
    '/api/appStore/publish/',
    { params: { operation_uuid: operationUuid } },
  );
}

/** 扫描服务端安装包命令下发（返回待扫描包名，空数组即服务端无包） */
export function executeLocalPackageScan() {
  return requestClient.post<AppStoreApi.ScanResult>(
    '/api/appStore/executeLocalPackageScan/',
  );
}

/** 扫描状态查询（stage_status 含 "ing" 时前端 2s 轮询） */
export function queryLocalPackageScanResult(params: {
  package_names: string;
  uuid: string;
}) {
  return requestClient.get<AppStoreApi.ScanResult>(
    '/api/appStore/localPackageScanResult/',
    { params },
  );
}

// ── 商店包删除（更多菜单「删除」弹窗） ──────────────────────────────

/** 可删除包列表（type：component 组件 name 无竖线 / product 产品名带 "|版本"） */
export function listDeletablePackages(type: 'component' | 'product') {
  return requestClient.get<{ data: AppStoreApi.DeletablePackage[]; type: string }>(
    '/api/appStore/delete/',
    { params: { type } },
  );
}

/**
 * 删除商店安装包（data 逐项 name+versions，复合串原样回传）。
 * 后端校验存在已安装实例时抛错（全局拦截器提示），整批不删。
 */
export function deletePackages(data: {
  data: AppStoreApi.DeletablePackage[];
  type: 'component' | 'product';
}) {
  return requestClient.post('/api/appStore/delete/', data);
}
