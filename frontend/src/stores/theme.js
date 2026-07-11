// 主题管理：跟随系统浅色/深色，支持手动覆盖并持久化
import { ref } from 'vue'

const STORAGE_KEY = 'workbuddy-theme'
const isDark = ref(false)
const mode = ref('system') // 'system' | 'light' | 'dark'
let initialized = false
let mediaQuery = null

function applyDark(val) {
  // Arco Design Vue 通过 body / html 的 arco-theme 属性切换暗黑模式
  const el = document.body
  const root = document.documentElement
  if (val) {
    el.setAttribute('arco-theme', 'dark')
    root.setAttribute('arco-theme', 'dark')
    root.style.colorScheme = 'dark'
    root.style.backgroundColor = '#17171a'
  } else {
    el.removeAttribute('arco-theme')
    root.removeAttribute('arco-theme')
    root.style.colorScheme = 'light'
    root.style.backgroundColor = '#fff'
  }
}

function systemPrefersDark() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function resolveDark(preferredMode) {
  if (preferredMode === 'dark') return true
  if (preferredMode === 'light') return false
  return systemPrefersDark()
}

function setTheme(preferredMode, persist = true) {
  mode.value = preferredMode
  const dark = resolveDark(preferredMode)
  isDark.value = dark
  applyDark(dark)
  if (persist) {
    localStorage.setItem(STORAGE_KEY, preferredMode)
  }
}

// 兼容旧 key（antigravity-theme）→ 新 key（workbuddy-theme）
function migrateKey() {
  const old = localStorage.getItem('antigravity-theme')
  if (old && !localStorage.getItem(STORAGE_KEY)) {
    localStorage.setItem(STORAGE_KEY, old)
    localStorage.removeItem('antigravity-theme')
  }
}

function onSystemThemeChange() {
  if (mode.value === 'system') {
    setTheme('system', false)
  }
}

export function useThemeStore() {
  function init() {
    if (initialized) return
    initialized = true
    migrateKey()

    const saved = localStorage.getItem(STORAGE_KEY)
    // 兼容旧值 dark/light；无记录或显式 system 则跟随系统
    const preferred =
      saved === 'dark' || saved === 'light' || saved === 'system' ? saved : 'system'
    setTheme(preferred, false)

    mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', onSystemThemeChange)
    } else {
      // Safari < 14
      mediaQuery.addListener(onSystemThemeChange)
    }
  }

  // 无参数：在 light ↔ dark 间切换（手动覆盖系统）
  // 带 boolean：强制设置 light/dark
  function toggle(val) {
    const next = typeof val === 'boolean' ? (val ? 'dark' : 'light') : (isDark.value ? 'light' : 'dark')
    setTheme(next, true)
  }

  /** 恢复跟随系统主题 */
  function useSystem() {
    setTheme('system', true)
  }

  return {
    isDark,
    mode,
    init,
    toggle,
    useSystem,
  }
}
