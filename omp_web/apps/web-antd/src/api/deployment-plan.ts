import { requestClient } from '#/api/request';

export namespace DeploymentPlanApi {
  /** 部署模板列表项 */
  export interface PlanRecord {
    created: string;
    create_user: string;
    host_num: number;
    id: number;
    /** 导入生成的安装任务唯一键（安装记录跳转用） */
    operation_uuid: string;
    plan_name: string;
    product_num: number;
    service_num: number;
  }

  /** 主机/服务分布校验响应（error 非空时行级失败原因已标注） */
  export interface ValidateResult<T> {
    correct: T[];
    error: Record<string, any>[];
  }

  /** xlsx 服务分布行（中文表头映射后） */
  export interface ServiceDataItem {
    instance_name: string;
    memory?: string;
    mode?: string;
    role?: string;
    row: number;
    service_name: string;
    vip?: string;
  }

  /** 服务分布校验载荷 */
  export interface ServiceValidatePayload {
    instance_name_ls: string[];
    service_data_ls: ServiceDataItem[];
  }

  /** 部署模板导入载荷（主机已 batchImport 纳管后调用） */
  export interface PlanImportPayload {
    instance_info_ls: { instance_name: string; run_user?: string }[];
    service_data_ls: ServiceDataItem[];
  }

  /** 导入完成后的数量汇总 */
  export interface ImportSummary {
    host_num: number;
    operation_uuid: string;
    product_num: number;
    service_num: number;
  }
}

/** 部署模板列表（DRF 分页 {count, results}） */
export function listDeploymentPlans(params: {
  ordering?: null | string;
  page: number;
  size: number;
}) {
  return requestClient.get<{
    count: number;
    results: DeploymentPlanApi.PlanRecord[];
  }>('/api/appStore/deploymentPlanList/', { params });
}

/** 快速部署可用性：已安装服务后不可再导入（data 布尔） */
export function getDeploymentOperable() {
  return requestClient.get<boolean>('/api/appStore/deploymentOperable');
}

/** 服务分布校验（主机数据校验复用 hosts.ts 的 batchValidateHosts） */
export function validateDeploymentServices(
  data: DeploymentPlanApi.ServiceValidatePayload,
) {
  return requestClient.post<
    DeploymentPlanApi.ValidateResult<DeploymentPlanApi.ServiceDataItem>
  >('/api/appStore/deploymentPlanValidate/', data);
}

/** 导入部署模板 */
export function importDeploymentPlan(
  data: DeploymentPlanApi.PlanImportPayload,
) {
  return requestClient.post<DeploymentPlanApi.ImportSummary>(
    '/api/appStore/deploymentPlanImport/',
    data,
  );
}

/** 批量查询主机 agent 状态：全部在线返回 true（快速部署等待 agent 就绪轮询用） */
export function getHostsAgentStatus(ipList: string[]) {
  return requestClient.post<boolean>('/api/hosts/hostsAgentStatus/', {
    ip_list: ipList,
  });
}

/** 进入安装任务（导入成功后自动触发，返回安装任务信息） */
export function retryInstall(uniqueKey: string) {
  return requestClient.post('/api/appStore/retryInstall/', {
    unique_key: uniqueKey,
  });
}
