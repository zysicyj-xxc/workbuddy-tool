<script setup>
// 账号管理页面 - 账号列表、添加、导入、删除、签到、积分详情
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { accountsApi, checkinApi, quotaApi } from '../api'

const loading = ref(false)
const accounts = ref([])

// 状态标签映射
const statusMap = {
  active: { text: '活跃', type: 'success' },
  quota_exhausted: { text: '积分耗尽', type: 'warning' },
  error: { text: '异常', type: 'danger' },
  disabled: { text: '已禁用', type: 'info' },
}

// 平台选项
const platformOptions = [
  { label: 'CodeBuddy', value: 'codebuddy' },
]

// ─── 添加账号对话框 ───
const addDialogVisible = ref(false)
const addForm = reactive({
  api_key: '',
  nickname: '',
  platform: 'codebuddy',
})
const addLoading = ref(false)

// ─── 批量导入对话框 ───
const importDialogVisible = ref(false)
const importForm = reactive({
  keys: '',
  platform: 'codebuddy',
})
const importLoading = ref(false)

// ─── 积分详情对话框 ───
const quotaDialogVisible = ref(false)
const quotaLoading = ref(false)
const quotaData = ref(null)
const currentAccount = ref(null)

// 计算积分百分比
function quotaPercentage(row) {
  const total = row.quota?.credits_total || 0
  const remaining = row.quota?.credits_remaining || 0
  if (total <= 0) return 0
  return Math.round((remaining / total) * 100)
}

// 今日是否已签到
function isCheckedToday(row) {
  const last = row.checkin?.last_checkin_time
  if (!last) return false
  return new Date(last).toISOString().slice(0, 10) === new Date().toISOString().slice(0, 10)
}

// 加载账号列表
async function loadAccounts() {
  loading.value = true
  try {
    accounts.value = (await accountsApi.list()) || []
  } finally {
    loading.value = false
  }
}

// 打开添加对话框
function openAddDialog() {
  addForm.api_key = ''
  addForm.nickname = ''
  addForm.platform = 'codebuddy'
  addDialogVisible.value = true
}

// 提交添加账号
async function submitAdd() {
  if (!addForm.api_key.trim()) {
    ElMessage.warning('请输入 API Key')
    return
  }
  addLoading.value = true
  try {
    await accountsApi.add({
      api_key: addForm.api_key.trim(),
      nickname: addForm.nickname.trim(),
      platform: addForm.platform,
    })
    ElMessage.success('添加账号成功')
    addDialogVisible.value = false
    loadAccounts()
  } finally {
    addLoading.value = false
  }
}

// 打开导入对话框
function openImportDialog() {
  importForm.keys = ''
  importForm.platform = 'codebuddy'
  importDialogVisible.value = true
}

// 提交批量导入
async function submitImport() {
  if (!importForm.keys.trim()) {
    ElMessage.warning('请输入要导入的 API Key')
    return
  }
  importLoading.value = true
  try {
    const res = await accountsApi.import({
      keys: importForm.keys,
      platform: importForm.platform,
    })
    ElMessage.success(`导入完成：成功 ${res.success} 个，失败 ${res.failed} 个`)
    importDialogVisible.value = false
    loadAccounts()
  } finally {
    importLoading.value = false
  }
}

// 刷新所有积分
async function refreshAllQuota() {
  loading.value = true
  try {
    const res = await quotaApi.refresh()
    ElMessage.success(`刷新完成：成功 ${res.success} 个，失败 ${res.failed} 个`)
    loadAccounts()
  } finally {
    loading.value = false
  }
}

// 删除账号
async function removeAccount(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除账号「${row.nickname}」吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning' }
    )
    await accountsApi.remove(row.uid)
    ElMessage.success('删除成功')
    loadAccounts()
  } catch (e) {
    // 用户取消或删除失败
  }
}

// 单账号签到
async function checkinAccount(row) {
  try {
    await checkinApi.checkin(row.uid)
    ElMessage.success(`账号「${row.nickname}」签到成功`)
    loadAccounts()
  } catch (e) {
    // 错误已由拦截器提示
  }
}

// 查看积分详情
async function showQuota(row) {
  currentAccount.value = row
  quotaDialogVisible.value = true
  quotaLoading.value = true
  quotaData.value = null
  try {
    quotaData.value = await quotaApi.get(row.uid)
  } finally {
    quotaLoading.value = false
  }
}

onMounted(loadAccounts)
</script>

