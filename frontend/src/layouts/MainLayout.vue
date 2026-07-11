<script setup>
// 主布局 - Arco Layout：可折叠侧边栏 + 顶部工具栏 + 全局搜索 + 通知中心 + 主题切换
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  IconMenuFold,
  IconMenuUnfold,
  IconMoon,
  IconSun,
  IconSearch,
  IconNotification,
  IconDashboard,
  IconUser,
  IconCalendar,
  IconLink,
  IconStorage,
  IconFile,
  IconSettings,
  IconBulb,
} from '@arco-design/web-vue/es/icon'
import { useThemeStore } from '../stores/theme'

const route = useRoute()
const router = useRouter()
const theme = useThemeStore()
// 解构 isDark 为顶层 ref，避免模板中 ref 对象不自动解包导致切换失效
const { isDark } = theme

// 菜单项配置
const menuItems = [
  { index: '/', title: '仪表盘', icon: IconDashboard },
  { index: '/accounts', title: '账号管理', icon: IconUser },
  { index: '/checkin', title: '每日签到', icon: IconCalendar },
  { index: '/proxy', title: 'API代理', icon: IconLink },
  { index: '/packages', title: '资源包管理', icon: IconStorage },
  { index: '/logs', title: '日志', icon: IconFile },
  { index: '/settings', title: '数据管理', icon: IconSettings },
]

// 侧边栏折叠状态（持久化）
const collapsed = ref(localStorage.getItem('workbuddy-collapsed') === 'true' || localStorage.getItem('antigravity-collapsed') === 'true')
const isMobile = ref(false)
const mobileDrawerVisible = ref(false)

function detectViewport() {
  isMobile.value = window.innerWidth < 768
  // 移动端默认折叠
  if (isMobile.value) {
    collapsed.value = true
  }
}

function toggleCollapsed() {
  // 移动端：打开抽屉而非折叠
  if (isMobile.value) {
    mobileDrawerVisible.value = true
    return
  }
  collapsed.value = !collapsed.value
  localStorage.setItem('workbuddy-collapsed', String(collapsed.value))
  localStorage.removeItem('antigravity-collapsed')
}

function handleMenuClick(key) {
  router.push(key)
  if (isMobile.value) {
    mobileDrawerVisible.value = false
  }
}

const activeMenuKey = computed(() => route.path)

// ─── 全局搜索 ───
const searchVisible = ref(false)
const searchKeyword = ref('')
const searchOptions = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return []
  return menuItems
    .filter((m) => m.title.toLowerCase().includes(kw))
    .map((m) => ({
      label: m.title,
      value: m.index,
    }))
})

function openSearch() {
  searchVisible.value = true
  searchKeyword.value = ''
  nextTick(() => {
    document.querySelector('.global-search-input input')?.focus()
  })
}

function handleSearchSelect(value) {
  if (value) {
    router.push(value)
    searchVisible.value = false
  }
}

// 快捷键：Ctrl/Cmd + K 唤出全局搜索
function handleKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    openSearch()
  }
}

// ─── 通知中心 ───
const notifyVisible = ref(false)
const notifications = ref([])
const notifUnreadCount = ref(0)

// 拉取一次通知（复用 dashboard 数据简单实现）
async function loadNotifications() {
  // 简化版：仅展示功能入口，未对接后端通知接口
  notifications.value = []
  notifUnreadCount.value = 0
}

watch(notifyVisible, (v) => {
  if (v) loadNotifications()
})

import { onBeforeUnmount, onMounted } from 'vue'

const appVersion = ref({ version: '1.0.0', build_time: '', git_sha: '' })

const versionLabel = computed(() => {
  const v = appVersion.value.version || '1.0.0'
  return v.startsWith('v') ? v : `v${v}`
})

const versionHint = computed(() => {
  const parts = []
  if (appVersion.value.build_time) parts.push(`部署 ${appVersion.value.build_time}`)
  if (appVersion.value.git_sha) parts.push(appVersion.value.git_sha)
  return parts.join(' · ') || 'WorkBuddy Tool'
})

