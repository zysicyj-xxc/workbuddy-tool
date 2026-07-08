<script setup>
// 账号管理页面 - Arco Table + 对话框 + 表单 + 进度条
import { ref, reactive, onMounted } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import {
  IconPlus,
  IconUpload,
  IconRefresh,
  IconDelete,
  IconEye,
  IconCheck,
} from '@arco-design/web-vue/es/icon'
import { accountsApi, checkinApi, quotaApi } from '../api'

const loading = ref(false)
const accounts = ref([])

// 状态标签映射（color 用 Arco 预设颜色名，保证浅色模式下文字清晰）
const statusMap = {
  active: { text: '活跃', color: 'green' },
  quota_exhausted: { text: '积分耗尽', color: 'orange' },
  error: { text: '异常', color: 'red' },
  disabled: { text: '已禁用', color: 'gray' },
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

// 积分取整（统一去掉小数点）
function formatInt(v) {
  const n = Number(v || 0)
  if (isNaN(n)) return 0
  return Math.round(n)
}

// 计算剩余积分百分比（用于进度条）
function quotaPercentage(row) {
  const total = formatInt(row.quota?.credits_total)
  const remaining = formatInt(row.quota?.credits_remaining)
  if (total <= 0) return 0
  return Math.round((remaining / total) * 100)
}

// 进度条颜色
function quotaColor(percentage) {
  if (percentage > 50) return '#00b42a'
  if (percentage > 20) return '#ff7d00'
  return '#f53f3f'
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
    Message.warning('请输入 API Key')
    return
  }
  addLoading.value = true
  try {
    await accountsApi.add({
      api_key: addForm.api_key.trim(),
      nickname: addForm.nickname.trim(),
      platform: addForm.platform,
    })
    Message.success('添加账号成功')
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
    Message.warning('请输入要导入的 API Key')
    return
  }
  importLoading.value = true
  try {
    const res = await accountsApi.import({
      keys: importForm.keys,
      platform: importForm.platform,
    })
    Message.success(`导入完成：成功 ${res.success} 个，失败 ${res.failed} 个`)
    importDialogVisible.value = false
    loadAccounts()
  } finally {
    importLoading.value = false
  }
}

// 刷新所有积分（刷新后立即合并到列表，无需重新请求）
async function refreshAllQuota() {
  loading.value = true
  try {
    const res = await quotaApi.refresh()
    Message.success(`刷新完成：成功 ${res.success} 个，失败 ${res.failed} 个`)
    // 合并刷新结果到本地列表
    if (res?.details?.length) {
      const detailMap = new Map(res.details.map((d) => [d.uid, d]))
      accounts.value = accounts.value.map((a) => {
        const d = detailMap.get(a.uid)
        if (!d || !a.quota) return a
        return {
          ...a,
          quota: {
            ...a.quota,
            credits_remaining: d.remaining ?? a.quota.credits_remaining,
            credits_total: d.total ?? a.quota.credits_total,
          },
        }
      })
    }
    // 后台再异步拉一次列表同步其他字段
    loadAccounts()
  } finally {
    loading.value = false
  }
}

