<script setup>
// 调用日志页面 - 日志文件列表 + 内容预览 + 实时刷新
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { proxyApi } from '../api'

const logFilesLoading = ref(false)
const logFiles = ref([])
const currentLogFile = ref('')
const logContent = ref('')
const logContentLoading = ref(false)
const logLines = computed(() => (logContent.value ? logContent.value.split('\n').length : 0))
// 实时刷新开关
const autoRefresh = ref(false)
let refreshTimer = null

// 格式化文件大小
function formatSize(bytes) {
  if (bytes == null) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

// 格式化修改时间
function formatTime(ts) {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// 加载日志文件列表
async function loadLogFiles() {
  logFilesLoading.value = true
  try {
    const data = (await proxyApi.getLogFiles()) || []
    logFiles.value = data
    // 默认选中最新文件
    if (data.length && !currentLogFile.value) {
      currentLogFile.value = data[0].name || data[0].filename
      await loadLogFileContent(currentLogFile.value)
    }
  } finally {
    logFilesLoading.value = false
  }
}

// 加载日志文件内容
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

// 选中日志文件
async function selectLogFile(file) {
  currentLogFile.value = file.name || file.filename
  await loadLogFileContent(currentLogFile.value)
}

// 切换自动刷新
function handleAutoRefreshChange(val) {
  if (val) {
    refreshTimer = setInterval(() => {
      if (currentLogFile.value) loadLogFileContent(currentLogFile.value)
    }, 3000)
    ElMessage.success('已开启实时刷新（每 3 秒）')
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
  <el-row :gutter="16">
    <!-- 左侧：日志文件列表 -->
    <el-col :span="8">
      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span>日志文件</span>
            <el-button type="primary" link @click="loadLogFiles">
              <el-icon><Refresh /></el-icon>刷新
            </el-button>
          </div>
        </template>
        <el-table
          v-loading="logFilesLoading"
          :data="logFiles"
          stripe
          border
          highlight-current-row
          @row-click="selectLogFile"
          style="cursor: pointer"
          max-height="650"
        >
          <el-table-column label="文件名" min-width="200">
            <template #default="{ row }">
              <span
                :style="{
                  color: currentLogFile === (row.name || row.filename) ? '#409eff' : '',
                  fontWeight: currentLogFile === (row.name || row.filename) ? '600' : 'normal',
                }"
              >
                {{ row.name || row.filename }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="大小" width="90">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column label="修改时间" min-width="160">
            <template #default="{ row }">{{ formatTime(row.modified_time) }}</template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!logFilesLoading && !logFiles.length" description="暂无日志文件" />
      </el-card>
    </el-col>

    <!-- 右侧：日志内容预览 -->
    <el-col :span="16">
      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <span>
              {{ currentLogFile || '请选择日志文件' }}
              <span style="color: #909399; font-size: 12px; margin-left: 8px">
                共 {{ logLines }} 行
              </span>
            </span>
            <div style="display: flex; align-items: center; gap: 12px">
              <span style="font-size: 13px; color: #606266">实时刷新</span>
              <el-switch v-model="autoRefresh" @change="handleAutoRefreshChange" />
              <el-button
                type="primary"
                link
                :disabled="!currentLogFile"
                @click="loadLogFileContent(currentLogFile)"
              >
                <el-icon><Refresh /></el-icon>刷新
              </el-button>
            </div>
          </div>
        </template>
        <div v-loading="logContentLoading" class="log-content-wrapper">
          <pre v-if="logContent" class="log-content">{{ logContent }}</pre>
          <el-empty v-else description="暂无日志内容" />
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.log-content-wrapper {
  max-height: 650px;
  overflow: auto;
  background-color: #1e1e1e;
  border-radius: 4px;
  padding: 12px;
}

.log-content {
  margin: 0;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #d4d4d4;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
