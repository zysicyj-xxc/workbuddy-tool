<script setup>
// API代理页面 - 代理状态 + 账号管理 + 子Key管理 + 模型列表（多 Tab）
import { ref, reactive, onMounted, computed } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import {
  IconCopy,
  IconRefresh,
  IconPlus,
  IconPlayCircleFill,
  IconPauseCircleFill,
  IconSearch,
  IconLink,
  IconDesktop,
} from '@arco-design/web-vue/es/icon'
import { proxyApi, accountsApi } from '../api'

// ─── 代理服务状态 ───
const statusLoading = ref(false)
const proxyStatus = ref(null)
const startForm = reactive({
  host: '0.0.0.0',
  port: 8002,
  mode: 'local',
})

async function loadStatus() {
  statusLoading.value = true
  try {
    const data = await proxyApi.getStatus()
    if (data) {
      startForm.host = data.host || '0.0.0.0'
      startForm.port = data.port || 8002
      startForm.mode = data.mode || 'local'
    }
    proxyStatus.value = data
  } finally {
    statusLoading.value = false
  }
}

async function startProxy() {
  try {
    await proxyApi.start({ ...startForm })
    Message.success('代理服务已启动')
    loadStatus()
  } catch (e) {}
}

function stopProxy() {
  Modal.warning({
    title: '停止确认',
    content: '确定要停止代理服务吗？',
    hideCancel: false,
    okText: '停止',
    okType: 'danger',
    onOk: async () => {
      await proxyApi.stop()
      Message.success('代理服务已停止')
      loadStatus()
    },
  })
}

// ─── 账号管理（代理池） ───
const keysLoading = ref(false)
const upstreamKeys = ref([])
const addKeyDialogVisible = ref(false)
const addKeyLoading = ref(false)
const allAccounts = ref([])
const selectedUids = ref([])
const accountLoading = ref(false)

/** 代理池已占用：凭证 + account_uid，避免空 api_key 误判 */
const pooledIdentity = computed(() => {
  const keys = new Set()
  const uids = new Set()
  for (const k of upstreamKeys.value) {
    if (k.api_key) keys.add(k.api_key)
    if (k.account_uid) uids.add(k.account_uid)
  }
  return { keys, uids }
})
const availableAccounts = computed(() => {
  const { keys, uids } = pooledIdentity.value
  return allAccounts.value.filter((a) => {
    if (a.uid && uids.has(a.uid)) return false
    if (a.api_key && keys.has(a.api_key)) return false
    return true
  })
})

/** 凭证列：ck_ 截断 / JWT 末6位 / 空 → 未绑定凭证 */
function formatCredential(key) {
  const v = (key || '').trim()
  if (!v) return { text: '未绑定凭证', kind: 'empty' }
  if (v.startsWith('ck_')) return { text: `${v.slice(0, 16)}…`, kind: 'ck' }
  // JWT 通常很长且含点
  if (v.includes('.') || v.length > 40) {
    return { text: `…${v.slice(-6)}`, kind: 'jwt' }
  }
  return { text: v.length > 20 ? `${v.slice(0, 16)}…` : v, kind: 'other' }
}

/** 积分列：解析「剩余/总量」，失败退回原串或 - */
function formatPoints(points) {
  const p = (points || '').trim()
  if (!p) return '-'
  const m = p.match(/^([\d.]+)\s*\/\s*([\d.]+)$/)
  if (m) return `${Math.round(Number(m[1]))} / ${Math.round(Number(m[2]))}`
  return p
}

function displayNickname(record) {
  return record.label || record.key_id || '-'
}

async function loadUpstreamKeys() {
  keysLoading.value = true
  try {
    upstreamKeys.value = (await proxyApi.listKeys()) || []
  } finally {
    keysLoading.value = false
  }
}

async function openAddKeyDialog() {
  selectedUids.value = []
  addKeyDialogVisible.value = true
  accountLoading.value = true
  try {
    allAccounts.value = (await accountsApi.list()) || []
  } finally {
    accountLoading.value = false
  }
}

// 全选/反全选（通过 selectedUids 实现）
function handleSelectAll(checked) {
  selectedUids.value = checked ? availableAccounts.value.map((a) => a.uid) : []
}

// 表格选择变化
function handleSelectionChange(rows) {
  selectedUids.value = rows.map((r) => r.uid)
}

