<script setup>
// 数据管理页面 - 导入导出数据包
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dataApi } from '../api'

const exporting = ref(false)
const importing = ref(false)
const importResult = ref(null)

// 导出数据包
async function handleExport() {
  exporting.value = true
  try {
    const blob = await dataApi.export()
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const now = new Date()
    const dateStr = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`
    link.download = `antigravity-data-${dateStr}.enc`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('数据包导出成功')
  } catch (e) {
    // 错误已由拦截器提示
  } finally {
    exporting.value = false
  }
}

// 导入旧版 SQLite 数据包
async function handleImportLegacy(option) {
  const file = option.file
  if (!file) return
  importing.value = true
  importResult.value = null
  try {
    const res = await dataApi.import(file)
    importResult.value = res || { success: true, message: '导入完成' }
    ElMessage.success('数据包导入成功')
    setTimeout(() => {
      window.location.reload()
    }, 1500)
  } catch (e) {
    // 错误已由拦截器提示
  } finally {
    importing.value = false
  }
}

// 导入加密数据包
async function handleImportEncrypted(option) {
  const file = option.file
  if (!file) return
  importing.value = true
  importResult.value = null
  try {
    const res = await dataApi.importEncrypted(file)
    importResult.value = res || { success: true, message: '导入完成' }
    ElMessage.success('加密数据包导入成功')
    setTimeout(() => {
      window.location.reload()
    }, 1500)
  } catch (e) {
    // 错误已由拦截器提示
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <el-card shadow="never" v-loading="importing">
    <template #header>
      <span>数据管理</span>
    </template>
    <el-form label-width="140px">
      <el-form-item label="导出数据包">
        <el-button type="primary" :loading="exporting" @click="handleExport">
          <el-icon><Download /></el-icon>导出加密数据包
        </el-button>
        <span style="margin-left: 8px; color: #909399; font-size: 12px">
          导出当前所有数据为加密数据包（.enc）
        </span>
      </el-form-item>
      <el-form-item label="导入旧版数据">
        <el-upload
          :http-request="handleImportLegacy"
          :show-file-list="false"
          accept=".db"
          :disabled="importing"
        >
          <el-button type="warning" :disabled="importing">
            <el-icon><Upload /></el-icon>导入 SQLite 数据包
          </el-button>
          <template #tip>
            <div style="color: #909399; font-size: 12px">仅支持 .db 格式的旧版 SQLite 数据包</div>
          </template>
        </el-upload>
      </el-form-item>
      <el-form-item label="导入加密数据">
        <el-upload
          :http-request="handleImportEncrypted"
          :show-file-list="false"
          accept=".enc"
          :disabled="importing"
        >
          <el-button type="success" :disabled="importing">
            <el-icon><Upload /></el-icon>导入加密数据包
          </el-button>
          <template #tip>
            <div style="color: #909399; font-size: 12px">支持 .enc 格式的加密数据包</div>
          </template>
        </el-upload>
      </el-form-item>
    </el-form>

    <!-- 导入结果 -->
    <el-alert
      v-if="importResult"
      :title="`导入${importResult.success !== false ? '成功' : '完成（存在失败项）'}`"
      :type="importResult.success === false ? 'warning' : 'success'"
      show-icon
      :closable="false"
      style="margin-top: 12px"
    >
      <template #default>
        <div>
          成功：<strong>{{ importResult.imported ?? importResult.success_count ?? 0 }}</strong>
          <span style="margin: 0 8px">|</span>
          失败：<strong>{{ importResult.failed ?? importResult.failed_count ?? 0 }}</strong>
          <span v-if="importResult.message" style="margin-left: 12px; color: #606266">
            {{ importResult.message }}
          </span>
        </div>
      </template>
    </el-alert>
  </el-card>
</template>
