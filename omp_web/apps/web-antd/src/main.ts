import { initPreferences, updatePreferences } from '@vben/preferences';
import { unmountGlobalLoading } from '@vben/utils';

import { overridesPreferences, preferencesExtension } from './preferences';

/**
 * 应用初始化完成之后再进行页面加载渲染
 */
async function initApplication() {
  // name用于指定项目唯一标识
  // 用于区分不同项目的偏好设置以及存储数据的key前缀以及其他一些需要隔离的数据
  const env = import.meta.env.PROD ? 'prod' : 'dev';
  const appVersion = import.meta.env.VITE_APP_VERSION;
  const namespace = `${import.meta.env.VITE_APP_NAMESPACE}-${appVersion}-${env}`;

  // app偏好设置初始化
  await initPreferences({
    extension: preferencesExtension,
    namespace,
    overrides: overridesPreferences,
  });

  // preferences 的合并顺序是 localStorage 缓存优先于 overrides：
  // 老用户缓存里的 widget 开关（语言/时区/登出位置）会盖掉 overridesPreferences，
  // 这里在启动时强制再刷一次并回写缓存（幂等），保证顶栏定制对所有人生效。
  // app.name 同理：品牌文案属部署级配置（.env 的 VITE_APP_TITLE），
  // 需强制刷新以免老缓存里改名前的旧名称一直生效。
  updatePreferences({
    app: {
      name: import.meta.env.VITE_APP_TITLE,
    },
    widget: {
      languageToggle: false,
      logoutButtonPosition: 'user-dropdown',
      timezone: false,
    },
  });

  // 启动应用并挂载
  // vue应用主要逻辑及视图
  const { bootstrap } = await import('./bootstrap');
  await bootstrap(namespace);

  // 移除并销毁loading
  unmountGlobalLoading();
}

void initApplication();
