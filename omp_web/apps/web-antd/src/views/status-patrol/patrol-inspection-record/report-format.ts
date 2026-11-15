import type { VNode } from 'vue';

import { h } from 'vue';

/** 状态小圆点（旧 renderCircular：10px 双色圆 + 文案） */
function discVNode(
  borderColor: string,
  backgroundColor: string,
  label: string,
): VNode {
  return h('div', [
    h('span', {
      style: {
        backgroundColor,
        borderColor,
        borderRadius: '50%',
        borderStyle: 'solid',
        borderWidth: '2px',
        display: 'inline-block',
        height: '10px',
        marginRight: '5px',
        width: '10px',
      },
    }),
    label,
  ]);
}

/**
 * 巡检报告单元格通用渲染（旧 config.formatTableRenderData 语义）：
 * 空值 → '-'；0/active/true → 绿点正常；1/unactive/false → 红点异常；
 * CREATE/UPDATE/DELETE → 增加/更新/删除；其余原样输出。
 */
export function formatCell(text: unknown): string | VNode {
  if (text === undefined || text === null || text === '') return '-';
  if (text === 0 || text === 'active' || text === true) {
    return discVNode('rgb(84, 187, 166)', 'rgb(238, 250, 244)', '正常');
  }
  if (text === 1 || text === 'unactive' || text === false) {
    return discVNode('#da4e48', '#fbe7e6', '异常');
  }
  if (text === 'CREATE') return '增加';
  if (text === 'UPDATE') return '更新';
  if (text === 'DELETE') return '删除';
  return text as string;
}

/** 风险级别胶囊（旧 ColorfulNotice：55×20 圆角描边块） */
function noticeVNode(
  backgroundColor: string,
  borderColor: string,
  text: string,
): VNode {
  return h(
    'div',
    {
      style: {
        alignItems: 'center',
        backgroundColor,
        border: `1px solid ${borderColor}`,
        borderRadius: '4px',
        color: 'rgba(0, 0, 0, 0.6)',
        display: 'flex',
        fontSize: '12px',
        height: '20px',
        justifyContent: 'center',
        margin: '0 auto',
        width: '55px',
      },
    },
    [text],
  );
}

/** 风险级别单元格渲染（critical-严重 / warning-警告 / 其余 '-'） */
export function riskLevelCell({
  record,
}: {
  record: { risk_level: string };
}): string | VNode {
  if (record.risk_level === 'critical') {
    return noticeVNode('#fbe7e6', '#da4e48', '严重');
  }
  if (record.risk_level === 'warning') {
    return noticeVNode('rgba(247, 231, 24,.2)', '#f5c773', '警告');
  }
  return '-';
}

/** 报告耗时格式化（旧 formatTime：X天X小时X分X秒；0/空 → "0"） */
export function formatReportDuration(
  text: null | number | undefined = 0,
): string {
  const second = Math.round(Number(text));
  const days = Math.floor(second / 86_400);
  const hours = Math.floor((second % 86_400) / 3600);
  const minutes = Math.floor((second % 3600) / 60);
  const seconds = Math.floor(second % 60);

  if (days > 0) return `${days}天${hours}小时${minutes}分${seconds}秒`;
  if (hours > 0) return `${hours}小时${minutes}分${seconds}秒`;
  if (minutes > 0) return `${minutes}分${seconds}秒`;
  if (seconds > 0) return `${seconds}秒`;
  return `${text ?? 0}`;
}
