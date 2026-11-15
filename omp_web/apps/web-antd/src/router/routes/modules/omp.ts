import type { RouteRecordRaw } from 'vue-router';

/**
 * OMP 菜单骨架。
 *
 * 路径与旧前端 router.config.js 保持一致。
 * notInMenu 的隐藏路由（详情/安装流程页等）提前登记，
 * 保证从其他页面跳转时路径不缺。
 */

const routes: RouteRecordRaw[] = [
  {
    meta: { icon: 'lucide:monitor', order: 1, title: '资源管理' },
    name: 'ResourceManagement',
    path: '/resource-management',
    children: [
      {
        name: 'MachineManagement',
        path: 'machine-management',
        component: () => import('#/views/machine-management/index.vue'),
        meta: { icon: 'lucide:server', title: '主机管理' },
      },
    ],
  },
  {
    meta: { icon: 'lucide:layout-grid', order: 2, title: '应用管理' },
    name: 'ApplicationManagement',
    path: '/application_management',
    children: [
      {
        name: 'ServiceManagement',
        path: 'service_management',
        component: () => import('#/views/service-management/index.vue'),
        meta: { icon: 'lucide:boxes', title: '服务管理' },
      },
      {
        name: 'AppStore',
        path: 'app_store',
        component: () => import('#/views/app-store/index.vue'),
        meta: { icon: 'lucide:store', title: '应用商店' },
      },
      {
        name: 'ComponentInstallation',
        path: 'app_store/component_installation/:name',
        component: () =>
          import('#/views/app-store/install-wizard/component-installation.vue'),
        meta: { hideInMenu: true, title: '组件安装' },
      },
      {
        name: 'ApplicationInstallation',
        path: 'app_store/application_installation/:name',
        component: () =>
          import('#/views/app-store/install-wizard/application-installation.vue'),
        meta: { hideInMenu: true, title: '应用安装' },
      },
      {
        name: 'AppServiceDetail',
        path: 'app_store/app-service-detail/:name/:verson',
        // 服务/组件详情共用组件，按路径区分类型
        component: () => import('#/views/app-store/app-store-detail.vue'),
        meta: { hideInMenu: true, title: '应用商店服务详情' },
      },
      {
        name: 'AppComponentDetail',
        path: 'app_store/app-component-detail/:name/:verson',
        component: () => import('#/views/app-store/app-store-detail.vue'),
        meta: { hideInMenu: true, title: '应用商店组件详情' },
      },
      {
        name: 'Installation',
        path: 'app_store/installation',
        component: () => import('#/views/installation/index.vue'),
        meta: { hideInMenu: true, title: '批量安装' },
      },
      {
        name: 'InstallationRecord',
        path: 'install-record',
        component: () => import('#/views/installation-record/index.vue'),
        meta: { icon: 'lucide:list-checks', title: '执行记录' },
      },
      {
        name: 'ServiceUpgrade',
        path: 'app_store/service_upgrade',
        component: () => import('#/views/app-store/service-upgrade.vue'),
        meta: { hideInMenu: true, title: '服务升级' },
      },
      {
        name: 'ServiceRollback',
        path: 'app_store/service_rollback',
        component: () => import('#/views/app-store/service-rollback.vue'),
        meta: { hideInMenu: true, title: '服务回滚' },
      },
      {
        name: 'DeploymentPlan',
        path: 'deployment-plan',
        component: () => import('#/views/deployment-plan/index.vue'),
        meta: { icon: 'lucide:rocket', title: '部署模板' },
      },
      {
        name: 'GetService',
        path: 'get-service',
        component: () => import('#/views/app-store/get-service.vue'),
        meta: { hideInMenu: true, title: '服务纳管' },
      },
    ],
  },
  {
    meta: { icon: 'lucide:activity', order: 3, title: '应用监控' },
    name: 'ApplicationMonitoring',
    path: '/application-monitoring',
    children: [
      {
        name: 'ExceptionList',
        path: 'exception-list',
        component: () => import('#/views/exception-list/index.vue'),
        meta: { icon: 'lucide:triangle-alert', title: '异常清单' },
      },
      {
        name: 'AlarmLog',
        path: 'alarm-log',
        component: () => import('#/views/alarm-log/index.vue'),
        meta: { icon: 'lucide:bell-ring', title: '告警记录' },
      },
      {
        name: 'MonitoringSettings',
        path: 'monitoring-settings',
        component: () => import('#/views/monitoring-settings/index.vue'),
        meta: { icon: 'lucide:settings-2', title: '监控设置' },
      },
    ],
  },
  {
    meta: { icon: 'lucide:heart-pulse', order: 4, title: '故障自愈' },
    name: 'FaultSelfHealing',
    path: '/fault-selfHealing',
    children: [
      {
        name: 'SelfHealingStrategy',
        path: 'selfHealing-strategy',
        component: () => import('#/views/self-healing-strategy/index.vue'),
        meta: { icon: 'lucide:clipboard-list', title: '自愈策略' },
      },
      {
        name: 'SelfHealingRecord',
        path: 'selfHealing-record',
        component: () => import('#/views/self-healing-record/index.vue'),
        meta: { icon: 'lucide:history', title: '自愈记录' },
      },
    ],
  },
  {
    meta: { icon: 'lucide:eye', order: 5, title: '状态巡检' },
    name: 'StatusPatrol',
    path: '/status-patrol',
    children: [
      {
        name: 'PatrolInspectionRecord',
        path: 'patrol-inspection-record',
        component: () =>
          import('#/views/status-patrol/patrol-inspection-record/index.vue'),
        meta: { icon: 'lucide:file-search', title: '巡检记录' },
      },
      {
        name: 'PatrolInspectionDetail',
        path: 'patrol-inspection-record/status-patrol-detail/:id',
        component: () =>
          import('#/views/status-patrol/patrol-inspection-record/detail.vue'),
        meta: { hideInMenu: true, title: '巡检记录详情' },
      },
      {
        name: 'PatrolStrategy',
        path: 'patrol-strategy',
        component: () => import('#/views/patrol-strategy/index.vue'),
        meta: { icon: 'lucide:calendar-clock', title: '巡检策略' },
      },
    ],
  },
  {
    meta: { icon: 'lucide:list', order: 6, title: '指标中心' },
    name: 'RuleCenter',
    path: '/rule-center',
    children: [
      {
        name: 'RuleIndicator',
        path: 'indicator-rule',
        component: () => import('#/views/rule-indicator/index.vue'),
        meta: { icon: 'lucide:ruler', title: '指标规则' },
      },
      {
        name: 'RuleExtend',
        path: 'extend-rule',
        component: () => import('#/views/rule-extend/index.vue'),
        meta: { icon: 'lucide:expand', title: '扩展指标' },
      },
    ],
  },
  {
    meta: { icon: 'lucide:database-backup', order: 7, title: '数据备份' },
    name: 'DataBackup',
    path: '/data-backup',
    children: [
      {
        name: 'BackupStrategy',
        path: 'backup-strategy',
        component: () => import('#/views/data-backup/backup-strategy.vue'),
        meta: { icon: 'lucide:calendar-check', title: '备份策略' },
      },
      {
        name: 'BackupRecords',
        path: 'backup-record',
        component: () => import('#/views/data-backup/backup-record.vue'),
        meta: { icon: 'lucide:archive', title: '备份记录' },
      },
    ],
  },
  {
    meta: { icon: 'lucide:wrench', order: 8, title: '实用工具' },
    name: 'Utilities',
    path: '/utilitie',
    children: [
      {
        name: 'ToolManagement',
        path: 'tool-management',
        component: () => import('#/views/utilities/tool-management.vue'),
        meta: { icon: 'lucide:briefcase', title: '工具管理' },
      },
      {
        name: 'ToolDetails',
        path: 'tool-management/tool-management-detail/:id',
        component: () => import('#/views/utilities/tool-management-detail.vue'),
        meta: { hideInMenu: true, title: '工具详情' },
      },
      {
        name: 'ToolExecution',
        path: 'tool-management/tool-execution/:id',
        component: () => import('#/views/utilities/tool-execution.vue'),
        meta: { hideInMenu: true, title: '工具执行' },
      },
      {
        name: 'ToolExecutionResults',
        path: 'tool-management/tool-execution-results/:id',
        component: () => import('#/views/utilities/tool-execution-results.vue'),
        meta: { hideInMenu: true, title: '执行结果' },
      },
      {
        name: 'TaskRecord',
        path: 'task-record',
        component: () => import('#/views/utilities/task-record.vue'),
        meta: { icon: 'lucide:timer', title: '任务记录' },
      },
    ],
  },
  {
    meta: { icon: 'lucide:scroll-text', order: 9, title: '操作记录' },
    name: 'OperationRecord',
    path: '/operation-record',
    children: [
      {
        name: 'LoginLog',
        path: 'login-log',
        component: () => import('#/views/operation-record/login-log.vue'),
        meta: { icon: 'lucide:log-in', title: '登录日志' },
      },
      {
        name: 'SystemLog',
        path: 'system-log',
        component: () => import('#/views/operation-record/system-log.vue'),
        meta: { icon: 'lucide:file-text', title: '系统记录' },
      },
    ],
  },
  {
    meta: { icon: 'lucide:settings', order: 10, title: '系统设置' },
    name: 'SystemSettings',
    path: '/system-settings',
    children: [
      {
        name: 'UserManagement',
        path: 'user-management',
        component: () => import('#/views/user-management/index.vue'),
        meta: { icon: 'lucide:user-cog', title: '用户管理' },
      },
      {
        name: 'EnvManagement',
        path: 'env-management',
        component: () =>
          import('#/views/system-settings/env-management/index.vue'),
        meta: { icon: 'lucide:layers', title: '环境管理' },
      },
      {
        name: 'SystemManagement',
        path: 'system-management',
        component: () => import('#/views/system-management/index.vue'),
        meta: { icon: 'lucide:server-cog', title: '系统管理' },
      },
      {
        name: 'EmailSettings',
        path: 'email-settings',
        component: () => import('#/views/email-settings/index.vue'),
        meta: { icon: 'lucide:mail', title: '邮件管理' },
      },
    ],
  },
  {
    /** 仪表盘（无子菜单的顶级路由，旧前端同位置） */
    component: () => import('#/views/homepage/index.vue'),
    meta: { icon: 'lucide:layout-dashboard', order: 0, title: '仪表盘' },
    name: 'Homepage',
    path: '/homepage',
  },
];

export default routes;
