<script setup>
// API代理页面 - 代理状态、账号管理、子Key管理、模型列表
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CopyDocument, Refresh, Plus, VideoPlay, VideoPause, Search, Collection } from '@element-plus/icons-vue'
import { proxyApi, accountsApi } from '../api'

// ─── 代理服务状态 ───
const statusLoading = ref(false)
const proxyStatus = ref(null)

// 启动代理表单
const startForm = reactive({
  host: '0.0.0.0',
  port: 8002,
  mode: 'local',
})

async function loadStatus() {
  statusLoading.value = true
  try {
    const data = await proxyApi.getStatus()
    // 把已保存的设置填入启动表单（持久化配置）
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
    ElMessage.success('代理服务已启动')
    loadStatus()
  } catch (e) {}
}

async function stopProxy() {
  try {
    await ElMessageBox.confirm('确定要停止代理服务吗？', '停止确认', { type: 'warning' })
    await proxyApi.stop()
    ElMessage.success('代理服务已停止')
    loadStatus()
  } catch (e) {}
}

// ─── 账号管理（代理池中的账号 = upstream_keys） ───
const keysLoading = ref(false)
const upstreamKeys = ref([])

// 添加账号对话框：从 /accounts 选账号加入代理池
const addKeyDialogVisible = ref(false)
const addKeyLoading = ref(false)
const allAccounts = ref([]) // 账号管理的全部账号
const selectedUids = ref([]) // 选中的账号 uid 列表
const accountLoading = ref(false)

// 已加入代理池的 api_key 集合（用于过滤已添加的账号）
const pooledApiKeys = computed(() => new Set(upstreamKeys.value.map((k) => k.api_key)))

// 可选账号（未加入代理池的）
const availableAccounts = computed(() =>
  allAccounts.value.filter((a) => !pooledApiKeys.value.has(a.api_key))
)

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

// 全选/反全选
function handleSelectAll(val) {
  if (val) {
    selectedUids.value = availableAccounts.value.map((a) => a.uid)
  } else {
    selectedUids.value = []
  }
}

// 提交添加账号到代理池
async function submitAddKey() {
  if (!selectedUids.value.length) {
    ElMessage.warning('请至少选择一个账号')
    return
  }
  addKeyLoading.value = true
  try {
    const selected = allAccounts.value.filter((a) => selectedUids.value.includes(a.uid))
    let okCount = 0
    for (const acc of selected) {
      try {
        await proxyApi.addKey({
          api_key: acc.api_key,
          label: acc.nickname || acc.api_key.slice(0, 12),
        })
        okCount++
      } catch (e) {
        // 单个失败不阻断
      }
    }
    ElMessage.success(`已添加 ${okCount} 个账号到代理池`)
    addKeyDialogVisible.value = false
    loadUpstreamKeys()
  } finally {
    addKeyLoading.value = false
  }
}

async function removeUpstreamKey(row) {
  try {
    await ElMessageBox.confirm(`确定将账号「${row.label || row.api_key?.slice(0, 12)}」移出代理池吗？`, '移除确认', {
      type: 'warning',
    })
    await proxyApi.removeKey(row.key_id)
    ElMessage.success('已移出代理池')
    loadUpstreamKeys()
  } catch (e) {}
}

// ─── 子 Key 管理 ───
const subKeysLoading = ref(false)
const subKeys = ref([])
const addSubKeyDialogVisible = ref(false)
const addSubKeyForm = reactive({
  name: '',
  key: '', // 留空则后端自动生成随机 key
  allowed_key_ids: [], // 关联的代理池账号 key_id
  daily_limit: 0,
  expires_at: '',
})
const addSubKeyLoading = ref(false)
const autoGenKey = ref(true) // 是否自动生成 key

