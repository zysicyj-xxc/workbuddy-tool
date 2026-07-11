<script setup>
// 仪表盘页面 - Arco Grid + 统计卡片 + ECharts 图表 + 数据导入提示
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import {
  IconRefresh,
  IconUser,
  IconCheckCircle,
  IconLink,
  IconThunderbolt,
} from '@arco-design/web-vue/es/icon'
import * as echarts from 'echarts'
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

// 是否显示数据导入提示
const showImportTip = computed(() => {
  if (!dashboardData.value) return false
  return (dashboardData.value.accounts?.total || 0) === 0
})

function goToSettings() {
  router.push('/settings')
}

// 计算积分使用概览
const quotaSummary = computed(() => {
  let total = 0
  let remaining = 0
  accounts.value.forEach((a) => {
    total += Math.round(Number(a.quota?.credits_total) || 0)
    remaining += Math.round(Number(a.quota?.credits_remaining) || 0)
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
  return `${Math.round(percent)}%`
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
    // 同时拉取按客户端维度的统计
    clientStats.value = await proxyApi.getStatsByClient(days)
  } finally {
    statsLoading.value = false
  }
}

// 客户端来源分析
const clientStats = ref([])
const clientChartRef = ref(null)
let clientChart = null

function renderClientChart() {
  if (!clientChartRef.value) return
  if (!clientChart) {
    clientChart = echarts.init(clientChartRef.value)
  }
  const data = clientStats.value || []
  if (!data.length) {
    clientChart.setOption({}, true)
    return
  }
  clientChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        const item = data.find((d) => d.client === p.name)
        if (!item) return p.name
        return `${p.name}<br/>请求数: ${item.requests}<br/>Token: ${item.total_tokens}`
      },
    },
    legend: { type: 'scroll', bottom: 0, textStyle: { color: '#888' } },
    series: [
      {
        name: '客户端分布',
        type: 'pie',
        radius: ['40%', '65%'],
        label: { show: true, formatter: '{b}: {c}' },
        data: data.map((d) => ({
          value: d.requests,
          name: d.client,
        })),
      },
    ],
  })
}

function handleStatsRangeChange() {
  loadStats()
}

// 加载仪表盘数据
async function loadData() {
  loading.value = true
  try {
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

// ─── ECharts 图表 ───
const quotaChartRef = ref(null)
const statusChartRef = ref(null)
let quotaChart = null
let statusChart = null

function renderQuotaChart() {
  if (!quotaChartRef.value) return
  if (!quotaChart) {
    quotaChart = echarts.init(quotaChartRef.value)
  }
  const used = quotaSummary.total - quotaSummary.remaining
  quotaChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { color: '#888' } },
    series: [
      {
        name: '积分使用',
        type: 'pie',
        radius: ['45%', '70%'],
        avoidLabelOverlap: false,
        label: {
          show: true,
          position: 'center',
          formatter: `{d}%\n剩余`,
          fontSize: 18,
          fontWeight: 'bold',
        },
        data: [
          { value: quotaSummary.remaining, name: '剩余', itemStyle: { color: '#00b42a' } },
          { value: used, name: '已用', itemStyle: { color: '#f53f3f' } },
        ],
      },
    ],
  })
}

function renderStatusChart() {
  if (!statusChartRef.value) return
  if (!statusChart) {
    statusChart = echarts.init(statusChartRef.value)
  }
  const d = dashboardData.value?.accounts
  if (!d) return
  statusChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { color: '#888' } },
    series: [
      {
        name: '账号状态',
        type: 'pie',
        radius: '65%',
        data: [
          { value: d.active, name: '活跃', itemStyle: { color: '#00b42a' } },
          { value: d.exhausted, name: '已耗尽', itemStyle: { color: '#ff7d00' } },
          { value: d.error, name: '异常', itemStyle: { color: '#f53f3f' } },
        ],
      },
    ],
  })
}

function resizeCharts() {
  quotaChart?.resize()
  statusChart?.resize()
  clientChart?.resize()
}

watch(
  () => [quotaSummary.value, dashboardData.value, clientStats.value],
  () => {
    nextTick(() => {
      renderQuotaChart()
      renderStatusChart()
      renderClientChart()
    })
  },
  { deep: true }
)

onMounted(() => {
  loadData()
  loadStats()
  window.addEventListener('resize', resizeCharts)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  quotaChart?.dispose()
  statusChart?.dispose()
  clientChart?.dispose()
})
</script>

