// 主题管理 composable - 明暗模式切换，持久化到 localStorage
import { ref } from 'vue'

const isDark = ref(false)
let initialized = false

function applyDark(val) {
  // Arco Design Vue 通过 body 的 arco-theme 属性切换暗黑模式
  if (val) {
    document.body.setAttribute('arco-theme', 'dark')
  } else {
    document.body.removeAttribute('arco-theme')
  }
}

// 兼容旧 key（antigravity-theme）→ 新 key（workbuddy-theme）
function migrateKey() {
  const old = localStorage.getItem('antigravity-theme')
  if (old && !localStorage.getItem('workbuddy-theme')) {
    localStorage.setItem('workbuddy-theme', old)
    localStorage.removeItem('antigravity-theme')
  }
}

export function useThemeStore() {
  function init() {
    if (initialized) return
    initialized = true
    migrateKey()
    const saved = localStorage.getItem('workbuddy-theme')
    if (saved === 'dark') {
      isDark.value = true
      applyDark(true)
    }
  }

  // 无参数：切换当前主题；带参数：强制设置
  function toggle(val) {
    const next = typeof val === 'boolean' ? val : !isDark.value
    isDark.value = next
    applyDark(next)
    localStorage.setItem('workbuddy-theme', next ? 'dark' : 'light')
  }

  return {
    isDark,
    init,
    toggle,
  }
}