async function submitAddKey() {
  if (!selectedUids.value.length) {
    Message.warning('请至少选择一个账号')
    return
  }
  addKeyLoading.value = true
  try {
    const selected = allAccounts.value.filter((a) => selectedUids.value.includes(a.uid))
    let okCount = 0
    for (const acc of selected) {
      try {
        await proxyApi.addKey({ uid: acc.uid })
        okCount++
      } catch (e) {
        // 单个失败不阻断
      }
    }
    Message.success(`已添加 ${okCount} 个账号到代理池`)
    addKeyDialogVisible.value = false
    loadUpstreamKeys()
  } finally {
    addKeyLoading.value = false
  }
}

function removeUpstreamKey(row) {
  Modal.warning({
    title: '移除确认',
    content: `确定将账号「${displayNickname(row)}」移出代理池吗？`,
    hideCancel: false,
    okText: '移出',
    okType: 'danger',
    onOk: async () => {
      await proxyApi.removeKey(row.key_id)
      Message.success('已移出代理池')
      loadUpstreamKeys()
    },
  })
}

// ─── 子 Key 管理 ───
const subKeysLoading = ref(false)
const subKeys = ref([])
const addSubKeyDialogVisible = ref(false)
const addSubKeyForm = reactive({
  name: '',
  key: '',
  allowed_key_ids: [],
  daily_limit: 0,
  expires_at: '',
})
const addSubKeyLoading = ref(false)
const autoGenKey = ref(true)

// 可调用账号池选择小窗口
const poolPickerVisible = ref(false)
const poolPickerSelected = ref([])
const poolPickerAllChecked = computed({
  get: () =>
    upstreamKeys.value.length > 0 &&
    poolPickerSelected.value.length === upstreamKeys.value.length,
  set: (val) => {
    poolPickerSelected.value = val
      ? upstreamKeys.value.map((k) => k.key_id)
      : []
  },
})

function handlePoolPickerSelection(rows) {
  poolPickerSelected.value = rows.map((r) => r.key_id)
}

const selectedPoolLabels = computed(() => {
  if (!addSubKeyForm.allowed_key_ids.length) return ''
  const m = new Map(upstreamKeys.value.map((k) => [k.key_id, displayNickname(k)]))
  return addSubKeyForm.allowed_key_ids.map((id) => m.get(id) || id).join('、')
})

async function loadSubKeys() {
  subKeysLoading.value = true
  try {
    subKeys.value = (await proxyApi.listSubKeys()) || []
  } finally {
    subKeysLoading.value = false
  }
}

function openAddSubKeyDialog() {
  addSubKeyForm.name = ''
  addSubKeyForm.key = ''
  addSubKeyForm.daily_limit = 0
  addSubKeyForm.expires_at = ''
  autoGenKey.value = true
  addSubKeyDialogVisible.value = true
  if (!upstreamKeys.value.length) {
    loadUpstreamKeys().then(() => {
      addSubKeyForm.allowed_key_ids = upstreamKeys.value.map((k) => k.key_id)
    })
  } else {
    addSubKeyForm.allowed_key_ids = upstreamKeys.value.map((k) => k.key_id)
  }
}

function openPoolPicker() {
  poolPickerSelected.value = [...addSubKeyForm.allowed_key_ids]
  poolPickerVisible.value = true
}

function confirmPoolPicker() {
  if (!poolPickerSelected.value.length) {
    Message.warning('请至少选择一个可调用账号')
    return
  }
  addSubKeyForm.allowed_key_ids = [...poolPickerSelected.value]
  poolPickerVisible.value = false
}

async function submitAddSubKey() {
  if (!addSubKeyForm.name.trim()) {
    Message.warning('请输入子 Key 名称')
    return
  }
  if (!addSubKeyForm.allowed_key_ids.length) {
    Message.warning('请选择可调用账号（点击"选择账号"按钮）')
    return
  }
  addSubKeyLoading.value = true
  try {
    const payload = {
      name: addSubKeyForm.name.trim(),
      key_mode: 1,
      allowed_key_ids: addSubKeyForm.allowed_key_ids,
      allowed_models: [],
      daily_limit: addSubKeyForm.daily_limit,
      expires_at: addSubKeyForm.expires_at,
    }
    if (!autoGenKey.value && addSubKeyForm.key.trim()) {
      payload.key = addSubKeyForm.key.trim()
    }
    await proxyApi.addSubKey(payload)
    Message.success('创建子 Key 成功')
    addSubKeyDialogVisible.value = false
    loadSubKeys()
  } finally {
    addSubKeyLoading.value = false
  }
}

