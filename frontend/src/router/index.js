// 路由配置 - 定义页面路由，含图标和菜单元信息
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: {
      title: '仪表盘',
      icon: 'icon-dashboard',
      requiresAuth: false,
    },
  },
  {
    path: '/accounts',
    name: 'Accounts',
    component: () => import('../views/Accounts.vue'),
    meta: {
      title: '账号管理',
      icon: 'icon-user',
      requiresAuth: false,
    },
  },
  {
    path: '/checkin',
    name: 'Checkin',
    component: () => import('../views/Checkin.vue'),
    meta: {
      title: '每日签到',
      icon: 'icon-calendar',
      requiresAuth: false,
    },
  },
  {
    path: '/proxy',
    name: 'ApiProxy',
    component: () => import('../views/ApiProxy.vue'),
    meta: {
      title: 'API代理',
      icon: 'icon-link',
      requiresAuth: false,
    },
  },
  {
    path: '/packages',
    name: 'Packages',
    component: () => import('../views/Packages.vue'),
    meta: {
      title: '资源包管理',
      icon: 'icon-storage',
      requiresAuth: false,
    },
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('../views/Logs.vue'),
    meta: {
      title: '日志',
      icon: 'icon-file',
      requiresAuth: false,
    },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/Settings.vue'),
    meta: {
      title: '数据管理',
      icon: 'icon-settings',
      requiresAuth: false,
    },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 设置页面标题
router.afterEach((to) => {
  const base = 'WorkBuddy Tool'
  document.title = to.meta.title ? `${to.meta.title} · ${base}` : base
})

export default router
