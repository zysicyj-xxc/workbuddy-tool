<script setup>
// 每日签到页面 - 批量签到、单账号签到、签到结果展示
import { ref, onMounted } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { IconCheck, IconRefresh } from '@arco-design/web-vue/es/icon'
import { accountsApi, checkinApi } from '../api'

const loading = ref(false)
const accounts = ref([])
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
function checkinAll() {
  Modal.info({
    title: '批量签到',
    content: '确定要对所有账号执行批量签到吗？',
    hideCancel: false,
    okText: '开始签到',
    onOk: async () => {
      loading.value = true
      try {
        const res = await checkinApi.checkinAll()
        batchResult.value = res
        Message.success(
          `批量签到完成：成功 ${res.success}，失败 ${res.failed}，已签 ${res.already || 0}`
        )
        loadAccounts()
      } finally {
        loading.value = false
      }
    },
  })
}

// 单账号签到
async function checkinAccount(row) {
  try {
    await checkinApi.checkin(row.uid)
    Message.success(`账号「${row.nickname}」签到成功`)
    loadAccounts()
  } catch (e) {
    // 错误已由拦截器提示
  }
}

// 积分取整
function formatInt(v) {
  const n = Number(v || 0)
  if (isNaN(n)) return 0
  return Math.round(n)
}

onMounted(loadAccounts)
</script>

<template>
  <a-spin :loading="loading" class="page-spin">
    <div class="checkin-page">
      <!-- 顶部操作栏 -->
      <a-card :bordered="true" style="margin-bottom: 12px">
        <div class="toolbar">
          <a-button type="primary" @click="checkinAll">
            <template #icon><IconCheck /></template>
            批量签到
          </a-button>
          <a-button @click="loadAccounts">
            <template #icon><IconRefresh /></template>
            刷新
          </a-button>
        </div>
      </a-card>

      <!-- 批量签到结果展示 -->
      <a-card
        v-if="batchResult"
        :bordered="true"
        title="批量签到结果"
        style="margin-bottom: 12px"
      >
        <a-descriptions :column="3" bordered :data="[
          { label: '成功', value: batchResult.success },
          { label: '失败', value: batchResult.failed },
          { label: '已签到', value: batchResult.already || 0 },
        ]" />

        <a-table
          v-if="batchResult.details && batchResult.details.length"
          :data="batchResult.details"
          stripe
          :pagination="false"
          style="margin-top: 12px"
        >
          <template #columns>
            <a-table-column title="账号" data-index="nickname" :min-width="120" />
            <a-table-column title="状态" :width="100">
              <template #cell="{ record }">
                <a-tag :color="record.status === 'success' ? 'green' : 'red'" size="small">
                  {{ record.status === 'success' ? '成功' : '失败' }}
                </a-tag>
              </template>
            </a-table-column>
            <a-table-column title="详情" :min-width="200">
              <template #cell="{ record }">
                <span v-if="record.status === 'success'">
                  剩余 {{ formatInt(record.remaining) }} / 总 {{ formatInt(record.total) }}
                </span>
                <span v-else class="text-danger">{{ record.error }}</span>
              </template>
            </a-table-column>
          </template>
        </a-table>
      </a-card>

      <!-- 账号列表 -->
      <a-card :bordered="true" title="账号签到列表">
        <a-table :data="accounts" stripe :pagination="{ pageSize: 20, showTotal: true }">
          <template #columns>
            <a-table-column title="昵称" data-index="nickname" :min-width="140" />
            <a-table-column title="平台" data-index="platform" :width="120" />
            <a-table-column title="连续签到天数" :width="130" align="center">
              <template #cell="{ record }">
                {{ record.checkin?.streak_days || 0 }} 天
              </template>
            </a-table-column>
            <a-table-column title="今日签到" :width="120" align="center">
              <template #cell="{ record }">
                <a-tag :color="isCheckedToday(record) ? 'green' : 'arcoblue'" size="small">
                  {{ isCheckedToday(record) ? '已签到' : '未签到' }}
                </a-tag>
              </template>
            </a-table-column>
            <a-table-column title="签到积分" :width="120" align="center">
              <template #cell="{ record }">
                {{ formatInt(record.checkin?.daily_credit) }}
              </template>
            </a-table-column>
            <a-table-column title="累计积分" :width="120" align="center">
              <template #cell="{ record }">
                {{ formatInt(record.checkin?.total_credits) }}
              </template>
            </a-table-column>
            <a-table-column title="上次签到时间" :min-width="180">
              <template #cell="{ record }">{{ formatTime(record) }}</template>
            </a-table-column>
            <a-table-column title="操作" :width="120" fixed="right">
              <template #cell="{ record }">
                <a-button
                  size="small"
                  type="primary"
                  :disabled="isCheckedToday(record)"
                  @click="checkinAccount(record)"
                >
                  签到
                </a-button>
              </template>
            </a-table-column>
          </template>
        </a-table>
      </a-card>
    </div>
  </a-spin>
</template>

<style lang="scss" scoped>
.page-spin {
  width: 100%;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.text-danger {
  color: rgb(var(--danger-6));
}
</style>
