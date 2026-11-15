import { describe, expect, it } from 'vitest';

import { buildLoginParams } from '../src/api/core/auth';
import { rsaEncrypt } from '../src/utils/rsa';

describe('rsaEncrypt — OMP 登录 RSA 公钥加密', () => {
  it('返回非空密文，长度大于 100（2048-bit RSA 密文块特征）', () => {
    const cipher = rsaEncrypt('admin');
    expect(typeof cipher).toBe('string');
    expect(cipher.length).toBeGreaterThan(100);
  });

  it('同一明文两次加密结果不同（RSA 填充随机）', () => {
    expect(rsaEncrypt('Passw0rd!demo')).not.toEqual(rsaEncrypt('Passw0rd!demo'));
  });
});

describe('buildLoginParams — OMP 登录请求体构造', () => {
  it('username/password 为密文，remember 原样传递', () => {
    const params = buildLoginParams('admin', 'Passw0rd!demo', true);
    expect(params.username).not.toBe('admin');
    expect(params.password).not.toBe('Passw0rd!demo');
    expect(params.username!.length).toBeGreaterThan(100);
    expect(params.password!.length).toBeGreaterThan(100);
    expect(params.remember).toBe(true);
  });
});
