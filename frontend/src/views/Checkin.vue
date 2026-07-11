<script setup>
// 每日签到页面 - 批量签到、单账号签到、定时签到配置
import { ref, reactive, onMounted, computed } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { IconCheck, IconClockCircle } from '@arco-design/web-vue/es/icon'
import { accountsApi, checkinApi } from '../api'

const loading = ref(false)
const accounts = ref([])
const checkingUid = ref('')
const scheduleSaving = ref(false)
const schedule = reactive({
  enabled: true,
  hour: 0,
  minute: 30,
  next_run: null,
})

// 批量签到实时进度
const progress = reactive({
  running: false,
  total: 0,
  current: 0,
  currentAccount: '',
  success: 0,
  failed: 0,
  already: 0,
  list: [],
})

const scheduleTimeValue = computed({
  get() {
    return `${String(schedule.hour).padStart(2, '0')}:${String(schedule.minute).padStart(2, '0')}`
  },
  set(v) {
    if (!v || typeof v !== 'string') return
    const [h, m] = v.split(':').map((x) => parseInt(x, 10))
    if (!Number.isNaN(h)) schedule.hour = h
    if (!Number.isNaN(m)) schedule.minute = m
  },
})

function isCheckedToday(row) {
  if (typeof row.checkin?.checked_today === 'boolean') {
    return row.checkin.checked_today
  }
  const last = row.checkin?.last_checkin_time
  if (!last) return false
  const d = new Date(last)
  const now = new Date()
  return d.getFullYear() === now.getFullYear() &&
         d.getMonth() === now.getMonth() &&
         d.getDate() === now.getDate()
}

function formatTime(row) {
  const last = row.checkin?.last_checkin_time
  if (!last) return '从未签到'
  return new Date(last).toLocaleString('zh-CN')
}

function formatNextRun(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-CN')
}

async function loadAccounts() {
  loading.value = true
  try {
    accounts.value = (await accountsApi.list()) || []
  } finally {
    loading.value = false
  }
}

async function loadSchedule() {
  try {
    const res = await checkinApi.getSchedule()
    schedule.enabled = !!res.enabled
    schedule.hour = res.hour ?? 0
    schedule.minute = res.minute ?? 30
    schedule.next_run = res.next_run || null
  } catch (e) {
    // 拦截器已提示
  }
}

async function saveSchedule() {
  scheduleSaving.value = true
  try {
    const res = await checkinApi.updateSchedule({
      enabled: schedule.enabled,
      hour: schedule.hour,
      minute: schedule.minute,
    })
    schedule.enabled = !!res.enabled
    schedule.hour = res.hour
    schedule.minute = res.minute
    schedule.next_run = res.next_run || null
    Message.success(
      res.enabled
        ? `定时签到已开启，每日 ${res.time} 自动签到`
        : '定时签到已关闭'
    )
  } catch (e) {
    // 拦截器已提示
  } finally {
    scheduleSaving.value = false
  }
}

function checkinAll() {
  Modal.confirm({
    title: '批量签到',
    content: '确定要对所有账号执行批量签到吗？失败会自动重试 3 次。',
    okText: '开始签到',
    onOk: async () => {
      progress.running = true
      progress.total = 0
      progress.current = 0
      progress.currentAccount = ''
      progress.success = 0
      progress.failed = 0
      progress.already = 0
      progress.list = []
      try {
        await checkinApi.checkinAllStream((event, data) => {
          if (event === 'start') {
            progress.total = data.total
          } else if (event === 'progress') {
            if (data.status === 'checking') {
              progress.current = data.current
              progress.currentAccount = data.account
            } else {
              progress.current = data.current
              progress.currentAccount = ''
              progress.list.push({
                account: data.account,
                status: data.status,
                retries: data.retries || 0,
                streak: data.streak,
                error: data.error,
                message: data.message,
              })
              if (data.status === 'success') progress.success++
              else if (data.status === 'failed') progress.failed++
              else if (data.status === 'already') progress.already++
            }
          } else if (event === 'retry') {
            progress.currentAccount = `${data.account}（第 ${data.attempt} 次重试…）`
          } else if (event === 'done') {
            progress.total = progress.total || (progress.success + progress.failed + progress.already)
            progress.current = progress.total
          }
        })
        Message.success(
          `批量签到完成：成功 ${progress.success}，失败 ${progress.failed}，已签 ${progress.already}`
        )
        loadAccounts()
      } finally {
        progress.running = false
      }
    },
  })
}

