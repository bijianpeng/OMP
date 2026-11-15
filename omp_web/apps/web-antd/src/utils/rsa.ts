/**
 * OMP 登录密码 RSA 加密。
 *
 * 与后端 `users/views.py` 的 `decrypt_rsa` 配对，公钥来自旧前端
 * `omp_web/public/pubKey.json`（对应后端 config/private_key.pem）。
 */
import JSEncrypt from 'jsencrypt';

/** OMP 平台登录公钥（2048-bit，PEM body） */
const PUBLIC_KEY = [
  'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwv4dqlvcYtrPJsCL/VuX',
  '0u4FZm2E0du1m01gUnp3afSkx+u2GTXptpS7dNfTLguu1HjJUzkEIGaJGG/x/PR2',
  'Zs6I/UmIFWj6tdmfBBlrVRETnm8tCAdO9/1zjzz4wB2yuHduBK6TYwhXfZOCg3LO',
  'j+QVpUYqyq3lqjPN+C6QbFzgk8FwMHr+R3OzZe9nsaNZOHRbSmu6NU5zkIdnScQw',
  'IiWIe9nZMpoTUe45FtYPj7SHiCItDOtbXGbyNOP5k5RhIQtJiEJgVOzGeRSaQAj6',
  'UfLClsa43ZXfXIZ+BfOO8GZBXmHeRHRs/Prw3Io4n0gXKpgrd6MxwfpoxmXEyoRU',
  'GwIDAQAB',
].join('\n');

/** RSA 公钥加密（与旧前端 utils/tool.js 的 encrypt 等价） */
export function rsaEncrypt(plain: string): string {
  const encrypt = new JSEncrypt();
  encrypt.setPublicKey(PUBLIC_KEY);
  const cipher = encrypt.encrypt(plain);
  if (!cipher) {
    throw new Error('RSA encrypt failed');
  }
  return cipher;
}
