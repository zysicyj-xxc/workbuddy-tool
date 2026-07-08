<script setup>
// 根组件 - 使用 el-config-provider 设置中文
import MainLayout from './layouts/MainLayout.vue'
</script>

<template>
  <!-- 全局配置：中文语言 -->
  <el-config-provider>
    <MainLayout />
  </el-config-provider>
</template>

<style>
/* 全局基础样式：去除默认 margin，占满高度 */
html,
body,
#app {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', Arial, sans-serif;
}
</style>
