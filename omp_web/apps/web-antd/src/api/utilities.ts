import { requestClient } from '#/api/request';

export namespace UtilitiesApi {
  /** 工具执行记录（后端 ToolExecuteMainHistory） */
  export interface TaskRecord {
    duration?: null | string;
    id: number;
    kind?: null | number;
    start_time?: null | string;
    status?: null | number;
    task_name?: null | string;
    tool_id?: null | number;
  }

  /** 工具卡片（后端 ToolListSerializer） */
  export interface ToolCard {
    description?: null | string;
    id: number;
    kind: number;
    /** logo 相对路径（如 /media/...），可能为空 */
    logo?: null | string;
    name: string;
    used_number: number;
  }

  /** 脚本参数定义 */
  export interface ScriptArg {
    default?: any;
    key: string;
    name: string;
    options?: string[];
    required: boolean;
    type: 'file' | 'input' | 'select';
  }

  /** 工具详情（后端 ToolInfoDetailSerializer） */
  export interface ToolDetail {
    description?: null | string;
    kind: number;
    logo?: null | string;
    name: string;
    readme_info?: null | string;
    script_args: ScriptArg[];
    script_path?: null | string;
    /** 安装包相对路径（下载时补前缀 /） */
    tar_url?: null | string;
    /** 模板示例文件 */
    templates: { name: string; sub_url: string }[];
    target_name: string;
  }

  /** 工具执行表单配置（后端 ToolFormDetailSerializer） */
  export interface ToolForm {
    default_form: {
      runuser?: null | string;
      task_name?: null | string;
      timeout?: null | number;
    };
    id: number;
    name: string;
    script_args: ScriptArg[];
  }

  /** 执行对象（主机或服务实例） */
  export interface TargetObject {
    host_agent_state: string;
    id: number;
    instance_name: string;
    ip: null | string;
    /** 服务类工具的连接参数（端口等），主机类工具无此字段 */
    modifiable_kwargs?: Record<string, string>;
  }

  /** 工具执行结果（后端 ToolDetailSerializer） */
  export interface ToolResult {
    count?: number;
    duration?: null | string;
    end_time?: null | string;
    operator?: null | string;
    run_user?: null | string;
    start_time?: null | string;
    status?: number;
    task_name?: null | string;
    time_out?: null | number;
    tool?: { target_name: string };
    tool_args: { name: string; value: string }[];
    /** 每个目标对象的执行明细 */
    tool_detail: { ip: string; log?: null | string; status: number; url: string }[];
  }

  /** 答案提交请求体 */
  export interface FormAnswerPayload {
    default_form: Record<string, any>;
    script_args: ScriptArg[];
  }
}

/** 任务记录（注意：接口无尾斜杠） */
export function queryTaskRecord(params: {
  kind?: null | number;
  ordering?: null | string;
  page: number;
  search?: null | string;
  size: number;
}) {
  return requestClient.get<{
    count: number;
    results: UtilitiesApi.TaskRecord[];
  }>('/api/tool/execute-history', { params });
}

/** 工具列表（kind：0 管理工具 / 2 安全工具；name icontains 模糊匹配） */
export function queryToolList(params: {
  kind?: null | number;
  name?: null | string;
  page: number;
  size: number;
}) {
  return requestClient.get<{
    count: number;
    results: UtilitiesApi.ToolCard[];
  }>('/api/tool/toolList/', { params });
}

/** 工具详情 */
export function queryToolDetail(id: number | string) {
  return requestClient.get<UtilitiesApi.ToolDetail>(
    `/api/tool/toolList/${id}/`,
  );
}

/** 工具执行表单配置（默认表单 + 脚本参数定义） */
export function queryToolForm(id: number | string) {
  return requestClient.get<UtilitiesApi.ToolForm>(`/api/tool/form/${id}/`);
}

/** 工具执行对象分页列表 */
export function queryToolTargetObject(
  id: number | string,
  params: { page: number; size: number },
) {
  return requestClient.get<{
    count: number;
    results: UtilitiesApi.TargetObject[];
  }>(`/api/tool/form/${id}/target-object`, { params });
}

/**
 * 下发工具执行任务。成功时 data 含执行历史 id，跳转执行结果页使用。
 */
export function executeToolForm(
  id: number | string,
  payload: UtilitiesApi.FormAnswerPayload,
) {
  return requestClient.post<{ id: number }>(
    `/api/tool/form/${id}/answer`,
    payload,
  );
}

/** 工具执行结果（status 0/1 时前端需轮询刷新） */
export function queryToolResult(id: number | string) {
  return requestClient.get<UtilitiesApi.ToolResult>(`/api/tool/result/${id}/`);
}