async function checkinAccount(row) {
  if (checkingUid.value) return
  checkingUid.value = row.uid
  try {
    const res = await checkinApi.checkin(row.uid)
    if (res.already) {
      Message.info(`账号「${row.nickname}」今日已签到`)
    } else if (res.success) {
      Message.success(`账号「${row.nickname}」签到成功`)
    } else {
      Message.warning(res.error || '签到失败')
    }
    await loadAccounts()
  } catch (e) {
    // 错误已由拦截器提示
  } finally {
    checkingUid.value = ''
  }
}

function formatInt(v) {
  const n = Number(v || 0)
  if (isNaN(n)) return 0
  return Math.round(n)
}

onMounted(() => {
  loadAccounts()
  loadSchedule()
})
</script>

<template>
  <a-spin :loading="loading" class="page-spin">
    <div class="checkin-page">
      <!-- 顶部：批量签到 + 定时签到 -->
      <a-card :bordered="true" style="margin-bottom: 12px">
        <div class="toolbar">
          <a-button type="primary" :loading="progress.running" @click="checkinAll">
            <template #icon><IconCheck /></template>
            批量签到
          </a-button>

          <div class="schedule-box">
            <IconClockCircle class="schedule-icon" />
            <span class="schedule-label">定时签到</span>
            <a-switch v-model="schedule.enabled" :disabled="scheduleSaving" />
            <a-time-picker
              v-model="scheduleTimeValue"
              format="HH:mm"
              value-format="HH:mm"
              :disable-confirm="true"
              style="width: 110px"
              :disabled="scheduleSaving || !schedule.enabled"
            />
            <a-button type="outline" size="small" :loading="scheduleSaving" @click="saveSchedule">
              保存
            </a-button>
            <span v-if="schedule.enabled && schedule.next_run" class="schedule-next">
              下次：{{ formatNextRun(schedule.next_run) }}
            </span>
            <span v-else-if="!schedule.enabled" class="schedule-next text-secondary">已关闭</span>
          </div>
        </div>
      </a-card>

      <!-- 批量签到实时进度 -->
      <a-card
        v-if="progress.running || progress.list.length"
        :bordered="true"
        :title="progress.running ? '批量签到进行中…' : '批量签到结果'"
        style="margin-bottom: 12px"
      >
        <a-progress
          :percent="progress.total ? Math.min(1, (progress.success + progress.failed + progress.already) / progress.total) : 0"
          :status="progress.failed ? 'warning' : 'success'"
        />
        <div class="progress-bar">
          正在签到：<b>{{ progress.currentAccount || '—' }}</b>
          （{{ progress.success + progress.failed + progress.already }}/{{ progress.total }}）｜
          已签 <span class="ok"> {{ progress.success }} </span>
          失败 <span class="bad"> {{ progress.failed }} </span>
          剩余 {{ Math.max(progress.total - (progress.success + progress.failed + progress.already), 0) }}
        </div>

        <a-table
          :data="progress.list"
          stripe
          size="small"
          :pagination="false"
          style="margin-top: 12px"
        >
          <template #columns>
            <a-table-column title="账号" data-index="account" :min-width="120" />
            <a-table-column title="状态" :width="90">
              <template #cell="{ record }">
                <a-tag
                  :color="record.status === 'success' ? 'green' : record.status === 'failed' ? 'red' : 'gray'"
                  size="small"
                >
                  {{ record.status === 'success' ? '成功' : record.status === 'failed' ? '失败' : '已签' }}
                </a-tag>
              </template>
            </a-table-column>
            <a-table-column title="重试" :width="70" align="center">
              <template #cell="{ record }">{{ record.retries > 0 ? record.retries + ' 次' : '—' }}</template>
            </a-table-column>
            <a-table-column title="详情" :min-width="200">
              <template #cell="{ record }">
                <span v-if="record.status === 'success'">连续 {{ record.streak || 0 }} 天</span>
                <span v-else-if="record.status === 'already'">{{ record.message }}</span>
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
                  :loading="checkingUid === record.uid"
                  :disabled="isCheckedToday(record) || (!!checkingUid && checkingUid !== record.uid)"
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
  flex-wrap: wrap;
  gap: 12px;
}

.schedule-box {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.schedule-icon {
  color: var(--color-text-2);
}

.schedule-label {
  font-size: 13px;
  color: var(--color-text-2);
}

.schedule-next {
  font-size: 12px;
  color: var(--color-text-3);
}

.text-secondary {
  color: var(--color-text-3);
}

.progress-bar {
  margin: 8px 0;
  font-size: 13px;
}

.ok {
  color: rgb(var(--success-6));
}

.bad {
  color: rgb(var(--danger-6));
}

.text-danger {
  color: rgb(var(--danger-6));
}
</style>
