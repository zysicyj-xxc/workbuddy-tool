import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vite 配置 - 配置代理将 /api 转发到后端 FastAPI 服务
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 开发环境代理：将所有 /api 请求转发到后端 FastAPI（http://localhost:8000）
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
