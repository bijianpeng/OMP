import { describe, expect, it, vi } from 'vitest';

// request.ts 依赖 #/store（会级联拉起 router/pinia），单测里 mock 掉
vi.mock('#/store', () => ({
  useAuthStore: () => ({ logout: vi.fn(async () => {}) }),
}));

import { isOmpUnauthorized } from '../src/api/omp-response';
import { requestClient } from '../src/api/request';

describe('isOmpUnauthorized — OMP 未认证响应识别', () => {
  it('code=1 且 message 含「未认证」时判定为未认证', () => {
    expect(isOmpUnauthorized({ code: 1, data: null, message: '未认证' })).toBe(
      true,
    );
  });

  it('code=1 的业务错误不算未认证', () => {
    expect(
      isOmpUnauthorized({ code: 1, data: null, message: '主机不存在' }),
    ).toBe(false);
  });

  it('code=0 成功响应不算未认证', () => {
    expect(
      isOmpUnauthorized({ code: 0, data: {}, message: 'success' }),
    ).toBe(false);
  });

  it('非对象响应不算未认证', () => {
    expect(isOmpUnauthorized(null)).toBe(false);
    expect(isOmpUnauthorized(undefined)).toBe(false);
    expect(isOmpUnauthorized('text')).toBe(false);
  });
});

describe('requestClient — OMP 会话配置', () => {
  it('携带 cookie 凭证（JWT 会话在 cookie）', () => {
    expect(requestClient.instance.defaults.withCredentials).toBe(true);
  });

  it('超时 150 秒（对齐旧前端 timeout 150000）', () => {
    expect(requestClient.instance.defaults.timeout).toBe(150_000);
  });
});
