<script setup>
// 数据管理页面 - 导入导出数据包
import { ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import {
  IconDownload,
  IconUpload,
  IconStorage,
} from '@arco-design/web-vue/es/icon'
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
    Message.success('数据包导出成功')
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
    Message.success('数据包导入成功')
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
    Message.success('加密数据包导入成功')
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
  <a-card :bordered="true" :loading="importing" class="settings-card">
    <template #title>
      <a-space>
        <IconStorage />
        <span>数据管理</span>
      </a-space>
    </template>

    <a-form :model="{}" layout="vertical" class="settings-form">
      <a-form-item label="导出数据包">
        <a-space align="center">
          <a-button type="primary" :loading="exporting" @click="handleExport">
            <template #icon><IconDownload /></template>
            导出加密数据包
          </a-button>
          <span class="text-secondary">导出当前所有数据为加密数据包（.enc）</span>
        </a-space>
      </a-form-item>

      <a-form-item label="导入旧版数据">
        <a-upload
          :custom-request="handleImportLegacy"
          :show-file-list="false"
          accept=".db"
          :disabled="importing"
        >
          <template #upload-button>
            <a-button type="outline" status="warning" :disabled="importing">
              <template #icon><IconUpload /></template>
              导入 SQLite 数据包
            </a-button>
          </template>
        </a-upload>
        <div class="text-secondary">仅支持 .db 格式的旧版 SQLite 数据包</div>
      </a-form-item>

      <a-form-item label="导入加密数据">
        <a-upload
          :custom-request="handleImportEncrypted"
          :show-file-list="false"
          accept=".enc"
          :disabled="importing"
        >
          <template #upload-button>
            <a-button type="outline" status="success" :disabled="importing">
              <template #icon><IconUpload /></template>
              导入加密数据包
            </a-button>
          </template>
        </a-upload>
        <div class="text-secondary">支持 .enc 格式的加密数据包</div>
      </a-form-item>
    </a-form>

    <!-- 导入结果 -->
    <a-alert
      v-if="importResult"
      :type="importResult.success === false ? 'warning' : 'success'"
      banner
      closable
      style="margin-top: 12px"
    >
      <template #title>
        导入{{ importResult.success !== false ? '成功' : '完成（存在失败项）' }}
      </template>
      <div class="import-result">
        成功：<strong>{{ importResult.imported ?? importResult.success_count ?? 0 }}</strong>
        <span class="divider">|</span>
        失败：<strong>{{ importResult.failed ?? importResult.failed_count ?? 0 }}</strong>
        <span v-if="importResult.message" class="result-message">
          {{ importResult.message }}
        </span>
      </div>
    </a-alert>
  </a-card>
</template>

<style lang="scss" scoped>
.settings-card {
  max-width: 800px;
}

.settings-form {
  max-width: 700px;
}

.text-secondary {
  color: var(--color-text-3);
  font-size: 12px;
  margin-top: 4px;
}

.import-result {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;

  .divider {
    color: var(--color-text-4);
  }

  .result-message {
    color: var(--color-text-2);
  }
}
</style>