<template>
  <a-spin :loading="loading" tip="加载中..." class="dashboard-spin">
    <div class="dashboard">
      <!-- 数据导入提示 -->
      <a-alert
        v-if="showImportTip"
        type="warning"
        banner
        closable
        :show-icon="true"
        title="尚未导入账号数据"
        style="margin-bottom: 16px"
      >
        检测到账号总数为 0，建议先导入历史数据包后继续使用。
        <a-button type="text" size="mini" @click="goToSettings">去导入</a-button>
      </a-alert>

      <!-- 统计卡片区域 -->
      <a-row :gutter="16" class="stat-row">
        <a-col :xs="24" :sm="12" :md="6">
          <a-card class="stat-card" hoverable>
            <div class="stat-card-body">
              <div class="stat-icon stat-icon-blue">
                <IconUser />
              </div>
              <div class="stat-content">
                <div class="stat-title">账号总数 / 活跃</div>
                <div class="stat-value">
                  {{ dashboardData?.accounts.total || 0 }}
                  <span class="stat-suffix">/ {{ dashboardData?.accounts.active || 0 }}</span>
                </div>
                <div class="stat-desc">{{ accountStatusText }}</div>
              </div>
            </div>
          </a-card>
        </a-col>

        <a-col :xs="24" :sm="12" :md="6">
          <a-card class="stat-card" hoverable>
            <div class="stat-card-body">
              <div class="stat-icon stat-icon-green">
                <IconCheckCircle />
              </div>
              <div class="stat-content">
                <div class="stat-title">今日签到 / 总账号</div>
                <div class="stat-value">
                  {{ dashboardData?.checkin.checked_today || 0 }}
                  <span class="stat-suffix">/ {{ dashboardData?.checkin.total || 0 }}</span>
                </div>
                <div class="stat-desc">每日签到统计</div>
              </div>
            </div>
          </a-card>
        </a-col>

        <a-col :xs="24" :sm="12" :md="6">
          <a-card class="stat-card" hoverable>
            <div class="stat-card-body">
              <div class="stat-icon stat-icon-orange">
                <IconLink />
              </div>
              <div class="stat-content">
                <div class="stat-title">上游Key / 活跃Key</div>
                <div class="stat-value">
                  {{ dashboardData?.proxy.upstream_keys || 0 }}
                  <span class="stat-suffix">/ {{ dashboardData?.proxy.active_upstream || 0 }}</span>
                </div>
                <div class="stat-desc">子Key数：{{ dashboardData?.proxy.sub_keys || 0 }}</div>
              </div>
            </div>
          </a-card>
        </a-col>

        <a-col :xs="24" :sm="12" :md="6">
          <a-card class="stat-card" hoverable>
            <div class="stat-card-body">
              <div class="stat-icon stat-icon-red">
                <IconThunderbolt />
              </div>
              <div class="stat-content">
                <div class="stat-title">总请求数</div>
                <div class="stat-value">{{ dashboardData?.proxy.total_requests || 0 }}</div>
                <div class="stat-desc">Prompt Tokens：{{ dashboardData?.proxy.total_prompt_tokens || 0 }}</div>
              </div>
            </div>
          </a-card>
        </a-col>
      </a-row>

      <!-- 图表区域 -->
      <a-row :gutter="16" style="margin-top: 16px">
        <a-col :xs="24" :md="12">
          <a-card title="积分使用概览" :bordered="true">
            <template #extra>
              <a-button type="text" size="small" @click="loadData">
                <template #icon><IconRefresh /></template>
                刷新
              </a-button>
            </template>
            <a-descriptions :column="3" layout="inline" :data="[
              { label: '总积分', value: quotaSummary.total },
              { label: '剩余积分', value: quotaSummary.remaining },
              { label: '剩余比例', value: `${quotaSummary.percentage}%` },
            ]" />
            <div ref="quotaChartRef" class="chart-container"></div>
          </a-card>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-card title="账号状态分布" :bordered="true">
            <template #extra>
              <a-button type="text" size="small" @click="loadData">
                <template #icon><IconRefresh /></template>
                刷新
              </a-button>
            </template>
            <div ref="statusChartRef" class="chart-container"></div>
          </a-card>
        </a-col>
      </a-row>

      <!-- 使用统计 -->
      <a-card title="使用统计" :bordered="true" style="margin-top: 16px" :loading="statsLoading">
        <template #extra>
          <a-space>
            <a-select
              v-model="statsRange"
              size="small"
              style="width: 120px"
              @change="handleStatsRangeChange"
            >
              <a-option v-for="o in statsRangeOptions" :key="o.value" :value="o.value">
                {{ o.label }}
              </a-option>
            </a-select>
            <a-button type="text" size="small" @click="loadStats">
              <template #icon><IconRefresh /></template>
              刷新
            </a-button>
          </a-space>
        </template>
        <a-row :gutter="12">
          <a-col :xs="12" :md="6">
            <a-statistic title="总请求数" :value="stats?.total_requests || 0" />
          </a-col>
          <a-col :xs="12" :md="6">
            <a-statistic title="Prompt Tokens" :value="stats?.total_prompt_tokens || 0" />
          </a-col>
          <a-col :xs="12" :md="6">
            <a-statistic title="Completion Tokens" :value="stats?.total_completion_tokens || 0" />
          </a-col>
          <a-col :xs="12" :md="6">
            <a-statistic title="消耗积分" :value="stats?.total_credits || 0" :precision="0" />
          </a-col>
        </a-row>
        <a-divider :margin="16" />
        <a-row :gutter="12">
          <a-col :span="12">
            <a-statistic title="缓存命中Token" :value="stats?.cached_tokens || 0" />
          </a-col>
          <a-col :span="12">
            <a-statistic
              title="缓存命中率"
              :value="cacheHitRatePercent(stats?.cache_hit_rate)"
            />
          </a-col>
        </a-row>
      </a-card>

      <!-- 客户端来源分析 -->
      <a-row :gutter="16" style="margin-top: 16px">
        <a-col :xs="24" :md="12">
          <a-card title="客户端来源分析" :bordered="true" :loading="statsLoading">
            <template #extra>
              <span class="text-secondary">
                共 {{ clientStats.length }} 个客户端
              </span>
            </template>
            <div ref="clientChartRef" class="chart-container"></div>
          </a-card>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-card title="客户端明细" :bordered="true" :loading="statsLoading">
            <a-table
              :data="clientStats"
              :pagination="false"
              stripe
              size="small"
              :scroll="{ y: 280 }"
            >
              <template #columns>
                <a-table-column title="客户端" data-index="client" :min-width="120" />
                <a-table-column title="请求数" data-index="requests" :width="100" align="right" />
                <a-table-column title="Prompt Tokens" :width="140" align="right">
                  <template #cell="{ record }">{{ record.prompt_tokens }}</template>
                </a-table-column>
                <a-table-column title="Total Tokens" :width="130" align="right">
                  <template #cell="{ record }">{{ record.total_tokens }}</template>
                </a-table-column>
              </template>
              <template #empty>
                <a-empty description="暂无客户端来源数据" />
              </template>
            </a-table>
          </a-card>
        </a-col>
      </a-row>
    </div>
  </a-spin>
