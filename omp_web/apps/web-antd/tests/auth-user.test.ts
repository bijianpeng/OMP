import { describe, expect, it } from 'vitest';

import { pickCurrentUser } from '../src/api/core/auth';

describe('pickCurrentUser — 用户列表精确匹配当前登录用户', () => {
  it('用户名互为包含时（admin2 先建、admin 后建）选中 admin 而非首条 admin2', () => {
    const results = [
      { id: 2, role: 'admin', username: 'admin2' },
      { id: 1, role: 'superuser', username: 'admin' },
    ];
    const picked = pickCurrentUser(results, 'admin');
    expect(picked?.username).toBe('admin');
    expect(picked?.id).toBe(1);
  });

  it('无精确匹配时返回 undefined（上层抛出获取失败）', () => {
    const results = [{ id: 2, role: 'admin', username: 'admin2' }];
    expect(pickCurrentUser(results, 'admin')).toBeUndefined();
  });

  it('空列表返回 undefined', () => {
    expect(pickCurrentUser([], 'admin')).toBeUndefined();
  });
});
