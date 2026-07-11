<script setup>
// 资源包管理页面 - 汇总所有账号的资源包
import { ref, computed, onMounted } from 'vue'
import {
  IconRefresh,
  IconSearch,
  IconStorage,
  IconCheckCircle,
  IconCloseCircle,
  IconExclamationCircle,
} from '@arco-design/web-vue/es/icon'
import { quotaApi } from '../api'

const loading = ref(false)
const packages = ref([])
const statusFilter = ref('')
const searchKey = ref('')

const statusOptions = [
  { label: '全部', value: '' },
  { label: '有效', value: 'ok' },
  { label: '已过期', value: 'expired' },
  { label: '已耗尽', value: 'exhausted' },
  { label: '未知', value: 'unknown' },
]

const filteredPackages = computed(() => {
  let list = packages.value
  if (statusFilter.value) {
    list = list.filter((p) => p.status === statusFilter.value)
  }
  if (searchKey.value.trim()) {
    const kw = searchKey.value.toLowerCase()
    list = list.filter(
      (p) =>
        (p.nickname || '').toLowerCase().includes(kw) ||
        (p.package_name || '').toLowerCase().includes(kw) ||
        (p.package_type || '').toLowerCase().includes(kw) ||
        (p.type_label || '').toLowerCase().includes(kw)
    )
  }
  return list
})

const summary = computed(() => {
  const total = packages.value.length
  const valid = packages.value.filter((p) => p.status === 'ok').length
  const expired = packages.value.filter((p) => p.status === 'expired').length
  const exhausted = packages.value.filter((p) => p.status === 'exhausted').length
  const totalRemain = packages.value
    .filter((p) => p.status === 'ok')
    .reduce((s, p) => s + (Number(p.cycle_remain) || 0), 0)
  const totalCapacity = packages.value
    .filter((p) => p.status === 'ok')
    .reduce((s, p) => s + (Number(p.cycle_size) || 0), 0)
  return { total, valid, expired, exhausted, totalRemain, totalCapacity }
})

function pkgStatusType(status) {
  // 返回 Arco 预设颜色名（保证浅色模式下文字清晰）
  if (status === 'ok') return 'green'
  if (status === 'expired') return 'red'
  if (status === 'exhausted') return 'gray'
  return 'orange'
}

function pkgStatusText(status) {
  const map = { ok: '有效', expired: '已过期', exhausted: '已耗尽', unknown: '未知' }
  return map[status] || status
}