function removeSubKey(row) {
  Modal.warning({
    title: '删除确认',
    content: `确定删除子 Key「${row.name || row.key}」吗？`,
    hideCancel: false,
    okText: '删除',
    okType: 'danger',
    onOk: async () => {
      await proxyApi.removeSubKey(row.key_id)
      Message.success('删除成功')
      loadSubKeys()
    },
  })
}

async function copySubKey(text) {
  try {
    await navigator.clipboard.writeText(text)
    Message.success('已复制到剪贴板')
  } catch (e) {
    Message.error('复制失败')
  }
}

// ─── 模型列表 ───
const modelsLoading = ref(false)
const models = ref([])
const modelSearch = ref('')

const filteredModels = computed(() => {
  if (!modelSearch.value.trim()) return models.value
  const keyword = modelSearch.value.toLowerCase()
  return models.value.filter((m) => (m.id || '').toLowerCase().includes(keyword))
})

async function loadModels() {
  modelsLoading.value = true
  try {
    models.value = (await proxyApi.getModels()) || []
  } finally {
    modelsLoading.value = false
  }
}

function formatContext(len) {
  if (!len) return '-'
  if (len >= 1000000) return `${(len / 1000000).toFixed(1)}M`
  if (len >= 1000) return `${(len / 1000).toFixed(0)}K`
  return String(len)
}

// Tab 切换时按需加载数据
function handleTabChange(name) {
  const n = Number(name)
  if (n === 1 && !upstreamKeys.value.length) loadUpstreamKeys()
  else if (n === 2 && !subKeys.value.length) loadSubKeys()
  else if (n === 3 && !models.value.length) loadModels()
}

onMounted(() => {
  loadStatus()
  // 默认激活第一个 Tab（账号管理），预加载账号池数据
  loadUpstreamKeys()
})
</script>

