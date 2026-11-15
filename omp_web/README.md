# omp_web — OMP 运维管理平台前端

基于 [vue-vben-admin v5](https://github.com/vbenjs/vue-vben-admin)(裁剪版 monorepo,仅保留 `apps/web-antd`:ant-design-vue 4 + Vue 3.5 + Vite + Tailwind 4 + TypeScript)。

## 快速开始

```bash
cd omp_web
pnpm install
pnpm dev:antd     # 开发模式(http://localhost:5666,端口占用自动顺延)
pnpm build:antd   # 生产构建
pnpm test:unit    # vitest 单测(根目录运行)
```

要求:Node ≥ 22.18、pnpm ≥ 10(corepack 自动管理版本)。

**构建产物**:输出至 `omp_web/dist/`(同时打包 `dist.zip`),与平台部署链路(如 `scripts/source/update_conf.py` 的静态目录)兼容。

## 后端联调

- dev 代理:`apps/web-antd/vite.config.ts` 将 `/api`、`/tool`、`/package_hub`、`/proxy` 代理到后端(默认 `http://127.0.0.1:19001`,按实际部署修改)
- 后端统一响应包 `{code: 0成功|1失败, message, data}`;错误走 HTTP 200 + code=1
- 认证:`POST /api/login/`(用户名/密码 RSA 公钥加密,公钥在 `apps/web-antd/src/utils/rsa.ts`);JWT 会话在 `jwtToken` cookie,**请求层不发 Authorization 头**(后端仅认 `JWT` 前缀,发 `Bearer` 会认证失败)

## 关键开发约定

1. **API 层**:接口定义放 `apps/web-antd/src/api/<模块>.ts`,路径全 `/api/...` 前缀(`VITE_GLOB_API_URL` 为空,不要拼 baseURL)
2. **请求**:统一用 `#/api/request` 的 `requestClient`(自动解包 data、未认证登出、cookie 凭证、150s 超时)
3. **列表页模板**:参照 `apps/web-antd/src/views/operation-record/login-log.vue`(最简)与 `views/alarm-log/index.vue`(复杂交互:列筛选/批量已读/iframe 抽屉)。**布局三层基线(缺一不可)**:① `<Page content-class="min-h-0 overflow-hidden">` ② `gridOptions: { height: 'auto' }` ③ `useVbenVxeGrid({ class: 'flex flex-col', gridClass: 'min-h-0 flex-1' })`——表体内部滚动、分页钉视口底、700×600~1920×1080 自适应。**vxe 远程排序/筛选四开关**:`sortConfig/filterConfig: {remote:true}` + `proxyConfig: {sort:true, filter:true}`,`sorts`/`filters` 从 `ajax.query` **第一参**解构。**排序映射**:asc→`field`(无前缀)、desc→`-field`(标准 DRF;个别后端自定义 `asc` 参数的接口以其实际契约为准)
4. **路由/菜单**:`apps/web-antd/src/router/routes/modules/omp.ts`;新增页面在该模块登记并指向对应 component
5. **用户信息**:OMP 无 /me 接口,登录后以表单用户名 `GET /api/users/users/?username=` 过滤获取角色(SuperUser/ReadOnlyUser),菜单不做角色过滤(权限在后端中间件)
6. **图表**:用 `@vben/plugins/echarts` 的 `EchartsUI` + `useEcharts`(echarts 按需注册,无需自装依赖);环形进度等已封装见 `apps/web-antd/src/components/progress-ring.vue`
7. **query 透传**:跨页跳转一律用 query;`router/guard.ts` 已处理「带 query 直访/刷新被动态路由首载 replace 剥参」问题,目标页从 `route.query` 读初始筛选
