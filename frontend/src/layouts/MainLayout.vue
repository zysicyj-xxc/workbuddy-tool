<script setup>
// 主布局组件 - 左侧菜单 + 顶部标题栏 + 右侧主内容区 + 左下角外观切换
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

// 菜单项配置（新增日志、设置改名数据管理）
const menuItems = [
  { index: '/', title: '仪表盘', icon: 'Odometer' },
  { index: '/accounts', title: '账号管理', icon: 'User' },
  { index: '/checkin', title: '每日签到', icon: 'Calendar' },
  { index: '/proxy', title: 'API代理', icon: 'Connection' },
  { index: '/packages', title: '资源包管理', icon: 'Box' },
  { index: '/logs', title: '日志', icon: 'Document' },
  { index: '/settings', title: '数据管理', icon: 'FolderOpened' },
]

// 主题切换（明暗模式）- 持久化到 localStorage
const isDark = ref(false)

function applyDark(val) {
  document.documentElement.classList.toggle('dark', val)
  // 同步 Element Plus 组件样式
  document.body.style.backgroundColor = val ? '#141414' : ''
}

function toggleDark(val) {
  isDark.value = val
  applyDark(val)
  localStorage.setItem('antigravity-theme', val ? 'dark' : 'light')
}

onMounted(() => {
  // 读取持久化主题
  const saved = localStorage.getItem('antigravity-theme')
  if (saved === 'dark') {
    isDark.value = true
    applyDark(true)
  }
})
</script>

<template>
  <el-container class="layout-container">
    <!-- 左侧菜单栏 -->
    <el-aside width="220px" class="layout-aside">
      <div class="logo">
        <el-icon size="24"><Cpu /></el-icon>
        <span class="logo-text">Antigravity Tools</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        class="layout-menu"
      >
        <el-menu-item
          v-for="item in menuItems"
          :key="item.index"
          :index="item.index"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>

      <!-- 左下角外观切换 -->
      <div class="aside-footer">
        <div class="theme-switch">
          <el-icon size="16"><Sunny /></el-icon>
          <el-switch
            v-model="isDark"
            size="small"
            @change="toggleDark"
            class="theme-switch-control"
          />
          <el-icon size="16"><Moon /></el-icon>
        </div>
      </div>
    </el-aside>

    <el-container>
      <!-- 顶部标题栏 -->
      <el-header class="layout-header">
        <span class="header-title">{{ route.meta.title || 'Antigravity Tools Web' }}</span>
      </el-header>

      <!-- 右侧主内容区 -->
      <el-main class="layout-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout-container {
  height: 100%;
}

.layout-aside {
  background-color: #304156;
  display: flex;
  flex-direction: column;
}

.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 60px;
  padding: 0 20px;
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
}

.logo-text {
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 菜单样式覆盖，适配深色背景 */
.layout-menu {
  border-right: none;
  background-color: #304156;
  flex: 1;
}

.layout-menu .el-menu-item {
  color: #bfcbd9;
}

.layout-menu .el-menu-item:hover {
  background-color: #263445;
  color: #fff;
}

.layout-menu .el-menu-item.is-active {
  background-color: #1f2d3d;
  color: #409eff;
}

/* 左下角外观切换 */
.aside-footer {
  padding: 12px 20px;
  border-top: 1px solid #263445;
  background-color: #2b3648;
}

.theme-switch {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #bfcbd9;
}

.theme-switch :deep(.el-switch) {
  --el-switch-on-color: #409eff;
}

.layout-header {
  display: flex;
  align-items: center;
  background-color: #fff;
  border-bottom: 1px solid #e6e6e6;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.layout-main {
  background-color: #f0f2f5;
  padding: 20px;
}

/* 深色模式适配 */
:global(.dark) .layout-header {
  background-color: #1d1e1f;
  border-bottom-color: #303030;
}
:global(.dark) .header-title {
  color: #e5eaf3;
}
:global(.dark) .layout-main {
  background-color: #141414;
}
</style>
