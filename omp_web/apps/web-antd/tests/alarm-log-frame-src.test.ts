import { describe, expect, it } from 'vitest';

import { isSafeFrameSrc } from '../src/utils/frame-src';

describe('isSafeFrameSrc — 告警页 iframe 地址白名单', () => {
  it('协议相对地址（// 开头）不允许，防 //evil.com 绕过', () => {
    expect(isSafeFrameSrc('//evil.com')).toBe(false);
    expect(isSafeFrameSrc('//evil.com/x/y')).toBe(false);
  });

  it('反斜杠地址（/\\ 开头）不允许，防 /\\evil.com 绕过（WHATWG URL 把 \\ 规范化为 /）', () => {
    expect(isSafeFrameSrc('/\\evil.com')).toBe(false);
    expect(isSafeFrameSrc('\\/evil.com')).toBe(false);
  });

  it('站内绝对路径与 http(s) 地址允许', () => {
    expect(isSafeFrameSrc('/api/x')).toBe(true);
    expect(isSafeFrameSrc('/proxy/v1/grafana/d/9CWBz0bik/panel')).toBe(true);
    expect(isSafeFrameSrc('https://grafana.example.com/d/1')).toBe(true);
    expect(isSafeFrameSrc('http://192.0.2.1:3000/d/1')).toBe(true);
  });

  it('其他协议与空值不允许', () => {
    expect(isSafeFrameSrc('javascript:alert(1)')).toBe(false);
    expect(isSafeFrameSrc('data:text/html;base64,xxx')).toBe(false);
    expect(isSafeFrameSrc('ftp://files.example.com')).toBe(false);
    expect(isSafeFrameSrc('')).toBe(false);
    expect(isSafeFrameSrc(null)).toBe(false);
    expect(isSafeFrameSrc(undefined)).toBe(false);
  });
});
