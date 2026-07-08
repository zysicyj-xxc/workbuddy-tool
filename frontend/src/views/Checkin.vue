<script setup>
// 每日签到页面 - 批量签到、单账号签到、签到结果展示
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { accountsApi, checkinApi } from '../api'

const loading = ref(false)
const accounts = ref([])
// 批量签到结果
const batchResult = ref(null)

// 判断今日是否已签到
function isCheckedToday(row) {
  const last = row.checkin?.last_checkin_time
  if (!last) return false
  return new Date(last).toISOString().slice(0, 10) === new Date().toISOString().slice(0, 10)
}

// 格式化签到时间
function formatTime(row) {
  const last = row.checkin?.last_checkin_time
  if (!last) return '从未签到'
  return new Date(last).toLocaleString('zh-CN')
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

// 批量签到
async function checkinAll() {
  try {
    await ElMessageBox.confirm('确定要对所有账号执行批量签到吗？', '批量签到', {
      type: 'info',
    })
  } catch (e) {
    return // 用户取消
  }

  loading.value = true
  try {
    const res = await checkinApi.checkinAll()
    batchResult.value = res
    ElMessage.success(`批量签到完成：成功 ${res.success}，失败 ${res.failed}，已签 ${res.already || 0}`)
    loadAccounts()
  } finally {
    loading.value = false
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

onMounted(loadAccounts)
</script>

<template>
  <div v-loading="loading">
    <!-- 顶部操作栏 -->
    <el-card shadow="never" style="margin-bottom: 16px">
      <div class="toolbar">
        <el-button type="primary" @click="checkinAll">
          <el-icon><Check /></el-icon>批量签到
        </el-button>
        <el-button @click="loadAccounts">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </el-card>

    <!-- 批量签到结果展示 -->
    <el-card v-if="batchResult" shadow="never" style="margin-bottom: 16px">
      <template #header>
        <span>批量签到结果</span>
      </template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="成功">
          <el-tag type="success">{{ batchResult.success }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="失败">
          <el-tag type="danger">{{ batchResult.failed }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="已签到">
          <el-tag type="info">{{ batchResult.already || 0 }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <el-table
        v-if="batchResult.details && batchResult.details.length"
        :data="batchResult.details"
        stripe
        style="margin-top: 12px"
      >
        <el-table-column prop="nickname" label="账号" min-width="120" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="详情" min-width="200">
          <template #default="{ row }">
            <span v-if="row.status === 'success'">
              剩余 {{ row.remaining }} / 总 {{ row.total }}
            </span>
            <span v-else style="color: #f56c6c">{{ row.error }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 账号列表 -->
    <el-card shadow="never">
      <template #header>
        <span>账号签到列表</span>
      </template>
      <el-table :data="accounts" stripe style="width: 100%">
        <el-table-column prop="nickname" label="昵称" min-width="140" />
        <el-table-column prop="platform" label="平台" width="120" />
        <el-table-column label="连续签到天数" width="130" align="center">
          <template #default="{ row }">
            <span>{{ row.checkin?.streak_days || 0 }} 天</span>
          </template>
        </el-table-column>
        <el-table-column label="今日签到" width="120" align="center">
          <template #default="{ row }">
            <el-tag :type="isCheckedToday(row) ? 'success' : 'info'" size="small">
              {{ isCheckedToday(row) ? '已签到' : '未签到' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="签到积分" width="120" align="center">
          <template #default="{ row }">
            {{ row.checkin?.daily_credit || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="累计积分" width="120" align="center">
          <template #default="{ row }">
            {{ row.checkin?.total_credits || 0 }}
          </template>
        </el-table-column>
        <el-table-column label="上次签到时间" min-width="180">
          <template #default="{ row }">
            {{ formatTime(row) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              :disabled="isCheckedToday(row)"
              @click="checkinAccount(row)"
            >
              签到
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