function formatCycleEnd(cycleEnd, endTs) {
  if (!cycleEnd) return '-'
  if (endTs) {
    const d = new Date(endTs * 1000)
    const pad = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  return cycleEnd
}

function daysLeft(endTs) {
  if (!endTs) return null
  const diff = endTs - Date.now() / 1000
  if (diff <= 0) return 0
  return Math.ceil(diff / 86400)
}

function daysLeftType(endTs) {
  // 返回 Arco 预设颜色名
  const days = daysLeft(endTs)
  if (days === null) return 'arcoblue'
  if (days === 0) return 'red'
  if (days <= 3) return 'red'
  if (days <= 7) return 'orange'
  return 'green'
}

function usageColor(percentage) {
  const remain = 100 - (percentage || 0)
  if (remain > 50) return '#00b42a'
  if (remain > 20) return '#ff7d00'
  return '#f53f3f'
}

async function loadPackages(force = false) {
  loading.value = true
  try {
    // 默认读 MySQL 缓存（快）；force=true 打上游刷新并写回
    packages.value = (await quotaApi.getAllPackages(force)) || []
  } catch (e) {
    // 错误已由拦截器提示
  } finally {
    loading.value = false
  }
}

// 强制刷新（打上游）
function forceRefresh() {
  loadPackages(true)
}

// 积分取整
function formatInt(v) {
  const n = Number(v || 0)
  if (isNaN(n)) return 0
  return Math.round(n)
}

onMounted(loadPackages)
</script>

<template>
  <a-spin :loading="loading" class="page-spin">
    <div class="packages-page">
      <!-- 顶部汇总卡片 -->
      <a-row :gutter="12" class="summary-row">
        <a-col :xs="12" :sm="12" :md="6">
          <a-card hoverable class="summary-card">
            <div class="summary-body">
              <div class="summary-icon summary-icon-blue">
                <IconStorage />
              </div>
              <div class="summary-content">
                <div class="summary-title">资源包总数</div>
                <div class="summary-value">{{ summary.total }}</div>
              </div>
            </div>
          </a-card>
        </a-col>
        <a-col :xs="12" :sm="12" :md="6">
          <a-card hoverable class="summary-card">
            <div class="summary-body">
              <div class="summary-icon summary-icon-green">
                <IconCheckCircle />
              </div>
              <div class="summary-content">
                <div class="summary-title">有效资源包</div>
                <div class="summary-value">{{ summary.valid }}</div>
              </div>
            </div>
          </a-card>
        </a-col>
        <a-col :xs="12" :sm="12" :md="6">
          <a-card hoverable class="summary-card">
            <div class="summary-body">
              <div class="summary-icon summary-icon-orange">
                <IconExclamationCircle />
              </div>
              <div class="summary-content">
                <div class="summary-title">剩余/总容量</div>
                <div class="summary-value">{{ formatInt(summary.totalRemain) }}</div>
                <div class="summary-desc">/ {{ formatInt(summary.totalCapacity) }}</div>
              </div>
            </div>
          </a-card>
        </a-col>
        <a-col :xs="12" :sm="12" :md="6">
          <a-card hoverable class="summary-card">
            <div class="summary-body">
              <div class="summary-icon summary-icon-red">
                <IconCloseCircle />
              </div>
              <div class="summary-content">
                <div class="summary-title">已过期/耗尽</div>
                <div class="summary-value">{{ summary.expired + summary.exhausted }}</div>
              </div>
            </div>
          </a-card>
        </a-col>
      </a-row>

      <!-- 资源包列表 -->
      <a-card :bordered="true" style="margin-top: 16px">
        <template #title>
          <span>资源包列表</span>
          <span class="text-secondary" style="font-weight: normal; margin-left: 8px">
            （按到期时间升序 · 默认读本地缓存，点刷新同步上游）
          </span>
        </template>
        <template #extra>
          <a-button type="text" size="small" @click="forceRefresh">
            <template #icon><IconRefresh /></template>
            刷新
          </a-button>
        </template>

        <!-- 筛选栏 -->
        <a-space style="margin-bottom: 12px">
          <a-select
            v-model="statusFilter"
            placeholder="状态筛选"
            style="width: 140px"
            allow-clear
          >
            <a-option v-for="o in statusOptions" :key="o.value" :value="o.value">
              {{ o.label }}
            </a-option>
          </a-select>
          <a-input
            v-model="searchKey"
            placeholder="搜索账号/名称/类型"
            allow-clear
            style="width: 260px"
          >
            <template #prefix><IconSearch /></template>
          </a-input>
        </a-space>

        <a-table :data="filteredPackages" stripe :pagination="{ pageSize: 20, showTotal: true }">
          <template #columns>
            <a-table-column title="所属账号" :min-width="120">
              <template #cell="{ record }">{{ record.nickname || record.uid || '-' }}</template>
            </a-table-column>
            <a-table-column title="资源包名称" :min-width="180">
              <template #cell="{ record }">{{ record.package_name || '-' }}</template>
            </a-table-column>
            <a-table-column title="类型" :width="110">
              <template #cell="{ record }">{{ record.type_label || record.package_type || '-' }}</template>
            </a-table-column>
            <a-table-column title="剩余/总容量" :width="130">
              <template #cell="{ record }">
                <span class="text-secondary">
                  {{ formatInt(record.cycle_remain) }} / {{ formatInt(record.cycle_size) }}
                </span>
              </template>
            </a-table-column>
            <a-table-column title="使用进度" :min-width="180">
              <template #cell="{ record }">
                <a-progress
                  :percent="(record.usage_percentage || 0) / 100"
                  :color="usageColor(record.usage_percentage)"
                  size="small"
                />
              </template>
            </a-table-column>
            <a-table-column title="到期时间" :min-width="180">
              <template #cell="{ record }">
                <div>{{ formatCycleEnd(record.cycle_end, record.cycle_end_ts) }}</div>
                <a-tag
                  v-if="daysLeft(record.cycle_end_ts) !== null"
                  :color="daysLeftType(record.cycle_end_ts)"
                  size="small"
                  style="margin-top: 4px"
                >
                  {{ daysLeft(record.cycle_end_ts) === 0 ? '已到期' : `剩 ${daysLeft(record.cycle_end_ts)} 天` }}
                </a-tag>
              </template>
            </a-table-column>
            <a-table-column title="状态" :width="100">
              <template #cell="{ record }">
                <a-tag :color="pkgStatusType(record.status)" size="small">
                  {{ pkgStatusText(record.status) }}
                </a-tag>
              </template>
            </a-table-column>
          </template>
        </a-table>

        <a-empty
          v-if="!loading && !filteredPackages.length"
          :description="packages.length ? '没有符合条件的资源包' : '暂无资源包数据（点刷新从上游同步，平时读本地缓存）'"
          style="padding: 24px"
        />
      </a-card>
    </div>
  </a-spin>
</template>

<style lang="scss" scoped>
.page-spin {
  width: 100%;
}

.text-secondary {
  color: var(--color-text-3);
  font-size: 12px;
}

.summary-row {
  margin-bottom: 4px;
}

.summary-card {
  margin-bottom: 12px;

  :deep(.arco-card-body) {
    padding: 16px;
  }

  .summary-body {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .summary-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: 10px;
    color: #fff;
    font-size: 20px;
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

  .summary-title {
    font-size: 11px;
    color: var(--color-text-3);
  }

  .summary-value {
    font-size: 20px;
    font-weight: 600;
    color: var(--color-text-1);
  }

  .summary-desc {
    font-size: 11px;
    color: var(--color-text-3);
    margin-top: 2px;
  }
}
</style>