<template>
  <div v-loading="loading">
    <!-- 顶部操作栏 -->
    <el-card shadow="never" style="margin-bottom: 16px">
      <div class="toolbar">
        <div>
          <el-button type="primary" @click="openAddDialog">
            <el-icon><Plus /></el-icon>添加账号
          </el-button>
          <el-button type="success" @click="openImportDialog">
            <el-icon><Upload /></el-icon>批量导入
          </el-button>
          <el-button type="warning" @click="refreshAllQuota">
            <el-icon><Refresh /></el-icon>刷新积分
          </el-button>
        </div>
        <el-button @click="loadAccounts">
          <el-icon><Refresh /></el-icon>刷新列表
        </el-button>
      </div>
    </el-card>

    <!-- 账号表格 -->
    <el-card shadow="never">
      <el-table :data="accounts" stripe style="width: 100%">
        <el-table-column prop="nickname" label="昵称" min-width="120" />
        <el-table-column prop="platform" label="平台" width="120" />

        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusMap[row.status]?.type || 'info'">
              {{ statusMap[row.status]?.text || row.status }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="剩余/总积分" min-width="180">
          <template #default="{ row }">
            <div>
              <span style="font-size: 12px; color: #909399">
                {{ row.quota?.credits_remaining || 0 }} / {{ row.quota?.credits_total || 0 }}
              </span>
            </div>
            <el-progress
              :percentage="quotaPercentage(row)"
              :stroke-width="10"
              :show-text="false"
              :color="quotaPercentage(row) > 50 ? '#67c23a' : quotaPercentage(row) > 20 ? '#e6a23c' : '#f56c6c'"
            />
          </template>
        </el-table-column>

        <el-table-column label="签到状态" width="120">
          <template #default="{ row }">
            <el-tag :type="isCheckedToday(row) ? 'success' : 'info'" size="small">
              {{ isCheckedToday(row) ? '今日已签' : '今日未签' }}
            </el-tag>
            <div style="font-size: 12px; color: #909399; margin-top: 4px">
              连续 {{ row.checkin?.streak_days || 0 }} 天
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="showQuota(row)">详情</el-button>
            <el-button size="small" type="primary" @click="checkinAccount(row)">签到</el-button>
            <el-button size="small" type="danger" @click="removeAccount(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 添加账号对话框 -->
    <el-dialog v-model="addDialogVisible" title="添加账号" width="500px">
      <el-form :model="addForm" label-width="100px">
        <el-form-item label="API Key" required>
          <el-input
            v-model="addForm.api_key"
            placeholder="请输入以 ck_ 开头的 API Key"
            clearable
          />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input
            v-model="addForm.nickname"
            placeholder="可选，留空则自动生成"
            clearable
          />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="addForm.platform" style="width: 100%">
            <el-option
              v-for="opt in platformOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="submitAdd">确定</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入对话框 -->
    <el-dialog v-model="importDialogVisible" title="批量导入账号" width="600px">
      <el-form :model="importForm" label-width="80px">
        <el-form-item label="平台">
          <el-select v-model="importForm.platform" style="width: 100%">
            <el-option
              v-for="opt in platformOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="API Keys">
          <el-input
            v-model="importForm.keys"
            type="textarea"
            :rows="10"
            placeholder="每行一个 ck_xxx"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importLoading" @click="submitImport">导入</el-button>
      </template>
    </el-dialog>

    <!-- 积分详情对话框 -->
    <el-dialog
      v-model="quotaDialogVisible"
      :title="`积分详情 - ${currentAccount?.nickname || ''}`"
      width="800px"
    >
      <div v-loading="quotaLoading">
        <template v-if="quotaData">
          <el-descriptions :column="2" border style="margin-bottom: 16px">
            <el-descriptions-item label="总积分">
              {{ quotaData.total_credits }}
            </el-descriptions-item>
            <el-descriptions-item label="剩余积分">
              {{ quotaData.remaining_credits }}
            </el-descriptions-item>
          </el-descriptions>

          <div style="margin-bottom: 8px; font-weight: 600">资源包列表</div>
          <el-table :data="quotaData.packages" stripe border>
            <el-table-column prop="package_name" label="资源包名称" min-width="140" />
            <el-table-column prop="type_label" label="类型" width="100" />
            <el-table-column label="容量（剩余/总）" width="140">
              <template #default="{ row }">
                {{ row.capacity_remain }} / {{ row.capacity_size }}
              </template>
            </el-table-column>
            <el-table-column label="使用进度" min-width="180">
              <template #default="{ row }">
                <el-progress
                  :percentage="row.usage_percentage"
                  :stroke-width="10"
                  :color="row.remain_percentage > 50 ? '#67c23a' : row.remain_percentage > 20 ? '#e6a23c' : '#f56c6c'"
                />
              </template>
            </el-table-column>
            <el-table-column label="周期剩余" width="100">
              <template #default="{ row }">
                {{ row.cycle_remain }} / {{ row.cycle_size }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.is_exhausted ? 'danger' : 'success'" size="small">
                  {{ row.is_exhausted ? '已耗尽' : '可用' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
