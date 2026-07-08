<script setup>
// 根组件 - 提供 Arco Config（中文 + 主题）
import { computed, onMounted, ref } from 'vue'
import MainLayout from './layouts/MainLayout.vue'
import { useThemeStore } from './stores/theme'
import zhCN from '@arco-design/web-vue/es/locale/lang/zh-cn'

const theme = useThemeStore()
const locale = zhCN

onMounted(() => {
  theme.init()
})
</script>

<template>
  <a-config-provider :locale="locale">
    <MainLayout />
  </a-config-provider>
</template>