async function loadVersion() {
  try {
    const resp = await fetch('/api/version')
    if (!resp.ok) return
    const data = await resp.json()
    appVersion.value = {
      version: data.version || '1.0.0',
      build_time: data.build_time || '',
      git_sha: data.git_sha || '',
    }
  } catch {
    // 角标失败不影响主流程
  }
}

onMounted(() => {
  detectViewport()
  window.addEventListener('resize', detectViewport)
  window.addEventListener('keydown', handleKeydown)
  loadNotifications()
  loadVersion()
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', detectViewport)
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <a-layout class="layout-root">
    <!-- 桌面侧边栏 -->
    <a-layout-sider
      v-if="!isMobile"
      :width="220"
      :collapsed-width="64"
      :collapsible="false"
      :collapsed="collapsed"
      :resize-directions="['right']"
      :resize-w="0"
      breakpoint="md"
      class="layout-sider"
    >
      <div class="logo">
        <div class="logo-icon">
          <IconBulb />
        </div>
        <span v-if="!collapsed" class="logo-text">WorkBuddy</span>
      </div>
      <a-menu
        :selected-keys="[activeMenuKey]"
        :collapsed="collapsed"
        :auto-open-selected="false"
        @menu-item-click="handleMenuClick"
        class="layout-menu"
      >
        <a-menu-item v-for="item in menuItems" :key="item.index">
          <template #icon>
            <component :is="item.icon" />
          </template>
          {{ item.title }}
        </a-menu-item>
      </a-menu>
      <div class="sider-version" :title="versionHint">
        <span class="sider-version-tag">{{ versionLabel }}</span>
        <span v-if="!collapsed && appVersion.build_time" class="sider-version-time">
          {{ appVersion.build_time }}
        </span>
      </div>
    </a-layout-sider>

    <!-- 移动端抽屉式侧边栏 -->
    <a-drawer
      v-if="isMobile"
      v-model:visible="mobileDrawerVisible"
      :width="220"
      placement="left"
      :footer="false"
      :header="false"
    >
      <div class="logo">
        <div class="logo-icon"><IconBulb /></div>
        <span class="logo-text">WorkBuddy</span>
      </div>
      <a-menu
        :selected-keys="[activeMenuKey]"
        @menu-item-click="handleMenuClick"
        class="layout-menu"
      >
        <a-menu-item v-for="item in menuItems" :key="item.index">
          <template #icon>
            <component :is="item.icon" />
          </template>
          {{ item.title }}
        </a-menu-item>
      </a-menu>
      <div class="sider-version" :title="versionHint">
        <span class="sider-version-tag">{{ versionLabel }}</span>
        <span v-if="appVersion.build_time" class="sider-version-time">
          {{ appVersion.build_time }}
        </span>
      </div>
    </a-drawer>

    <a-layout class="layout-body">
      <!-- 顶部工具栏 -->
      <a-layout-header class="layout-header">
        <div class="header-left">
          <a-button type="text" class="collapse-btn" @click="toggleCollapsed">
            <template #icon>
              <IconMenuUnfold v-if="collapsed && !isMobile" />
              <IconMenuFold v-else />
            </template>
          </a-button>
          <a-breadcrumb class="header-breadcrumb">
            <a-breadcrumb-item>
              <IconDashboard />
            </a-breadcrumb-item>
            <a-breadcrumb-item>{{ route.meta.title || 'WorkBuddy Tool' }}</a-breadcrumb-item>
          </a-breadcrumb>
        </div>

        <div class="header-right">
          <a-button type="text" class="header-action" @click="openSearch" title="搜索 (Ctrl+K)">
            <template #icon><IconSearch /></template>
          </a-button>
          <a-badge :count="notifUnreadCount" :max-count="9" dot>
            <a-button type="text" class="header-action" @click="notifyVisible = true" title="通知">
              <template #icon><IconNotification /></template>
            </a-button>
          </a-badge>
          <a-button type="text" class="header-action" @click="theme.toggle()" title="切换主题">
            <template #icon>
              <IconMoon v-if="!isDark" />
              <IconSun v-else />
            </template>
          </a-button>
        </div>
      </a-layout-header>

      <!-- 主内容区 -->
      <a-layout-content class="layout-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </a-layout-content>
    </a-layout>
  </a-layout>

  <!-- 全局搜索弹窗 -->
  <a-modal
    v-model:visible="searchVisible"
    :footer="false"
    :mask-closable="true"
    :mask="true"
    :unmount-on-close="false"
    :modal-style="{ width: '600px', padding: 0 }"
    :body-style="{ padding: 0 }"
    title=""
    :closable="false"
  >
    <div class="global-search">
      <a-input
        v-model="searchKeyword"
        class="global-search-input"
        placeholder="搜索功能菜单（Ctrl+K）"
        allow-clear
        size="large"
        :bordered="false"
      >
        <template #prefix><IconSearch /></template>
      </a-input>
      <a-list v-if="searchOptions.length" class="search-options">
        <a-list-item
          v-for="opt in searchOptions"
          :key="opt.value"
          @click="handleSearchSelect(opt.value)"
          class="search-option-item"
        >
          <a-list-item-meta :title="opt.label">
            <template #avatar>
              <IconDashboard />
            </template>
          </a-list-item-meta>
        </a-list-item>
      </a-list>
      <a-empty v-else-if="searchKeyword" description="没有匹配的菜单" style="padding: 24px" />
      <div v-else class="search-tip">输入关键词以快速跳转</div>
    </div>
  </a-modal>

  <!-- 通知中心抽屉 -->
  <a-drawer
    v-model:visible="notifyVisible"
    :width="380"
    title="通知中心"
    placement="right"
  >
    <a-empty v-if="!notifications.length" description="暂无通知">
      <template #image>
        <IconNotification />
      </template>
    </a-empty>
    <a-list v-else :data="notifications">
      <template #item="{ item }">
        <a-list-item>
          <a-list-item-meta :title="item.title" :description="item.desc" />
        </a-list-item>
      </template>
    </a-list>
  </a-drawer>
</template>

<style lang="scss" scoped>
.layout-root {
  height: 100%;
}

.layout-sider {
  background-color: var(--color-bg-2);
  border-right: 1px solid var(--color-border-2);
  display: flex;
  flex-direction: column;
  height: 100%;

  :deep(.arco-layout-sider-children) {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 56px;
  padding: 0 16px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-1);
  white-space: nowrap;
  overflow: hidden;
  border-bottom: 1px solid var(--color-border-2);

  .logo-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: 8px;
    background: linear-gradient(135deg, rgb(var(--primary-6)), rgb(var(--success-6)));
    color: #fff;
    flex-shrink: 0;
    font-size: 18px;
  }

  .logo-text {
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

.layout-menu {
  flex: 1;
  background-color: transparent;
  border-right: none;
  overflow-y: auto;
}

.sider-version {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 14px 14px;
  border-top: 1px solid var(--color-border-2);
  color: var(--color-text-3);
  font-size: 11px;
  line-height: 1.35;
  flex-shrink: 0;

  .sider-version-tag {
    font-weight: 600;
    color: var(--color-text-2);
    letter-spacing: 0.02em;
  }

  .sider-version-time {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.layout-body {
  background-color: var(--color-fill-1);
}

.layout-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: var(--color-bg-1);
  border-bottom: 1px solid var(--color-border-2);
  padding: 0 16px;
  height: 56px;

  .header-left,
  .header-right {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .header-breadcrumb {
    margin-left: 8px;
  }

  .header-action {
    color: var(--color-text-2);
    &:hover {
      color: rgb(var(--primary-6));
      background-color: var(--color-fill-2);
    }
  }

  .collapse-btn {
    color: var(--color-text-1);
  }
}

.layout-content {
  padding: 16px;
  min-height: 0;
}

// 全局搜索弹窗样式
.global-search {
  display: flex;
  flex-direction: column;

  .global-search-input {
    padding: 12px 16px;
    border-bottom: 1px solid var(--color-border-2);
  }

  .search-options {
    max-height: 360px;
    overflow-y: auto;
  }

  .search-option-item {
    cursor: pointer;
    padding: 10px 16px;

    &:hover {
      background-color: var(--color-fill-2);
    }
  }

  .search-tip {
    padding: 32px 16px;
    text-align: center;
    color: var(--color-text-3);
    font-size: 13px;
  }
}

// 路由切换动画
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

// 移动端适配
@media (max-width: 768px) {
  .layout-content {
    padding: 12px;
  }
}
</style>
