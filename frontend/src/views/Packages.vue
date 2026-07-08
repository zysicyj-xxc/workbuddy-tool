<script setup>
// 资源包管理页面 - 汇总所有账号的资源包（与上游 Key 代理池无关）
// 数据来源：/api/quota/packages/all 遍历账号管理中的每个账号，
// 调用 get_user_resource() 获取资源包列表后聚合，等同于账号详情的汇总
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { quotaApi } from '../api'

const loading = ref(false)
const packages = ref([])
// 筛选
const statusFilter = ref('')
const searchKey = ref('')

const statusOptions = [
  { label: '全部', value: '' },
  { label: '有效', value: 'ok' },
  { label: '已过期', value: 'expired' },
  { label: '已耗尽', value: 'exhausted' },
  { label: '未知', value: 'unknown' },
]

// 过滤后的资源包
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

// 汇总统计
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

// 状态映射
function pkgStatusType(status) {
  if (status === 'ok') return 'success'
  if (status === 'expired') return 'danger'
  if (status === 'exhausted') return 'info'
  return 'warning'
}
function pkgStatusText(status) {
  const map = { ok: '有效', expired: '已过期', exhausted: '已耗尽', unknown: '未知' }
  return map[status] || status
}

// 格式化过期时间
function formatCycleEnd(cycleEnd, endTs) {
  if (!cycleEnd) return '-'
  if (endTs) {
    const d = new Date(endTs * 1000)
    const pad = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  }
  return cycleEnd
}

// 剩余天数
function daysLeft(endTs) {
  if (!endTs) return null
  const diff = endTs - Date.now() / 1000
  if (diff <= 0) return 0
  return Math.ceil(diff / 86400)
}

// 剩余天数对应的标签类型
function daysLeftType(endTs) {
  const days = daysLeft(endTs)
  if (days === null) return 'info'
  if (days === 0) return 'danger'
  if (days <= 3) return 'danger'
  if (days <= 7) return 'warning'
  return 'success'
}

// 使用进度颜色
function usageColor(percentage) {
  const remain = 100 - (percentage || 0)
  if (remain > 50) return '#67c23a'
  if (remain > 20) return '#e6a23c'
  return '#f56c6c'
}

// 加载资源包列表
async function loadPackages() {
  loading.value = true
  try {
    packages.value = (await quotaApi.getAllPackages()) || []
  } catch (e) {
    // 错误已由拦截器提示
  } finally {
    loading.value = false
  }
}

onMounted(loadPackages)
</script>

<template>
  <div v-loading="loading">
    <!-- 顶部汇总卡片 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="资源包总数" :value="summary.total" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="有效资源包" :value="summary.valid" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="剩余/总容量" :value="summary.totalRemain" />
          <div style="font-size: 12px; color: #909399; margin-top: 4px">
            / {{ summary.totalCapacity }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="已过期/耗尽" :value="summary.expired + summary.exhausted" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 资源包列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>资源包列表（按到期时间升序，汇总自所有账号）</span>
          <el-button type="primary" link @click="loadPackages">
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div style="margin-bottom: 12px; display: flex; gap: 12px; align-items: center">
        <el-select v-model="statusFilter" placeholder="状态筛选" style="width: 140px" clearable>
          <el-option v-for="o in statusOptions" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <el-input v-model="searchKey" placeholder="搜索账号/名称/类型" clearable style="width: 260px" />
      </div>

      <el-table :data="filteredPackages" stripe border>
        <el-table-column label="所属账号" min-width="120">
          <template #default="{ row }">{{ row.nickname || row.uid || '-' }}</template>
        </el-table-column>
        <el-table-column label="资源包名称" min-width="180">
          <template #default="{ row }">{{ row.package_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="类型" width="110">
          <template #default="{ row }">{{ row.type_label || row.package_type || '-' }}</template>
        </el-table-column>
        <el-table-column label="剩余/总容量" width="130">
          <template #default="{ row }">
            <span style="font-size: 12px; color: #909399">
              {{ row.cycle_remain }} / {{ row.cycle_size }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="使用进度" min-width="180">
          <template #default="{ row }">
            <el-progress
              :percentage="row.usage_percentage"
              :stroke-width="10"
              :color="usageColor(row.usage_percentage)"
            />
          </template>
        </el-table-column>
        <el-table-column label="到期时间" min-width="180">
          <template #default="{ row }">
            <div>{{ formatCycleEnd(row.cycle_end, row.cycle_end_ts) }}</div>
            <el-tag
              v-if="daysLeft(row.cycle_end_ts) !== null"
              :type="daysLeftType(row.cycle_end_ts)"
              size="small"
              style="margin-top: 4px"
            >
              {{ daysLeft(row.cycle_end_ts) === 0 ? '已到期' : `剩 ${daysLeft(row.cycle_end_ts)} 天` }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="pkgStatusType(row.status)" size="small">
              {{ pkgStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!loading && !filteredPackages.length"
        :description="packages.length ? '没有符合条件的资源包' : '暂无资源包数据（资源包来自账号管理的每个账号实时查询）'"
      />
    </el-card>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