// 可调用账号池选择小窗口（独立弹窗）
const poolPickerVisible = ref(false)
// 小窗口内表格临时选择（点确认才回填到 addSubKeyForm.allowed_key_ids）
const poolPickerSelected = ref([])
// 小窗口内的"全选"绑定
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
// 小窗口内表格选择变化
function handlePoolPickerSelection(rows) {
  poolPickerSelected.value = rows.map((r) => r.key_id)
}
// 已选账号展示文本
const selectedPoolLabels = computed(() => {
  if (!addSubKeyForm.allowed_key_ids.length) return ''
  const m = new Map(upstreamKeys.value.map((k) => [k.key_id, k.label || k.api_key?.slice(0, 12)]))
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
  // 确保代理池账号已加载（用于选择关联账号）
  if (!upstreamKeys.value.length) {
    loadUpstreamKeys().then(() => {
      // 默认权限：默认全选所有代理池账号
      addSubKeyForm.allowed_key_ids = upstreamKeys.value.map((k) => k.key_id)
    })
  } else {
    // 默认权限：默认全选所有代理池账号
    addSubKeyForm.allowed_key_ids = upstreamKeys.value.map((k) => k.key_id)
  }
}

// 打开可调用账号池小窗口
function openPoolPicker() {
  poolPickerSelected.value = [...addSubKeyForm.allowed_key_ids]
  poolPickerVisible.value = true
}

// 确认选择账号池
function confirmPoolPicker() {
  if (!poolPickerSelected.value.length) {
    ElMessage.warning('请至少选择一个可调用账号')
    return
  }
  addSubKeyForm.allowed_key_ids = [...poolPickerSelected.value]
  poolPickerVisible.value = false
}

async function submitAddSubKey() {
  if (!addSubKeyForm.name.trim()) {
    ElMessage.warning('请输入子 Key 名称')
    return
  }
  if (!addSubKeyForm.allowed_key_ids.length) {
    ElMessage.warning('请选择可调用账号（点击"选择账号"按钮）')
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
    // 如果用户自定义了 key，传给后端
    if (!autoGenKey.value && addSubKeyForm.key.trim()) {
      payload.key = addSubKeyForm.key.trim()
    }
    await proxyApi.addSubKey(payload)
    ElMessage.success('创建子 Key 成功')
    addSubKeyDialogVisible.value = false
    loadSubKeys()
  } finally {
    addSubKeyLoading.value = false
  }
}

async function removeSubKey(row) {
  try {
    await ElMessageBox.confirm(`确定删除子 Key「${row.name || row.key}」吗？`, '删除确认', {
      type: 'warning',
    })
    await proxyApi.removeSubKey(row.key_id)
    ElMessage.success('删除成功')
    loadSubKeys()
  } catch (e) {}
}

async function copySubKey(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch (e) {
    ElMessage.error('复制失败')
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

// 格式化上下文长度
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

onMounted(loadStatus)
</script>

<template>
  <div>
    <!-- 代理服务状态面板 -->
    <el-card shadow="never" style="margin-bottom: 16px" v-loading="statusLoading">
      <template #header>
        <div class="card-header">
          <span>代理服务状态</span>
          <el-button type="primary" link @click="loadStatus">
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </div>
      </template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="运行状态">
          <el-tag :type="proxyStatus?.running ? 'success' : 'danger'">
            {{ proxyStatus?.running ? '运行中' : '已停止' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Base URL">
          {{ proxyStatus?.base_url || '未启动' }}
        </el-descriptions-item>
        <el-descriptions-item label="监听地址">
          {{ proxyStatus?.host }}:{{ proxyStatus?.port }}（{{ proxyStatus?.mode }}）
        </el-descriptions-item>
      </el-descriptions>

      <div style="margin-top: 16px" v-if="!proxyStatus?.running">
        <el-form :inline="true" :model="startForm">
          <el-form-item label="Host">
            <el-input v-model="startForm.host" style="width: 140px" />
          </el-form-item>
          <el-form-item label="Port">
            <el-input-number v-model="startForm.port" :min="1" :max="65535" controls-position="right" />
          </el-form-item>
          <el-form-item label="模式">
            <el-select v-model="startForm.mode" style="width: 120px">
              <el-option label="本地" value="local" />
              <el-option label="开放" value="open" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button type="success" @click="startProxy">
              <el-icon><VideoPlay /></el-icon>启动代理
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <div style="margin-top: 16px" v-else>
        <el-button type="danger" @click="stopProxy">
          <el-icon><VideoPause /></el-icon>停止代理
        </el-button>
      </div>
    </el-card>

    <!-- Tab 页 -->
    <el-card shadow="never">
      <el-tabs @tab-change="handleTabChange">
        <!-- 账号管理（代理池） -->
        <el-tab-pane label="账号管理" name="1">
          <el-alert
            type="info"
            :closable="false"
            style="margin-bottom: 12px"
            title="从账号管理选择账号加入代理池，代理服务将使用这些账号的 API Key 进行调度"
          />
          <div style="margin-bottom: 12px">
            <el-button type="primary" @click="openAddKeyDialog">
              <el-icon><Plus /></el-icon>添加账号
            </el-button>
            <el-button @click="loadUpstreamKeys">
              <el-icon><Refresh /></el-icon>刷新
            </el-button>
            <span style="margin-left: 12px; color: #909399; font-size: 13px">
              代理池共 {{ upstreamKeys.length }} 个账号
            </span>
          </div>
          <el-table v-loading="keysLoading" :data="upstreamKeys" stripe border>
            <el-table-column label="昵称" min-width="120">
              <template #default="{ row }">{{ row.label || '-' }}</template>
            </el-table-column>
            <el-table-column label="API Key" min-width="180">
              <template #default="{ row }">
                <span>{{ row.api_key?.slice(0, 16) }}...</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
                  {{ row.status === 'active' ? '活跃' : row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="积分" min-width="120">
              <template #default="{ row }">{{ row.points || '-' }}</template>
            </el-table-column>
            <el-table-column label="使用次数" width="100">
              <template #default="{ row }">{{ row.used_count ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="danger" @click="removeUpstreamKey(row)">移出</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 子 Key 管理 -->
        <el-tab-pane label="子Key管理" name="2">
          <el-alert
            type="info"
            :closable="false"
            style="margin-bottom: 12px"
            title="子 Key 只能调用关联的代理池账号，未关联的账号不会被调度"
          />
          <div style="margin-bottom: 12px">
            <el-button type="primary" @click="openAddSubKeyDialog">
              <el-icon><Plus /></el-icon>创建子Key
            </el-button>
            <el-button @click="loadSubKeys">
              <el-icon><Refresh /></el-icon>刷新
            </el-button>
          </div>
          <el-table v-loading="subKeysLoading" :data="subKeys" stripe border>
            <el-table-column label="名称" min-width="120">
              <template #default="{ row }">{{ row.name || '-' }}</template>
            </el-table-column>
            <el-table-column label="Key" min-width="260">
              <template #default="{ row }">
                <span class="sub-key-text">{{ row.key }}</span>
                <el-button
                  size="small"
                  link
                  :icon="CopyDocument"
                  @click="copySubKey(row.key)"
                  style="margin-left: 8px"
                />
              </template>
            </el-table-column>
            <el-table-column label="关联账号数" width="110">
              <template #default="{ row }">{{ row.allowed_key_ids?.length || 0 }}</template>
            </el-table-column>
            <el-table-column label="日限额" width="100">
              <template #default="{ row }">{{ row.daily_limit || '不限' }}</template>
            </el-table-column>
            <el-table-column label="今日已用" width="100">
              <template #default="{ row }">{{ row.daily_used ?? 0 }}</template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                  {{ row.is_active ? '启用' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="danger" @click="removeSubKey(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 模型列表 -->
        <el-tab-pane label="模型列表" name="3">
          <div style="margin-bottom: 16px; display: flex; align-items: center; gap: 12px">
            <el-input
              v-model="modelSearch"
              placeholder="搜索模型ID"
              clearable
              :prefix-icon="Search"
              style="width: 320px"
            />
            <el-button @click="loadModels">
              <el-icon><Refresh /></el-icon>刷新
            </el-button>
            <span style="margin-left: auto; color: #909399; font-size: 13px">
              共 {{ filteredModels.length }} / {{ models.length }} 个模型
            </span>
          </div>
          <div v-loading="modelsLoading" class="model-grid">
            <el-card
              v-for="m in filteredModels"
              :key="m.id"
              shadow="hover"
              class="model-card"
            >
              <div class="model-card-header">
                <el-icon size="18" color="#409eff"><Cpu /></el-icon>
                <span class="model-id" :title="m.id">{{ m.id }}</span>
              </div>
              <div class="model-card-body">
                <el-tag size="small" type="info" effect="plain">
                  上下文 {{ formatContext(m.context_length) }}
                </el-tag>
              </div>
            </el-card>
            <el-empty
              v-if="!modelsLoading && !filteredModels.length"
              description="暂无模型数据"
              style="grid-column: 1 / -1"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 添加账号对话框（从账号管理选账号） -->
    <el-dialog v-model="addKeyDialogVisible" title="选择账号加入代理池" width="640px">
      <div v-loading="accountLoading">
        <div style="margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between">
          <span style="color: #606266; font-size: 13px">
            可选账号：{{ availableAccounts.length }} 个（已加入代理池的不再显示）
          </span>
          <el-checkbox
            :model-value="selectedUids.length === availableAccounts.length && availableAccounts.length > 0"
            :indeterminate="selectedUids.length > 0 && selectedUids.length < availableAccounts.length"
            @change="handleSelectAll"
          >
            全选
          </el-checkbox>
        </div>
        <el-table
          :data="availableAccounts"
          stripe
          border
          max-height="400"
          @selection-change="(rows) => (selectedUids = rows.map((r) => r.uid))"
          ref="accountTableRef"
        >
          <el-table-column type="selection" width="50" />
          <el-table-column prop="nickname" label="昵称" min-width="120" />
          <el-table-column label="API Key" min-width="180">
            <template #default="{ row }">
              <span>{{ row.api_key?.slice(0, 20) }}...</span>
            </template>
          </el-table-column>
          <el-table-column label="剩余/总积分" width="140">
            <template #default="{ row }">
              {{ row.quota?.credits_remaining || 0 }} / {{ row.quota?.credits_total || 0 }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
                {{ row.status === 'active' ? '活跃' : row.status }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!accountLoading && !availableAccounts.length" description="没有可添加的账号（全部已在代理池中）" />
      </div>
      <template #footer>
        <el-button @click="addKeyDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="addKeyLoading" :disabled="!selectedUids.length" @click="submitAddKey">
          添加（{{ selectedUids.length }}）
        </el-button>
      </template>
    </el-dialog>

    <!-- 创建子 Key 对话框 -->
    <el-dialog v-model="addSubKeyDialogVisible" title="创建子 Key" width="560px">
      <el-form :model="addSubKeyForm" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="addSubKeyForm.name" placeholder="子 Key 备注" clearable />
        </el-form-item>
        <el-form-item label="Key 生成">
          <el-radio-group v-model="autoGenKey">
            <el-radio :value="true">自动生成随机 Key</el-radio>
            <el-radio :value="false">自定义 Key</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="!autoGenKey" label="自定义 Key" required>
          <el-input v-model="addSubKeyForm.key" placeholder="sk-xxx" clearable />
        </el-form-item>
        <el-form-item label="可调用账号" required>
          <div style="display: flex; align-items: center; gap: 8px; width: 100%">
            <el-button type="primary" plain :icon="Collection" @click="openPoolPicker">
              选择账号
            </el-button>
            <el-tag
              v-if="addSubKeyForm.allowed_key_ids.length"
              type="success"
              size="large"
            >
              已选 {{ addSubKeyForm.allowed_key_ids.length }} / {{ upstreamKeys.length }} 个账号
            </el-tag>
            <el-tag v-else type="danger" size="large">未选择</el-tag>
          </div>
          <div
            v-if="selectedPoolLabels"
            style="font-size: 12px; color: #606266; margin-top: 6px; line-height: 1.6"
          >
            {{ selectedPoolLabels }}
          </div>
          <div style="font-size: 12px; color: #909399; margin-top: 4px">
            子 Key 只能调用选中的账号，未选中的不会调度。默认选中全部代理池账号。
          </div>
        </el-form-item>
        <el-form-item label="日限额">
          <el-input-number v-model="addSubKeyForm.daily_limit" :min="0" controls-position="right" />
          <span style="margin-left: 8px; color: #909399; font-size: 12px">0 表示不限</span>
        </el-form-item>
        <el-form-item label="过期时间">
          <el-date-picker
            v-model="addSubKeyForm.expires_at"
            type="datetime"
            placeholder="留空表示永不过期"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addSubKeyDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="addSubKeyLoading" @click="submitAddSubKey">创建</el-button>
      </template>
    </el-dialog>

    <!-- 可调用账号池选择小窗口（独立弹窗） -->
    <el-dialog
      v-model="poolPickerVisible"
      title="选择可调用账号"
      width="640px"
      append-to-body
      :close-on-click-modal="false"
    >
      <div style="margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between">
        <el-checkbox v-model="poolPickerAllChecked">全选（{{ poolPickerSelected.length }} / {{ upstreamKeys.length }}）</el-checkbox>
        <span style="font-size: 12px; color: #909399">
          勾选的账号可被本子 Key 调度
        </span>
      </div>
      <el-table
        :data="upstreamKeys"
        stripe
        border
        max-height="400"
        @selection-change="handlePoolPickerSelection"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column label="昵称" min-width="120">
          <template #default="{ row }">{{ row.label || '-' }}</template>
        </el-table-column>
        <el-table-column label="API Key" min-width="200">
          <template #default="{ row }">
            <span style="font-family: Consolas, Monaco, monospace; font-size: 12px">
              {{ row.api_key?.slice(0, 18) }}...
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? '活跃' : row.status || '-' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="poolPickerVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmPoolPicker">确认（{{ poolPickerSelected.length }}）</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sub-key-text {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}

/* 模型列表网格样式 */
.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  min-height: 200px;
}

.model-card {
  cursor: default;
  transition: transform 0.15s, box-shadow 0.15s;
}

.model-card:hover {
  transform: translateY(-2px);
}

.model-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.model-id {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-card-body {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* 深色模式适配 */
:global(.dark) .model-id {
  color: #e5eaf3;
}
</style>
