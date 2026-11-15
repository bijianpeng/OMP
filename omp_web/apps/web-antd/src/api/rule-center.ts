import { requestClient } from '#/api/request';

/**
 * 指标中心（指标规则 / 扩展指标）接口。
 * 路径与旧前端 requestApi.js ruleCenter 段保持一致。
 */
export namespace RuleCenterApi {
  /** 指标规则（后端 AlertRule） */
  export interface QuotaRule {
    alert: string;
    compare_str: string;
    /** 1 可删除 / 2 禁止删除（内置规则） */
    forbidden: number;
    for_time: string;
    id: number;
    /** 自定义 PromSQL 表达式 */
    expr?: null | string;
    name?: null | string;
    quota_type: 0 | 1;
    severity: 'critical' | 'warning';
    status: 0 | 1;
    /** 自定义 PromSQL 的告警标题/消息 */
    summary?: null | string;
    description?: null | string;
    service?: null | string;
    threshold_value: number;
  }

  /** 指标规则创建/更新载荷（id 存在即为更新） */
  export interface QuotaRulePayload {
    alert: string;
    compare_str: string;
    description?: string;
    env_id: number;
    expr?: string;
    for_time: string;
    id?: number;
    /** 内置指标时携带 {description,name,expr,service} */
    builtins_quota?: {
      description: null | string;
      expr: string;
      name: string;
      service: string;
    };
    quota_type: number;
    service?: string;
    severity: string;
    status: number;
    summary?: string;
    threshold_value: number;
  }

  /** 内置指标（后端 Rule，按 service 分组返回） */
  export interface BuiltinsRule {
    description: null | string;
    expr: string;
    name: string;
    service: string;
  }

  /** PromSQL 测试结果行（Prometheus instant query） */
  export interface PromSqlTestMetric {
    metric: Record<string, any>;
    value: [number, string];
  }

  /** 扩展指标（后端 CustomScript） */
  export interface CustomScript {
    bound_hosts: string[];
    bound_hosts_num: number;
    description: string;
    enabled: number;
    id: number;
    metric_num: number;
    metrics: string[];
    scrape_interval: number;
    script_content: string;
    script_name: string;
  }

  /** 扩展指标采集作业状态（Prometheus target） */
  export interface ScriptJobInfo {
    last_error: null | string;
    last_scrape_duration: null | number;
    scrape_url: null | string;
    status: null | string;
  }

}

/** 查询指标规则列表（分页 + 规则名称模糊搜索 + 排序） */
export function listQuotaRules(params: {
  alert?: null | string;
  ordering?: null | string;
  page: number;
  size: number;
}) {
  return requestClient.get<{
    count: number;
    results: RuleCenterApi.QuotaRule[];
  }>('/api/promemonitor/quota/', { params });
}

/** 查询内置指标（按服务名分组的字典） */
export function listBuiltinsRules() {
  return requestClient.get<Record<string, RuleCenterApi.BuiltinsRule[]>>(
    '/api/promemonitor/builtinRule/',
  );
}

/**
 * 添加/修改指标规则（同一端点：载荷带 id 即更新，env_id 取当前环境上下文）。
 * 后端直接下发 Prometheus 规则文件并热重载，故提示文案为「下发成功」。
 */
export function saveQuotaRule(payload: RuleCenterApi.QuotaRulePayload) {
  return requestClient.post('/api/promemonitor/quota/', payload);
}

/** 删除指标规则（query 传 id） */
export function deleteQuotaRule(id: number) {
  return requestClient.delete('/api/promemonitor/quota/', {
    params: { id },
  });
}

/** 批量启用/停用指标规则 */
export function batchUpdateQuotaRules(ids: number[], status: 0 | 1) {
  return requestClient.post('/api/promemonitor/batchUpdateRule/', {
    ids,
    status,
  });
}

/** 测试 PromSQL（即时查询，失败由全局拦截器提示） */
export function testPromSql(expr: string) {
  return requestClient.post<RuleCenterApi.PromSqlTestMetric[]>(
    '/api/promemonitor/testPromSql/',
    { expr },
  );
}

/** 查询扩展指标列表（分页 + 描述模糊搜索） */
export function listCustomScripts(params: {
  description?: null | string;
  ordering?: null | string;
  page: number;
  size: number;
}) {
  return requestClient.get<{
    count: number;
    results: RuleCenterApi.CustomScript[];
  }>('/api/promemonitor/customScript/', { params });
}

/** 添加扩展指标（multipart：采集脚本文件 + 探测周期） */
export function createCustomScript(data: FormData) {
  return requestClient.post('/api/promemonitor/customScript/', data);
}

/** 修改扩展指标（描述/探测周期/绑定主机） */
export function updateCustomScript(
  id: number,
  data: {
    bound_hosts: string[];
    description: string;
    scrape_interval: number;
  },
) {
  return requestClient.put(`/api/promemonitor/customScript/${id}/`, data);
}

/** 删除扩展指标 */
export function deleteCustomScript(id: number) {
  return requestClient.delete(`/api/promemonitor/customScript/${id}/`);
}

/** 查询扩展指标采集作业状态（Prometheus targets） */
export function queryScriptJobInfo(id: number) {
  return requestClient.get<RuleCenterApi.ScriptJobInfo[]>(
    '/api/promemonitor/customScriptJobInfo/',
    { params: { id } },
  );
}
