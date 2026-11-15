/**
 * 轻量 Markdown → HTML 渲染（工具详情页 README 用）。
 *
 * 旧前端用 markdown-it + highlight.js；新工程未引入该依赖
 * （避免为单一页面新增 workspace 依赖），此处实现常用语法子集：
 * 标题 / 粗斜体 / 行内代码 / 围栏代码块 / 无序有序列表 / 引用 /
 * 分隔线 / 链接 / GFM 表格。整段先做 HTML 转义，再生成受控标签，
 * 不存在 XSS 注入面。
 */

/** HTML 转义 */
function escapeHtml(text: string): string {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

/** 行内语法：行内代码 → 粗体/斜体 → 链接（行内代码先行，避免内容被二次处理） */
function renderInline(text: string): string {
  const codeSlots: string[] = [];
  let out = text.replaceAll(
    /`([^`]+)`/g,
    (_m, code: string) => {
      codeSlots.push(code);
      return `\u0000${codeSlots.length - 1}\u0000`;
    },
  );
  out = out
    .replaceAll(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replaceAll(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replaceAll(
      /\[([^\]]+)\]\(([^)\s]+)\)/g,
      (_m, label: string, href: string) => {
        // 链接协议白名单：拦截 javascript: 等（对齐旧前端 markdown-it validateLink 防线）
        const safe = /^(?:https?:\/\/|\/|#|mailto:)/.test(href);
        return safe
          ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`
          : label;
      },
    );
  return out.replaceAll(
    /\u0000(\d+)\u0000/g,
    (_m, idx: string) =>
      `<code class="md-inline-code">${escapeHtml(codeSlots[Number(idx)]!)}</code>`,
  );
}

/** 单元格行拆分（忽略行内代码中的 | —— OMP README 场景足够） */
function splitRow(line: string): string[] {
  return line
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((cell) => cell.trim());
}

/** 是否为表格分隔行（如 | --- | :---: |） */
function isAlignRow(line: string): boolean {
  return /^\s*\|?[\s:|-]+\|?\s*$/.test(line) && line.includes('-');
}

/**
 * 渲染 Markdown 文本为 HTML 片段。
 */
export function renderMarkdown(source?: null | string): string {
  if (!source) return '';
  const lines = escapeHtml(source).replaceAll('\r\n', '\n').split('\n');
  const html: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i]!;

    // 围栏代码块
    const fence = /^\s*```(\w*)/.exec(line);
    if (fence) {
      const codeLines: string[] = [];
      i += 1;
      while (i < lines.length && !/^\s*```/.test(lines[i]!)) {
        codeLines.push(lines[i]!);
        i += 1;
      }
      i += 1; // 跳过收尾 ```
      html.push(`<pre class="md-code"><code>${codeLines.join('\n')}</code></pre>`);
      continue;
    }

    // 标题
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1]!.length;
      html.push(
        `<h${level} class="md-h md-h${level}">${renderInline(heading[2]!)}</h${level}>`,
      );
      i += 1;
      continue;
    }

    // 分隔线
    if (/^\s*([-*_])\s*(\1\s*){2,}$/.test(line)) {
      html.push('<hr class="md-hr">');
      i += 1;
      continue;
    }

    // 表格：表头行 + 分隔行 + 数据行
    if (line.includes('|') && i + 1 < lines.length && isAlignRow(lines[i + 1]!)) {
      const header = splitRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i]!.includes('|')) {
        rows.push(splitRow(lines[i]!));
        i += 1;
      }
      html.push(
        `<table class="md-table"><thead><tr>${header.map((cell) => `<th>${renderInline(cell)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${renderInline(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table>`,
      );
      continue;
    }

    // 引用块
    if (/^\s*&gt;\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (i < lines.length && /^\s*&gt;\s?/.test(lines[i]!)) {
        quoteLines.push(lines[i]!.replace(/^\s*&gt;\s?/, ''));
        i += 1;
      }
      html.push(
        `<blockquote class="md-quote">${renderInline(quoteLines.join('<br>'))}</blockquote>`,
      );
      continue;
    }

    // 列表（无序 / 有序，支持单层嵌套缩进项）
    const bullet = /^(\s*)([-*+])\s+(.*)$/;
    const ordered = /^(\s*)(\d+\.)\s+(.*)$/;
    if (bullet.test(line) || ordered.test(line)) {
      const isOrdered = ordered.test(line);
      const items: string[] = [];
      while (i < lines.length) {
        const current = lines[i]!;
        const matcher = isOrdered ? ordered : bullet;
        const matched = matcher.exec(current);
        if (matched) {
          items.push(`<li>${renderInline(matched[3]!)}</li>`);
          i += 1;
        } else if (/^\s+\S/.test(current) && items.length > 0) {
          // 缩进续行并入上一项
          items[items.length - 1] = items[items.length - 1]!.replace(
            /<\/li>$/,
            ` ${renderInline(current.trim())}</li>`,
          );
          i += 1;
        } else {
          break;
        }
      }
      const tag = isOrdered ? 'ol' : 'ul';
      html.push(`<${tag} class="md-list">${items.join('')}</${tag}>`);
      continue;
    }

    // 空行
    if (!line.trim()) {
      i += 1;
      continue;
    }

    // 普通段落（连续非空非块级行合并）
    const paragraphLines: string[] = [];
    while (
      i < lines.length &&
      lines[i]!.trim() &&
      !/^\s*(```|#{1,6}\s|&gt;|([-*+]\s|\d+\.\s))/.test(lines[i]!) &&
      !lines[i]!.includes('|')
    ) {
      paragraphLines.push(lines[i]!);
      i += 1;
    }
    if (paragraphLines.length > 0) {
      html.push(`<p class="md-p">${renderInline(paragraphLines.join('<br>'))}</p>`);
    } else {
      // 表格等未归入上方分支的行，兜底推进避免死循环
      html.push(`<p class="md-p">${renderInline(lines[i]!)}</p>`);
      i += 1;
    }
  }
  return html.join('\n');
}
