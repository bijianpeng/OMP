/**
 * OMP 统一响应包 {code, message, data} 相关工具。
 *
 * OMP 后端对未认证请求返回 HTTP 200 + {code:1, message:'未认证'}
 * （而非 401），需要单独识别以触发登出。
 */

/** OMP 后端未认证时 message 的固定文案 */
const UNAUTHORIZED_MESSAGE = '未认证';

/**
 * 判断响应体是否为 OMP 的「未认证」响应。
 *
 * 仅当 code=1 且 message 精确匹配「未认证」时判定为 true，
 * 业务错误（如「主机不存在」）不触发登出。
 */
export function isOmpUnauthorized(body: unknown): boolean {
  if (typeof body !== 'object' || body === null) {
    return false;
  }
  const { code, message } = body as { code?: unknown; message?: unknown };
  return code === 1 && message === UNAUTHORIZED_MESSAGE;
}
