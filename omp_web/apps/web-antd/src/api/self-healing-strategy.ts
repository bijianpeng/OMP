import { requestClient } from '#/api/request';

export namespace SelfHealingStrategyApi {
  /** 自愈策略项 */
  export interface Strategy {
    /** 探测周期（分钟） */
    fresh_rate: number;
    id: number;
    /** 自愈类型：0=启动 [start]，1=重启 [restart] */
    instance_tp: number;
    /** 重试次数上限 */
    max_healing_count: number;
    /** 自愈维度列表：host / component / service */
    repair_instance: string[];
    /** 是否生效 */
    used: boolean;
  }

  /** 自愈策略提交体 */
  export interface StrategyPayload {
    fresh_rate: number;
    instance_tp: number;
    max_healing_count: number;
    repair_instance: string[];
    used: boolean;
  }
}

/** 自愈策略列表（后端返回全量数组，无分页/排序/筛选契约） */
export function listSelfHealingStrategies() {
  return requestClient.get<SelfHealingStrategyApi.Strategy[]>(
    '/api/services/SelfHealingSetting/',
  );
}

/** 添加自愈策略 */
export function createSelfHealingStrategy(
  data: SelfHealingStrategyApi.StrategyPayload,
) {
  return requestClient.post('/api/services/SelfHealingSetting/', data);
}

/** 编辑自愈策略 */
export function updateSelfHealingStrategy(
  id: number,
  data: SelfHealingStrategyApi.StrategyPayload,
) {
  return requestClient.put(`/api/services/SelfHealingSetting/${id}/`, data);
}

/** 删除自愈策略 */
export function deleteSelfHealingStrategy(id: number) {
  return requestClient.delete(`/api/services/SelfHealingSetting/${id}/`);
}
