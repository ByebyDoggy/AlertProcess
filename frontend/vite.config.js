import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/alert': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        bypass(req) {
          // 仅跳过前端页面路由 (无尾斜杠且无查询参数), API 请求正常代理
          if (req.url === '/alert') return '/index.html'
        },
      },
      '/rule-chain': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        bypass(req) {
          // 仅跳过前端页面路由, API 子路径 (如 /rule-chain/chains) 正常代理
          if (req.url === '/rule-chain') return '/index.html'
        },
      },
      '/knowledge-base': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        bypass(req) {
          if (req.url === '/knowledge-base') return '/index.html'
        },
      },
      '/detectors': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/pool-config': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        bypass(req) {
          if (req.url === '/pool-config') return '/index.html'
        },
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
