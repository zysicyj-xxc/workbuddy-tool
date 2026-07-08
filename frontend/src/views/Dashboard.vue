<script setup>
// 仪表盘页面 - 统计卡片 + 积分使用概览 + 使用统计
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { dashboardApi, accountsApi, proxyApi } from '../api'

const router = useRouter()
const loading = ref(false)
const dashboardData = ref(null)
const accounts = ref([])
// 使用统计
const statsLoading = ref(false)
const stats = ref(null)
const statsRange = ref('7')
const statsRangeOptions = [
  { label: '总计', value: 'total' },
  { label: '今日', value: 'today' },
  { label: '近7天', value: '7' },
  { label: '近30天', value: '30' },
]

// 是否显示数据导入提示（账号总数为0时显示）
const showImportTip = computed(() => {
  if (!dashboardData.value) return false
  return (dashboardData.value.accounts?.total || 0) === 0
})

// 跳转到设置页
function goToSettings() {
  router.push('/settings')
}

// 计算积分使用概览：剩余积分 / 总积分
const quotaSummary = computed(() => {
  let total = 0
  let remaining = 0
  accounts.value.forEach((a) => {
    total += a.quota?.credits_total || 0
    remaining += a.quota?.credits_remaining || 0
  })
  const percentage = total > 0 ? Math.round((remaining / total) * 100) : 0
  return { total, remaining, percentage }
})

// 账号状态分布
const accountStatusText = computed(() => {
  if (!dashboardData.value) return ''
  const a = dashboardData.value.accounts
  return `活跃 ${a.active} · 已耗尽 ${a.exhausted} · 异常 ${a.error}`
})

// 缓存命中率百分比
function cacheHitRatePercent(rate) {
  if (rate == null) return '0%'
  const num = Number(rate)
  if (isNaN(num)) return '0%'
  const percent = num <= 1 ? num * 100 : num
  return `${percent.toFixed(2)}%`
}

// 加载使用统计
async function loadStats() {
  statsLoading.value = true
  try {
    let days
    if (statsRange.value === 'today') days = 1
    else if (statsRange.value === '7') days = 7
    else if (statsRange.value === '30') days = 30
    stats.value = await proxyApi.getStats(days)
  } finally {
    statsLoading.value = false
  }
}

function handleStatsRangeChange() {
  loadStats()
}

// 加载仪表盘数据
async function loadData() {
  loading.value = true
  try {
    // 并行加载仪表盘统计、账号列表、使用统计
    const [data, accountList] = await Promise.all([
      dashboardApi.getDashboard(),
      accountsApi.list(),
    ])
    dashboardData.value = data
    accounts.value = accountList || []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadData()
  loadStats()
})
</script>

<template>
  <div v-loading="loading">
    <!-- 数据导入提示（账号总数为0时显示） -->
    <el-alert
      v-if="showImportTip"
      title="尚未导入账号数据"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom: 16px"
    >
      <template #default>
        <div style="display: flex; align-items: center; justify-content: space-between">
          <span>检测到账号总数为 0，建议先导入历史数据包（支持旧版 SQLite 数据包或加密数据包）后继续使用。</span>
          <el-button type="primary" size="small" @click="goToSettings">去导入</el-button>
        </div>
      </template>
    </el-alert>

    <!-- 统计卡片区域 -->
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic
            v-if="dashboardData"
            :title="`账号总数 / 活跃账号`"
            :value="dashboardData.accounts.total"
          >
            <template #suffix>
              <span style="font-size: 14px; color: #909399">
                / {{ dashboardData.accounts.active }}
              </span>
            </template>
          </el-statistic>
          <div class="stat-desc">{{ accountStatusText }}</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic
            v-if="dashboardData"
            title="今日已签到 / 总账号数"
            :value="dashboardData.checkin.checked_today"
          >
            <template #suffix>
              <span style="font-size: 14px; color: #909399">
                / {{ dashboardData.checkin.total }}
              </span>
            </template>
          </el-statistic>
          <div class="stat-desc">每日签到统计</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic
            v-if="dashboardData"
            title="上游Key数 / 活跃Key数"
            :value="dashboardData.proxy.upstream_keys"
          >
            <template #suffix>
              <span style="font-size: 14px; color: #909399">
                / {{ dashboardData.proxy.active_upstream }}
              </span>
            </template>
          </el-statistic>
          <div class="stat-desc">子Key数：{{ dashboardData?.proxy.sub_keys || 0 }}</div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic
            v-if="dashboardData"
            title="总请求数"
            :value="dashboardData.proxy.total_requests"
          />
          <div class="stat-desc">
            Prompt Tokens：{{ dashboardData?.proxy.total_prompt_tokens || 0 }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 积分使用概览 -->
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="24">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>积分使用概览</span>
              <el-button type="primary" link @click="loadData">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </template>

          <el-descriptions :column="3" border>
            <el-descriptions-item label="总积分">
              {{ quotaSummary.total }}
            </el-descriptions-item>
            <el-descriptions-item label="剩余积分">
              {{ quotaSummary.remaining }}
            </el-descriptions-item>
            <el-descriptions-item label="剩余比例">
              {{ quotaSummary.percentage }}%
            </el-descriptions-item>
          </el-descriptions>

          <div style="margin-top: 20px">
            <el-progress
              :percentage="quotaSummary.percentage"
              :color="quotaSummary.percentage > 50 ? '#67c23a' : quotaSummary.percentage > 20 ? '#e6a23c' : '#f56c6c'"
              :stroke-width="20"
              :text-inside="true"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 使用统计 -->
    <el-card shadow="hover" style="margin-top: 20px" v-loading="statsLoading">
      <template #header>
        <div class="card-header">
          <span>使用统计</span>
          <div style="display: flex; align-items: center; gap: 12px">
            <el-select v-model="statsRange" style="width: 120px" @change="handleStatsRangeChange">
              <el-option
                v-for="o in statsRangeOptions"
                :key="o.value"
                :label="o.label"
                :value="o.value"
              />
            </el-select>
            <el-button type="primary" link @click="loadStats">
              <el-icon><Refresh /></el-icon>刷新
            </el-button>
          </div>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="6">
          <el-card shadow="hover">
            <el-statistic v-if="stats" title="总请求数" :value="stats.total_requests || 0" />
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover">
            <el-statistic v-if="stats" title="Prompt Tokens" :value="stats.total_prompt_tokens || 0" />
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover">
            <el-statistic v-if="stats" title="Completion Tokens" :value="stats.total_completion_tokens || 0" />
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="hover">
            <el-statistic v-if="stats" title="消耗积分" :value="stats.total_credits || 0" :precision="2" />
          </el-card>
        </el-col>
      </el-row>
      <el-row :gutter="20" style="margin-top: 16px">
        <el-col :span="12">
          <el-card shadow="hover">
            <el-statistic v-if="stats" title="缓存命中Token" :value="stats.cached_tokens || 0" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="hover">
            <el-statistic
              v-if="stats"
              title="缓存命中率"
              :value="cacheHitRatePercent(stats.cache_hit_rate)"
            />
          </el-card>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<style scoped>
.stat-desc {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