// 删除账号
function removeAccount(row) {
  Modal.warning({
    title: '删除确认',
    content: `确定要删除账号「${row.nickname}」吗？此操作不可恢复。`,
    hideCancel: false,
    okText: '删除',
    okType: 'danger',
    onOk: async () => {
      await accountsApi.remove(row.uid)
      Message.success('删除成功')
      loadAccounts()
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
  <a-spin :loading="loading" class="page-spin">
    <div class="accounts-page">
      <!-- 顶部操作栏 -->
      <a-card :bordered="true" style="margin-bottom: 12px">
        <div class="toolbar">
          <a-space>
            <a-button type="primary" @click="openAddDialog">
              <template #icon><IconPlus /></template>
              添加账号
            </a-button>
            <a-button type="outline" status="success" @click="openImportDialog">
              <template #icon><IconUpload /></template>
              批量导入
            </a-button>
            <a-button type="outline" status="warning" @click="refreshAllQuota">
              <template #icon><IconRefresh /></template>
              刷新积分
            </a-button>
          </a-space>
          <a-button @click="loadAccounts">
            <template #icon><IconRefresh /></template>
            刷新列表
          </a-button>
        </div>
      </a-card>

      <!-- 账号表格 -->
      <a-card :bordered="true">
        <a-table
          :data="accounts"
          :pagination="{
            pageSize: 10,
            showTotal: true,
            showPageSize: true,
          }"
          :scroll="{ x: 1200 }"
          stripe
        >
          <template #columns>
            <a-table-column title="昵称" data-index="nickname" :width="120" ellipsis tooltip />
            <a-table-column title="平台" data-index="platform" :width="90" />

            <a-table-column title="状态" :width="100">
              <template #cell="{ record }">
                <a-tag :color="statusMap[record.status]?.color || 'gray'" bordered>
                  {{ statusMap[record.status]?.text || record.status }}
                </a-tag>
              </template>
            </a-table-column>

            <a-table-column title="剩余积分" :min-width="220">
              <template #cell="{ record }">
                <div class="quota-cell">
                  <div class="quota-text">
                    <span class="quota-remaining">{{ formatInt(record.quota?.credits_remaining) }}</span>
                    <span class="quota-total"> / {{ formatInt(record.quota?.credits_total) }}</span>
                    <span class="quota-used">（已用 {{ formatInt(formatInt(record.quota?.credits_total) - formatInt(record.quota?.credits_remaining)) }}）</span>
                  </div>
                  <a-progress
                    :percent="quotaPercentage(record)"
                    :color="quotaColor(quotaPercentage(record))"
                    size="mini"
                    :show-text="false"
                  />
                </div>
              </template>
            </a-table-column>

            <a-table-column title="签到状态" :width="130">
              <template #cell="{ record }">
                <a-tag
                  :color="isCheckedToday(record) ? 'green' : 'arcoblue'"
                  size="small"
                  bordered
                >
                  {{ isCheckedToday(record) ? '今日已签' : '今日未签' }}
                </a-tag>
                <div class="text-secondary" style="margin-top: 4px">
                  连续 {{ record.checkin?.streak_days || 0 }} 天
                </div>
              </template>
            </a-table-column>

            <a-table-column title="操作" :width="240" fixed="right">
              <template #cell="{ record }">
                <a-space size="small">
                  <a-button size="small" type="text" @click="showQuota(record)">
                    <template #icon><IconEye /></template>
                    详情
                  </a-button>
                  <a-button
                    size="small"
                    type="text"
                    status="primary"
                    @click="checkinAccount(record)"
                  >
                    <template #icon><IconCheck /></template>
                    签到
                  </a-button>
                  <a-button
                    size="small"
                    type="text"
                    status="danger"
                    @click="removeAccount(record)"
                  >
                    <template #icon><IconDelete /></template>
                    删除
                  </a-button>
                </a-space>
              </template>
            </a-table-column>
          </template>
        </a-table>
      </a-card>

      <!-- 添加账号对话框 -->
      <a-modal
        v-model:visible="addDialogVisible"
        title="添加账号"
        :width="500"
        :on-before-ok="async () => {
          await submitAdd()
          return !addLoading.value && !addDialogVisible.value
        }"
        :ok-loading="addLoading"
        @cancel="addDialogVisible = false"
      >
        <a-form :model="addForm" layout="vertical">
          <a-form-item label="API Key" required>
            <a-input
              v-model="addForm.api_key"
              placeholder="请输入以 ck_ 开头的 API Key"
              allow-clear
            />
          </a-form-item>
          <a-form-item label="昵称">
            <a-input
              v-model="addForm.nickname"
              placeholder="可选，留空则自动生成"
              allow-clear
            />
          </a-form-item>
          <a-form-item label="平台">
            <a-select v-model="addForm.platform">
              <a-option v-for="opt in platformOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </a-option>
            </a-select>
          </a-form-item>
        </a-form>
      </a-modal>

      <!-- 批量导入对话框 -->
      <a-modal
        v-model:visible="importDialogVisible"
        title="批量导入账号"
        :width="600"
        @ok="submitImport"
        :ok-loading="importLoading"
        @cancel="importDialogVisible = false"
      >
        <a-form :model="importForm" layout="vertical">
          <a-form-item label="平台">
            <a-select v-model="importForm.platform">
              <a-option v-for="opt in platformOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </a-option>
            </a-select>
          </a-form-item>
          <a-form-item label="API Keys" required>
            <a-textarea
              v-model="importForm.keys"
              :auto-size="{ minRows: 8, maxRows: 16 }"
              placeholder="每行一个 ck_xxx"
              allow-clear
            />
          </a-form-item>
        </a-form>
      </a-modal>

      <!-- 积分详情对话框 -->
      <a-modal
        v-model:visible="quotaDialogVisible"
        :title="`积分详情 - ${currentAccount?.nickname || ''}`"
        :width="800"
        :footer="false"
      >
        <a-spin :loading="quotaLoading">
          <template v-if="quotaData">
            <a-descriptions :column="2" bordered :data="[
              { label: '总积分', value: formatInt(quotaData.total_credits) },
              { label: '剩余积分', value: formatInt(quotaData.remaining_credits) },
              { label: '已用积分', value: formatInt(formatInt(quotaData.total_credits) - formatInt(quotaData.remaining_credits)) },
            ]" style="margin-bottom: 16px" />

            <div class="section-title">资源包列表</div>
            <a-table :data="quotaData.packages" stripe :pagination="false" :bordered="{ wrapper: true, cell: true }">
              <template #columns>
                <a-table-column title="资源包名称" data-index="package_name" :min-width="140" />
                <a-table-column title="类型" data-index="type_label" :width="100" />
                <a-table-column title="容量（剩余/总）" :width="140">
                  <template #cell="{ record }">
                    {{ formatInt(record.capacity_remain) }} / {{ formatInt(record.capacity_size) }}
                  </template>
                </a-table-column>
                <a-table-column title="使用进度" :min-width="180">
                  <template #cell="{ record }">
                    <a-progress
                      :percent="record.usage_percentage"
                      :color="quotaColor(record.remain_percentage)"
                      size="small"
                    />
                  </template>
                </a-table-column>
                <a-table-column title="周期剩余" :width="100">
                  <template #cell="{ record }">
                    {{ formatInt(record.cycle_remain) }} / {{ formatInt(record.cycle_size) }}
                  </template>
                </a-table-column>
                <a-table-column title="状态" :width="90">
                  <template #cell="{ record }">
                    <a-tag :color="record.is_exhausted ? 'red' : 'green'" size="small">
                      {{ record.is_exhausted ? '已耗尽' : '可用' }}
                    </a-tag>
                  </template>
                </a-table-column>
              </template>
            </a-table>
          </template>
        </a-spin>
      </a-modal>
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

.quota-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;

  .quota-text {
    font-size: 12px;
    color: var(--color-text-3);
    line-height: 1.4;
  }

  .quota-remaining {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text-1);
  }

  .quota-total {
    color: var(--color-text-3);
  }

  .quota-used {
    color: var(--color-text-4);
    font-size: 11px;
  }
}

.section-title {
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--color-text-1);
}

.text-secondary {
  color: var(--color-text-3);
  font-size: 12px;
}
</style>
