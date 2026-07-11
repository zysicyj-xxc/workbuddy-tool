<script setup>
// 数据管理：从 MySQL 导出 / 导入 / 清空
import { ref } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import {
  IconDownload,
  IconUpload,
  IconStorage,
  IconDelete,
} from '@arco-design/web-vue/es/icon'
import { dataApi } from '../api'

const exporting = ref(false)
const importing = ref(false)
const clearing = ref(false)
const importResult = ref(null)
const packagePassword = ref('')
const replaceOnImport = ref(true)

/** Arco Upload custom-request：文件在 option.fileItem.file */
function pickUploadFile(option) {
  return option?.fileItem?.file || option?.file || null
}

async function handleExport() {
  exporting.value = true
  try {
    const blob = await dataApi.export(packagePassword.value)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const now = new Date()
    const dateStr = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`
    link.download = `workbuddy-data-${dateStr}.enc`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    Message.success('数据包导出成功（已从 MySQL 导出）')
  } catch (e) {
    Message.error(e?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

async function handleImportLegacy(option) {
  const file = pickUploadFile(option)
  if (!file) {
    Message.error('未选择文件')
    option?.onError?.(new Error('no file'))
    return
  }
  importing.value = true
  importResult.value = null
  Message.loading({ id: 'import-pkg', content: '正在导入 SQLite…', duration: 0 })
  try {
    const res = await dataApi.import(file, { replace: replaceOnImport.value })
    importResult.value = res || { success: true, message: '导入完成' }
    if (res && res.success === false) {
      Message.warning({ id: 'import-pkg', content: res.message || '导入失败' })
      option?.onError?.(new Error(res.message || 'import failed'))
    } else {
      Message.success({ id: 'import-pkg', content: res?.message || 'SQLite 已导入 MySQL' })
      option?.onSuccess?.(res)
      setTimeout(() => window.location.reload(), 1200)
    }
  } catch (e) {
    Message.error({ id: 'import-pkg', content: e?.message || '导入失败' })
    option?.onError?.(e)
  } finally {
    importing.value = false
  }
}

async function handleImportEncrypted(option) {
  const file = pickUploadFile(option)
  if (!file) {
    Message.error('未选择文件')
    option?.onError?.(new Error('no file'))
    return
  }
  importing.value = true
  importResult.value = null
  Message.loading({ id: 'import-pkg', content: `正在导入 ${file.name}…`, duration: 0 })
  try {
    const res = await dataApi.importEncrypted(file, {
      password: packagePassword.value,
      replace: replaceOnImport.value,
    })
    importResult.value = res || { success: true, message: '导入完成' }
    if (res && res.success === false) {
      Message.warning({ id: 'import-pkg', content: res.message || '导入失败' })
      option?.onError?.(new Error(res.message || 'import failed'))
    } else {
      Message.success({
        id: 'import-pkg',
        content: res?.message || '加密数据包已导入 MySQL',
      })
      option?.onSuccess?.(res)
      setTimeout(() => window.location.reload(), 1200)
    }
  } catch (e) {
    Message.error({ id: 'import-pkg', content: e?.message || '导入失败' })
    option?.onError?.(e)
  } finally {
    importing.value = false
  }
}

function handleClearClick() {
  Modal.warning({
    title: '确认清空全部数据？',
    content:
      '将删除 MySQL 中全部账号与设置，并清空代理上游 Key / 子 Key。此操作不可恢复，建议先导出备份。',
    okText: '确认清空',
    cancelText: '取消',
    okButtonProps: { status: 'danger' },
    hideCancel: false,
    onOk: async () => {
      clearing.value = true
      try {
        const res = await dataApi.clear()
        if (res && res.success === false) {
          Message.warning(res.message || '清空失败')
          return
        }
        Message.success(res?.message || '已清空全部数据')
        setTimeout(() => window.location.reload(), 1000)
      } catch (e) {
        Message.error(e?.message || '清空失败')
      } finally {
        clearing.value = false
      }
    },
  })
}
</script>

<template>
  <a-card :bordered="true" :loading="importing || clearing" class="settings-card">
    <template #title>
      <a-space>
        <IconStorage />
        <span>数据管理</span>
      </a-space>
    </template>

    <a-alert type="info" style="margin-bottom: 16px">
      账号/设置存 MySQL。推荐导入跨环境口令包（WBDP）。
      旧版 <code>~/.antigravity-tools/data.enc</code> 需先运行
      <code>python scripts/migrate_legacy_data.py --import-http --replace</code> 转换导入。
      也可直接导入同目录下的 <code>antigravity.db</code>（SQLite）。
    </a-alert>

    <a-form :model="{}" layout="vertical" class="settings-form">
      <a-form-item label="数据包口令（导出/导入共用）">
        <a-input-password
          v-model="packagePassword"
          allow-clear
          placeholder="留空则用环境变量或默认开发口令"
          style="max-width: 360px"
        />
      </a-form-item>

      <a-form-item label="导入选项">
        <a-checkbox v-model="replaceOnImport">
          替换模式（先清空 accounts/settings 再导入）
        </a-checkbox>
      </a-form-item>

      <a-form-item label="导出数据包">
        <a-space align="center">
          <a-button type="primary" :loading="exporting" @click="handleExport">
            <template #icon><IconDownload /></template>
            从 MySQL 导出
          </a-button>
          <span class="text-secondary">导出为 .enc 口令包，可带到新环境空库导入</span>
        </a-space>
      </a-form-item>

      <a-form-item label="导入加密数据">
        <a-upload
          :custom-request="handleImportEncrypted"
          :show-file-list="false"
          accept=".enc"
          :disabled="importing || clearing"
        >
          <template #upload-button>
            <a-button type="outline" status="success" :loading="importing">
              <template #icon><IconUpload /></template>
              导入加密数据包 → MySQL
            </a-button>
          </template>
        </a-upload>
        <div class="text-secondary">选 WBDP 口令包；旧版 data.enc 请先用迁移脚本</div>
      </a-form-item>

      <a-form-item label="导入旧版 SQLite">
        <a-upload
          :custom-request="handleImportLegacy"
          :show-file-list="false"
          accept=".db"
          :disabled="importing || clearing"
        >
          <template #upload-button>
            <a-button type="outline" status="warning" :loading="importing">
              <template #icon><IconUpload /></template>
              导入 SQLite .db → MySQL
            </a-button>
          </template>
        </a-upload>
        <div class="text-secondary">
          可直接选 <code>C:\Users\zysic\.antigravity-tools\antigravity.db</code>
        </div>
      </a-form-item>

      <a-form-item label="危险操作">
        <a-space align="center">
          <a-button status="danger" :loading="clearing" @click="handleClearClick">
            <template #icon><IconDelete /></template>
            清空全部数据
          </a-button>
          <span class="text-secondary">删除账号、设置与代理 Key，不可恢复</span>
        </a-space>
      </a-form-item>
    </a-form>

    <a-alert
      v-if="importResult"
      :type="importResult.success === false ? 'warning' : 'success'"
      banner
      closable
      style="margin-top: 12px"
    >
      <template #title>
        导入{{ importResult.success !== false ? '成功' : '失败' }}
      </template>
      <div class="import-result">
        成功：<strong>{{ importResult.accounts_success ?? importResult.imported ?? importResult.success_count ?? 0 }}</strong>
        <span class="divider">|</span>
        失败：<strong>{{ importResult.accounts_failed ?? importResult.failed ?? importResult.failed_count ?? 0 }}</strong>
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
