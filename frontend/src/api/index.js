// API 请求封装 - 使用 axios 封装所有后端接口调用
// baseURL 为空字符串，通过 Vite 代理转发到 http://localhost:8000
import axios from 'axios'
import { Message } from '@arco-design/web-vue'

// 创建 axios 实例
const request = axios.create({
  baseURL: '',
  timeout: 30000,
})

// 响应拦截器：统一处理错误
request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    // 提取后端返回的错误信息
    const msg =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      '请求失败'
    Message.error(msg)
    return Promise.reject(error)
  }
)

// ─── 仪表盘 API ───
export const dashboardApi = {
  // 获取仪表盘统计数据
  getDashboard: () => request.get('/api/dashboard'),
}

// ─── 账号管理 API ───
export const accountsApi = {
  // 获取账号列表
  list: (platform) => request.get('/api/accounts', { params: platform ? { platform } : {} }),
  // 添加账号
  add: (data) => request.post('/api/accounts', data),
  // 批量导入
  import: (data) => request.post('/api/accounts/import', data),
  // 删除账号
  remove: (uid) => request.delete(`/api/accounts/${uid}`),
  // 更新账号
  update: (uid, data) => request.put(`/api/accounts/${uid}`, data),
}

// ─── 签到 API ───
export const checkinApi = {
  // 获取签到状态
  getStatus: (uid) => request.get(`/api/checkin/status/${uid}`),
  // 单账号签到
  checkin: (uid) => request.post(`/api/checkin/${uid}`),
  // 批量签到（同步返回汇总，保留兼容）
  checkinAll: () => request.post('/api/checkin'),
  // 定时签到配置
  getSchedule: () => request.get('/api/checkin/schedule'),
  updateSchedule: (data) => request.put('/api/checkin/schedule', data),
  // 批量签到（流式实时进度，无超时）
  // 后端以 SSE 形式逐条推送事件，前端用 fetch 读取 ReadableStream 实时回调
  checkinAllStream: (onEvent) => {
    return fetch('/api/checkin/stream', { method: 'POST' }).then((resp) => {
      if (!resp.ok) throw new Error('批量签到请求失败: ' + resp.status)
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      return new Promise((resolve, reject) => {
        const pump = () => {
          reader.read().then(({ done, value }) => {
            if (done) { resolve(); return }
            buffer += decoder.decode(value, { stream: true })
            let idx
            while ((idx = buffer.indexOf('\n\n')) >= 0) {
              const chunk = buffer.slice(0, idx)
              buffer = buffer.slice(idx + 2)
              const ev = {}
              chunk.split('\n').forEach((line) => {
                if (line.startsWith('event:')) ev.event = line.slice(6).trim()
                else if (line.startsWith('data:')) ev.data = line.slice(5).trim()
              })
              if (ev.event && ev.data) {
                try { onEvent(ev.event, JSON.parse(ev.data)) } catch (e) { /* ignore parse error */ }
              }
            }
            pump()
          }).catch(reject)
        }
        pump()
      })
    })
  },
}

// ─── 积分 API ───
export const quotaApi = {
  // 查询账号积分
  get: (uid) => request.get(`/api/quota/${uid}`),
  // 刷新所有积分
  refresh: () => request.post('/api/quota/refresh'),
  // 查询付费类型
  getPayment: (uid) => request.get(`/api/quota/${uid}/payment`),
  // 所有账号资源包汇总（默认读 MySQL 缓存；refresh=true 强制打上游）
  getAllPackages: (refresh = false) =>
    request.get('/api/quota/packages/all', { params: refresh ? { refresh: true } : {} }),
}

// ─── API 代理 API ───
export const proxyApi = {
  // 上游 Key 列表
  listKeys: () => request.get('/api/proxy/keys'),
  // 添加上游 Key
  addKey: (data) => request.post('/api/proxy/keys', data),
  // 更新上游 Key
  updateKey: (keyId, data) => request.put(`/api/proxy/keys/${keyId}`, data),
  // 删除上游 Key
  removeKey: (keyId) => request.delete(`/api/proxy/keys/${keyId}`),
  // 子 Key 列表
  listSubKeys: () => request.get('/api/proxy/subkeys'),
  // 创建子 Key
  addSubKey: (data) => request.post('/api/proxy/subkeys', data),
  // 更新子 Key
  updateSubKey: (keyId, data) => request.put(`/api/proxy/subkeys/${keyId}`, data),
  // 删除子 Key
  removeSubKey: (keyId) => request.delete(`/api/proxy/subkeys/${keyId}`),
  // 代理状态
  getStatus: () => request.get('/api/proxy/status'),
  // 启动代理
  start: (data) => request.post('/api/proxy/start', data),
  // 停止代理
  stop: () => request.post('/api/proxy/stop'),
  // 使用统计
  getStats: (days) => request.get('/api/proxy/stats', { params: days ? { days } : {} }),
  // 按客户端维度统计（来源分析）
  getStatsByClient: (days) => request.get('/api/proxy/stats/by-client', { params: days ? { days } : {} }),
  // 请求日志
  getLogs: (limit) => request.get('/api/proxy/logs', { params: limit ? { limit } : {} }),
  // 支持的模型列表
  getModels: () => request.get('/api/proxy/models'),
  // 代理设置
  getSettings: () => request.get('/api/proxy/settings'),
  // 更新设置
  updateSettings: (data) => request.put('/api/proxy/settings', data),
  // 日志文件列表
  getLogFiles: () => request.get('/api/proxy/log-files'),
  // 读取日志文件内容
  getLogFile: (filename) => request.get(`/api/proxy/log-files/${filename}`),
  // 资源包列表（按到期时间排序）
  getPackages: () => request.get('/api/proxy/packages'),
}

// ─── 数据包导入导出 API（MySQL 导出 / 空库导入）───
export const dataApi = {
  // 导出：从 MySQL + 代理存储打口令包
  export: (password = '') =>
    request.post('/api/data/export', null, {
      responseType: 'blob',
      params: password ? { password } : {},
    }),
  // 导入旧版 SQLite .db → MySQL
  import: (file, { replace = false } = {}) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('replace', replace ? 'true' : 'false')
    return request.post('/api/data/import', formData)
  },
  // 导入加密包 → MySQL（空库可直接导入）
  importEncrypted: (file, { password = '', replace = false } = {}) => {
    const formData = new FormData()
    formData.append('file', file)
    if (password) formData.append('password', password)
    formData.append('replace', replace ? 'true' : 'false')
    return request.post('/api/data/import-encrypted', formData)
  },
  // 清空全部数据（需 confirm=CLEAR）
  clear: (opts = {}) =>
    request.post('/api/data/clear', {
      confirm: 'CLEAR',
      clear_proxy: opts.clearProxy !== false,
      clear_settings: opts.clearSettings !== false,
    }),
}

export default {
  dashboardApi,
  accountsApi,
  checkinApi,
  quotaApi,
  proxyApi,
  dataApi,
}
