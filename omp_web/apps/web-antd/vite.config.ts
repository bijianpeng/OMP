import { defineConfig } from '@vben/vite-config';

export default defineConfig(async () => {
  return {
    application: {},
    vite: {
      build: {
        // 产物输出到 omp_web/dist,兼容既有部署链路(scripts/source/update_conf.py)
        outDir: '../../dist',
        emptyOutDir: true,
      },
      server: {
        proxy: {
          '/api': {
            changeOrigin: true,
            // OMP 后端（接口路径自带 /api 前缀，无需 rewrite）
            target: 'http://127.0.0.1:19001',
            ws: true,
          },
          '/tool': {
            changeOrigin: true,
            // 工具 logo / 安装包 / 执行产物等静态资源由后端同源提供（生产同源，dev 需代理）
            target: 'http://127.0.0.1:19001',
          },
          '/package_hub': {
            changeOrigin: true,
            // 工具 tar 安装包等仓库静态资源（db_models tool.tar_url 指向 /package_hub/tool/tar/...）
            target: 'http://127.0.0.1:19001',
          },
          '/proxy': {
            changeOrigin: true,
            // 主机/服务监控面板 iframe（hosts.monitor_url 为相对路径 /proxy/v1/grafana/...，
            // 由后端网关反代 Grafana；dev 下不代理会被 SPA fallback 吞成 404 兜底页）
            target: 'http://127.0.0.1:19001',
          },
        },
      },
    },
  };
});
