import { requestClient } from '#/api/request';

export namespace PatrolStrategyApi {
  /** 巡检定时任务（按 job_type 单例，0=深度分析） */
  export interface InspectionCrontab {
    /** 定时详情：均为 crontab 字符串，"*" 表示不指定 */
    crontab_detail: {
      day: string;
      day_of_week: string;
      hour: string;
      minute: string;
      month: string;
    };
    env: number;
    id: number;
    /** 是否开启定时：0=开启，1=关闭（与常规布尔语义相反，历史约定） */
    is_start_crontab: number;
    job_name: string;
    job_type: number;
  }

  /** 巡检定时任务提交体 */
  export interface InspectionCrontabPayload {
    crontab_detail: PatrolStrategyApi.InspectionCrontab['crontab_detail'];
    /** 当前环境 id（取环境上下文） */
    env: number;
    is_start_crontab: number;
    job_name: string;
    job_type: number;
  }

  /** 巡检报告推送设置 */
  export interface InspectionEmailSetting {
    send_email: boolean;
    to_users?: null | string;
  }
}

/** 查询巡检定时任务（按 job_type 单例；任务不存在时后端 404，调用方需 catch） */
export function queryPatrolStrategy(jobType: number = 0) {
  return requestClient.get<PatrolStrategyApi.InspectionCrontab>(
    `/api/inspection/crontab/${jobType}/`,
  );
}

/** 创建巡检定时任务 */
export function createPatrolStrategy(
  data: PatrolStrategyApi.InspectionCrontabPayload,
) {
  return requestClient.post('/api/inspection/crontab/', data);
}

/** 更新巡检定时任务 */
export function updatePatrolStrategy(
  jobType: number,
  data: PatrolStrategyApi.InspectionCrontabPayload,
) {
  return requestClient.put(`/api/inspection/crontab/${jobType}/`, data);
}

/** 查询巡检报告推送设置 */
export function queryInspectionEmailSetting() {
  return requestClient.get<Partial<PatrolStrategyApi.InspectionEmailSetting>>(
    '/api/inspection/inspectionSendEmailSetting/',
  );
}

/** 更新巡检报告推送设置（后端以 POST 表达更新语义，env_id 取当前环境上下文） */
export function updateInspectionEmailSetting(data: {
  /** 当前环境 id（取环境上下文） */
  env_id: number;
  send_email: boolean;
  to_users?: null | string;
}) {
  return requestClient.post('/api/inspection/inspectionSendEmailSetting/', data);
}