<template>
  <div>
    <!-- 代理服务状态面板 -->
    <a-card :bordered="true" style="margin-bottom: 12px" :loading="statusLoading">
      <template #title>
        <a-space>
          <IconLink />
          <span>代理服务状态</span>
        </a-space>
      </template>
      <template #extra>
        <a-button type="text" size="small" @click="loadStatus">
          <template #icon><IconRefresh /></template>
          刷新
        </a-button>
      </template>

      <a-descriptions :column="3" bordered :data="[
        {
          label: '运行状态',
          value: proxyStatus?.running ? '运行中' : '已停止',
        },
        { label: 'Base URL', value: proxyStatus?.base_url || '未启动' },
        {
          label: '监听地址',
          value: proxyStatus ? `${proxyStatus.host}:${proxyStatus.port}（${proxyStatus.mode}）` : '-',
        },
      ]" />

      <div v-if="!proxyStatus?.running" style="margin-top: 16px">
        <a-form :model="startForm" layout="inline">
          <a-form-item label="Host">
            <a-input v-model="startForm.host" style="width: 140px" />
          </a-form-item>
          <a-form-item label="Port">
            <a-input-number v-model="startForm.port" :min="1" :max="65535" />
          </a-form-item>
          <a-form-item label="模式">
            <a-select v-model="startForm.mode" style="width: 120px">
              <a-option label="本地" value="local" />
              <a-option label="开放" value="open" />
            </a-select>
          </a-form-item>
          <a-form-item>
            <a-button type="primary" status="success" @click="startProxy">
              <template #icon><IconPlayCircleFill /></template>
              启动代理
            </a-button>
          </a-form-item>
        </a-form>
      </div>
      <div v-else style="margin-top: 16px">
        <a-button status="danger" @click="stopProxy">
          <template #icon><IconPauseCircleFill /></template>
          停止代理
        </a-button>
      </div>
    </a-card>

    <!-- Tab 页 -->
    <a-card :bordered="true">
      <a-tabs @change="handleTabChange" type="rounded">
        <!-- 账号管理（代理池） -->
        <a-tab-pane key="1" title="账号管理">
          <a-alert type="info" banner style="margin-bottom: 12px">
            从账号管理选择账号加入代理池，代理服务将使用这些账号的 API Key 进行调度
          </a-alert>
          <a-space style="margin-bottom: 12px">
            <a-button type="primary" @click="openAddKeyDialog">
              <template #icon><IconPlus /></template>
              添加账号
            </a-button>
            <a-button @click="loadUpstreamKeys">
              <template #icon><IconRefresh /></template>
              刷新
            </a-button>
            <span class="text-secondary">
              代理池共 {{ upstreamKeys.length }} 个账号
            </span>
          </a-space>
          <a-table
            v-loading="keysLoading"
            :data="upstreamKeys"
            :loading="keysLoading"
            stripe
            :pagination="false"
          >
            <template #columns>
              <a-table-column title="昵称" :min-width="120">
                <template #cell="{ record }">{{ displayNickname(record) }}</template>
              </a-table-column>
              <a-table-column title="凭证" :min-width="200">
                <template #cell="{ record }">
                  <span v-if="formatCredential(record.api_key).kind === 'empty'" class="text-secondary">
                    未绑定凭证
                  </span>
                  <template v-else>
                    <a-tag
                      v-if="formatCredential(record.api_key).kind === 'jwt'"
                      color="orangered"
                      size="small"
                      style="margin-right: 6px"
                    >JWT</a-tag>
                    <code class="text-mono">{{ formatCredential(record.api_key).text }}</code>
                  </template>
                </template>
              </a-table-column>
              <a-table-column title="状态" :width="110">
                <template #cell="{ record }">
                  <a-tag :color="record.status === 'active' ? 'green' : 'arcoblue'" size="small">
                    {{ record.status === 'active' ? '活跃' : record.status }}
                  </a-tag>
                </template>
              </a-table-column>
              <a-table-column title="积分（剩余/总量）" :min-width="140">
                <template #cell="{ record }">{{ formatPoints(record.points) }}</template>
              </a-table-column>
              <a-table-column title="使用次数" :width="100">
                <template #cell="{ record }">{{ record.used_count ?? 0 }}</template>
              </a-table-column>
              <a-table-column title="操作" :width="120" fixed="right">
                <template #cell="{ record }">
                  <a-button size="small" type="text" status="danger" @click="removeUpstreamKey(record)">
                    移出
                  </a-button>
                </template>
              </a-table-column>
            </template>
          </a-table>
        </a-tab-pane>

        <!-- 子 Key 管理 -->
        <a-tab-pane key="2" title="子Key管理">
          <a-alert type="info" banner style="margin-bottom: 12px">
            子 Key 只能调用关联的代理池账号，未关联的账号不会被调度
          </a-alert>
          <a-space style="margin-bottom: 12px">
            <a-button type="primary" @click="openAddSubKeyDialog">
              <template #icon><IconPlus /></template>
              创建子Key
            </a-button>
            <a-button @click="loadSubKeys">
              <template #icon><IconRefresh /></template>
              刷新
            </a-button>
          </a-space>
          <a-table
            :data="subKeys"
            :loading="subKeysLoading"
            stripe
            :pagination="false"
          >
            <template #columns>
              <a-table-column title="名称" :min-width="120">
                <template #cell="{ record }">{{ record.name || '-' }}</template>
              </a-table-column>
              <a-table-column title="Key" :min-width="280">
                <template #cell="{ record }">
                  <a-space>
                    <code class="text-mono">{{ record.key }}</code>
                    <a-button
                      size="mini"
                      type="text"
                      @click="copySubKey(record.key)"
                    >
                      <template #icon><IconCopy /></template>
                    </a-button>
                  </a-space>
                </template>
              </a-table-column>
              <a-table-column title="关联账号数" :width="110">
                <template #cell="{ record }">{{ record.allowed_key_ids?.length || 0 }}</template>
              </a-table-column>
              <a-table-column title="日限额" :width="100">
                <template #cell="{ record }">{{ record.daily_limit || '不限' }}</template>
              </a-table-column>
              <a-table-column title="今日已用" :width="100">
                <template #cell="{ record }">{{ record.daily_used ?? 0 }}</template>
              </a-table-column>
              <a-table-column title="状态" :width="90">
                <template #cell="{ record }">
                  <a-tag :color="record.is_active ? 'green' : 'arcoblue'" size="small">
                    {{ record.is_active ? '启用' : '禁用' }}
                  </a-tag>
                </template>
              </a-table-column>
              <a-table-column title="操作" :width="100" fixed="right">
                <template #cell="{ record }">
                  <a-button size="small" type="text" status="danger" @click="removeSubKey(record)">
                    删除
                  </a-button>
                </template>
              </a-table-column>
            </template>
          </a-table>
        </a-tab-pane>

        <!-- 模型列表 -->
        <a-tab-pane key="3" title="模型列表">
          <div class="model-toolbar">
            <a-input
              v-model="modelSearch"
              placeholder="搜索模型ID"
              allow-clear
              style="width: 320px"
            >
              <template #prefix><IconSearch /></template>
            </a-input>
            <a-button @click="loadModels">
              <template #icon><IconRefresh /></template>
              刷新
            </a-button>
            <span class="text-secondary">
              共 {{ filteredModels.length }} / {{ models.length }} 个模型
            </span>
          </div>
          <a-spin :loading="modelsLoading" class="model-grid-spin">
            <div class="model-grid">
              <a-card
                v-for="m in filteredModels"
                :key="m.id"
                hoverable
                class="model-card"
              >
                <div class="model-card-header">
                  <div class="model-icon">
                    <IconDesktop />
                  </div>
                  <span class="model-id" :title="m.id">{{ m.id }}</span>
                </div>
                <div class="model-card-body">
                  <a-tag size="small" color="arcoblue">
                    上下文 {{ formatContext(m.context_length) }}
                  </a-tag>
                </div>
              </a-card>
              <a-empty
                v-if="!modelsLoading && !filteredModels.length"
                description="暂无模型数据"
                class="model-empty"
              />
            </div>
          </a-spin>
        </a-tab-pane>
      </a-tabs>
    </a-card>

    <!-- 添加账号对话框 -->
    <a-modal
      v-model:visible="addKeyDialogVisible"
      title="选择账号加入代理池"
      :width="640"
      @ok="submitAddKey"
      :ok-loading="addKeyLoading"
      :ok-button-props="{ disabled: !selectedUids.length }"
      ok-text="添加"
    >
      <a-spin :loading="accountLoading">
        <div class="dialog-toolbar">
          <span class="text-secondary">
            可选账号：{{ availableAccounts.length }} 个（已加入代理池的不再显示）
          </span>
          <a-checkbox
            :model-value="selectedUids.length === availableAccounts.length && availableAccounts.length > 0"
            @change="handleSelectAll"
          >
            全选
          </a-checkbox>
        </div>
        <a-table
          :data="availableAccounts"
          :row-key="'uid'"
          :row-selection="{ type: 'checkbox', showCheckedAll: false }"
          v-model:selectedKeys="selectedUids"
          @selection-change="handleSelectionChange"
          stripe
          :pagination="false"
          :scroll="{ y: 360 }"
        >
          <template #columns>
            <a-table-column title="昵称" data-index="nickname" :min-width="120" />
            <a-table-column title="凭证" :min-width="200">
              <template #cell="{ record }">
                <span v-if="!record.api_key" class="text-secondary">手机号/JWT 账号</span>
                <code v-else class="text-mono">{{ formatCredential(record.api_key).text }}</code>
              </template>
            </a-table-column>
            <a-table-column title="剩余/总积分" :width="140">
              <template #cell="{ record }">
                {{ Math.round(Number(record.quota?.credits_remaining) || 0) }} / {{ Math.round(Number(record.quota?.credits_total) || 0) }}
              </template>
            </a-table-column>
            <a-table-column title="状态" :width="90">
              <template #cell="{ record }">
                <a-tag :color="record.status === 'active' ? 'green' : 'arcoblue'" size="small">
                  {{ record.status === 'active' ? '活跃' : record.status }}
                </a-tag>
              </template>
            </a-table-column>
          </template>
        </a-table>
        <a-empty
          v-if="!accountLoading && !availableAccounts.length"
          description="没有可添加的账号（全部已在代理池中）"
        />
      </a-spin>
    </a-modal>

    <!-- 创建子 Key 对话框 -->
    <a-modal
      v-model:visible="addSubKeyDialogVisible"
      title="创建子 Key"
      :width="560"
      @ok="submitAddSubKey"
      :ok-loading="addSubKeyLoading"
      ok-text="创建"
    >
      <a-form :model="addSubKeyForm" layout="vertical">
        <a-form-item label="名称" required>
          <a-input v-model="addSubKeyForm.name" placeholder="子 Key 备注" allow-clear />
        </a-form-item>
        <a-form-item label="Key 生成">
          <a-radio-group v-model="autoGenKey">
            <a-radio :value="true">自动生成随机 Key</a-radio>
            <a-radio :value="false">自定义 Key</a-radio>
          </a-radio-group>
        </a-form-item>
        <a-form-item v-if="!autoGenKey" label="自定义 Key" required>
          <a-input v-model="addSubKeyForm.key" placeholder="sk-xxx" allow-clear />
        </a-form-item>
        <a-form-item label="可调用账号" required>
          <a-button type="primary" @click="openPoolPicker">
            选择账号
          </a-button>
          <a-tag
            v-if="addSubKeyForm.allowed_key_ids.length"
            color="success"
            size="large"
            style="margin-left: 8px"
          >
            已选 {{ addSubKeyForm.allowed_key_ids.length }} / {{ upstreamKeys.length }} 个账号
          </a-tag>
          <a-tag v-else color="danger" size="large" style="margin-left: 8px">未选择</a-tag>
          <div v-if="selectedPoolLabels" class="text-secondary" style="margin-top: 6px; line-height: 1.6">
            {{ selectedPoolLabels }}
          </div>
          <div class="text-secondary" style="margin-top: 4px">
            子 Key 只能调用选中的账号，未选中的不会调度。默认选中全部代理池账号。
          </div>
        </a-form-item>
        <a-form-item label="日限额">
          <a-input-number v-model="addSubKeyForm.daily_limit" :min="0" />
          <span class="text-secondary" style="margin-left: 8px">0 表示不限</span>
        </a-form-item>
        <a-form-item label="过期时间">
          <a-date-picker
            v-model="addSubKeyForm.expires_at"
            show-time
            placeholder="留空表示永不过期"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 可调用账号池选择小窗口 -->
    <a-modal
      v-model:visible="poolPickerVisible"
      title="选择可调用账号"
      :width="640"
      :mask-closable="false"
      @ok="confirmPoolPicker"
      ok-text="确认"
    >
      <div class="dialog-toolbar">
        <a-checkbox v-model="poolPickerAllChecked">
          全选（{{ poolPickerSelected.length }} / {{ upstreamKeys.length }}）
        </a-checkbox>
        <span class="text-secondary">勾选的账号可被本子 Key 调度</span>
      </div>
      <a-table
        :data="upstreamKeys"
        :row-key="'key_id'"
        :row-selection="{ type: 'checkbox', showCheckedAll: false }"
        v-model:selectedKeys="poolPickerSelected"
        @selection-change="handlePoolPickerSelection"
        stripe
        :pagination="false"
        :scroll="{ y: 360 }"
      >
        <template #columns>
          <a-table-column title="昵称" :min-width="120">
            <template #cell="{ record }">{{ displayNickname(record) }}</template>
          </a-table-column>
          <a-table-column title="凭证" :min-width="200">
            <template #cell="{ record }">
              <span v-if="formatCredential(record.api_key).kind === 'empty'" class="text-secondary">
                未绑定凭证
              </span>
              <code v-else class="text-mono">{{ formatCredential(record.api_key).text }}</code>
            </template>
          </a-table-column>
          <a-table-column title="状态" :width="100">
            <template #cell="{ record }">
              <a-tag :color="record.status === 'active' ? 'green' : 'arcoblue'" size="small">
                {{ record.status === 'active' ? '活跃' : record.status || '-' }}
              </a-tag>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-modal>
  </div>
</template>

<style lang="scss" scoped>
.text-secondary {
  color: var(--color-text-3);
  font-size: 12px;
}

.text-mono {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}

.dialog-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.model-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.model-grid-spin {
  display: block;
  width: 100%;
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  min-height: 200px;
}

.model-card {
  transition: transform 0.15s ease, box-shadow 0.15s ease;

  &:hover {
    transform: translateY(-2px);
  }

  .model-card-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
  }

  .model-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: 6px;
    background: rgb(var(--primary-1));
    color: rgb(var(--primary-6));
    font-size: 16px;
    flex-shrink: 0;
  }

  .model-id {
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text-1);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .model-card-body {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
}

.model-empty {
  grid-column: 1 / -1;
}
</style>