</template>

<style lang="scss" scoped>
.dashboard-spin {
  width: 100%;
}

.text-secondary {
  color: var(--color-text-3);
  font-size: 12px;
}

.stat-row {
  margin-bottom: 0;
}

.stat-card {
  border-radius: 8px;
  transition: all 0.2s ease;
  margin-bottom: 12px;

  :deep(.arco-card-body) {
    padding: 16px;
  }

  .stat-card-body {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .stat-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 48px;
    height: 48px;
    border-radius: 12px;
    color: #fff;
    font-size: 24px;
    flex-shrink: 0;

    &-blue {
      background: linear-gradient(135deg, #165dff, #4080ff);
    }
    &-green {
      background: linear-gradient(135deg, #00b42a, #23c343);
    }
    &-orange {
      background: linear-gradient(135deg, #ff7d00, #f7ba1e);
    }
    &-red {
      background: linear-gradient(135deg, #f53f3f, #cb2634);
    }
  }

  .stat-content {
    flex: 1;
    min-width: 0;
  }

  .stat-title {
    font-size: 12px;
    color: var(--color-text-3);
    margin-bottom: 4px;
  }

  .stat-value {
    font-size: 22px;
    font-weight: 600;
    color: var(--color-text-1);
    line-height: 1.2;
  }

  .stat-suffix {
    font-size: 14px;
    color: var(--color-text-3);
    font-weight: 400;
  }

  .stat-desc {
    font-size: 11px;
    color: var(--color-text-3);
    margin-top: 4px;
  }
}

.chart-container {
  width: 100%;
  height: 280px;
  margin-top: 12px;
}

@media (max-width: 768px) {
  .stat-card {
    .stat-value {
      font-size: 18px;
    }
    .stat-icon {
      width: 40px;
      height: 40px;
      font-size: 20px;
    }
  }
  .chart-container {
    height: 220px;
  }
}
</style>
