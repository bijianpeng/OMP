import { preferences } from '@vben/preferences';

/** iframe 地址白名单：仅允许站内绝对路径（排除协议相对的 // 与反斜杠 /\，WHATWG URL 会把 \ 规范化为 / 后指向外域）或 http(s) 地址 */
export function isSafeFrameSrc(src?: null | string): boolean {
  return /^(?:\/(?!\/|\\)|https?:\/\/)/.test(src ?? '');
}

/**
 * Grafana 面板 URL 注入主题参数（theme=dark|light）。
 * 非 Grafana 地址原样返回；已带 theme 参数的覆盖为当前主题。
 * 响应式：模板绑定中调用时主题切换会触发 iframe 重载跟随。
 */
export function withGrafanaTheme(url: string): string {
  if (!url || !url.toLowerCase().includes('/grafana/')) {
    return url;
  }
  try {
    // 站内绝对路径（/ 开头）解析后保持相对形式，避免硬编码 origin
    const isRelative = url.startsWith('/');
    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set(
      'theme',
      preferences.theme.mode === 'dark' ? 'dark' : 'light',
    );
    return isRelative
      ? `${parsed.pathname}${parsed.search}${parsed.hash}`
      : parsed.href;
  } catch {
    return url;
  }
}
