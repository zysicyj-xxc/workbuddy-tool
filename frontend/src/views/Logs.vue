<script setup>
// 调用日志页面 - 日志文件列表 + 内容预览 + 实时刷新
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconRefresh, IconFile } from '@arco-design/web-vue/es/icon'
import { proxyApi } from '../api'

const logFilesLoading = ref(false)
const logFiles = ref([])
const currentLogFile = ref('')
const logContent = ref('')
const logContentLoading = ref(false)
const logLines = computed(() => (logContent.value ? logContent.value.split('\n').length : 0))
const autoRefresh = ref(false)
let refreshTimer = null

// 表格行自定义类名（用于高亮当前选中行）
function rowClass(record) {
  return currentLogFile.value === (record.name || record.filename) ? 'arco-table-tr-active' : ''
}

function formatSize(bytes) {
  if (bytes == null) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function formatTime(ts) {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

async function loadLogFiles() {
  logFilesLoading.value = true
  try {
    const data = (await proxyApi.getLogFiles()) || []
    logFiles.value = data
    if (data.length && !currentLogFile.value) {
      currentLogFile.value = data[0].name || data[0].filename
      await loadLogFileContent(currentLogFile.value)
    }
  } finally {
    logFilesLoading.value = false
  }
}

async function loadLogFileContent(filename) {
  if (!filename) return
  logContentLoading.value = true
  try {
    const data = await proxyApi.getLogFile(filename)
    logContent.value = typeof data === 'string' ? data : (data?.content || data?.data || '')
  } catch (e) {
    logContent.value = ''
  } finally {
    logContentLoading.value = false
  }
}

async function selectLogFile(file) {
  currentLogFile.value = file.name || file.filename
  await loadLogFileContent(currentLogFile.value)
}

function handleAutoRefreshChange(val) {
  if (val) {
    refreshTimer = setInterval(() => {
      if (currentLogFile.value) loadLogFileContent(currentLogFile.value)
    }, 3000)
    Message.success('已开启实时刷新（每 3 秒）')
  } else {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
  }
}

onMounted(loadLogFiles)

onBeforeUnmount(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<template>
  <a-row :gutter="12">
    <!-- 左侧：日志文件列表 -->
    <a-col :xs="24" :md="8">
      <a-card :bordered="true">
        <template #title>
          <a-space>
            <IconFile />
            <span>日志文件</span>
          </a-space>
        </template>
        <template #extra>
          <a-button type="text" size="small" @click="loadLogFiles">
            <template #icon><IconRefresh /></template>
            刷新
          </a-button>
        </template>
        <a-table
          :data="logFiles"
          :loading="logFilesLoading"
          :pagination="false"
          stripe
          :scroll="{ y: 580 }"
          row-class="log-file-row"
          :row-class="rowClass"
          @row-click="selectLogFile"
        >
          <template #columns>
            <a-table-column title="文件名" :min-width="200">
              <template #cell="{ record }">
                <span
                  :class="{
                    'log-name-active': currentLogFile === (record.name || record.filename),
                  }"
                >
                  {{ record.name || record.filename }}
                </span>
              </template>
            </a-table-column>
            <a-table-column title="大小" :width="90">
              <template #cell="{ record }">{{ formatSize(record.size) }}</template>
            </a-table-column>
            <a-table-column title="修改时间" :min-width="160">
              <template #cell="{ record }">{{ formatTime(record.modified_time) }}</template>
            </a-table-column>
          </template>
        </a-table>
        <a-empty v-if="!logFilesLoading && !logFiles.length" description="暂无日志文件" />
      </a-card>
    </a-col>

    <!-- 右侧：日志内容预览 -->
    <a-col :xs="24" :md="16">
      <a-card :bordered="true">
        <template #title>
          <a-space>
            <span>{{ currentLogFile || '请选择日志文件' }}</span>
            <a-tag size="small" color="arcoblue">
              共 {{ logLines }} 行
            </a-tag>
          </a-space>
        </template>
        <template #extra>
          <a-space>
            <a-space size="small">
              <span class="text-secondary">实时刷新</span>
              <a-switch v-model="autoRefresh" @change="handleAutoRefreshChange" size="small" />
            </a-space>
            <a-button
              type="text"
              size="small"
              :disabled="!currentLogFile"
              @click="loadLogFileContent(currentLogFile)"
            >
              <template #icon><IconRefresh /></template>
              刷新
            </a-button>
          </a-space>
        </template>
        <a-spin :loading="logContentLoading" class="log-content-spin">
          <pre v-if="logContent" class="log-content">{{ logContent }}</pre>
          <a-empty v-else description="暂无日志内容" />
        </a-spin>
      </a-card>
    </a-col>
  </a-row>
</template>

<style lang="scss" scoped>
.text-secondary {
  color: var(--color-text-3);
  font-size: 13px;
}

.log-content-spin {
  display: block;
  width: 100%;
}

.log-content {
  margin: 0;
  max-height: 580px;
  overflow: auto;
  background-color: var(--color-fill-3);
  border-radius: 6px;
  padding: 12px 16px;
  font-family: 'JetBrains Mono', 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.7;
  color: var(--color-text-1);
  white-space: pre-wrap;
  word-break: break-all;
}

.log-name-active {
  color: rgb(var(--primary-6));
  font-weight: 600;
}

:deep(.log-file-row) {
  cursor: pointer;
}

@media (max-width: 768px) {
  .log-content {
    max-height: 400px;
    font-size: 12px;
  }
}
</style>
