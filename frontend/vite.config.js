import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  appType: 'spa',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/alert': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        bypass(req) {
          // 仅跳过前端页面路由 (无尾斜杠且无查询参数), API 请求正常代理
          if (req.url === '/alert') return '/index.html'
        },
      },
      '/rule-chain/': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/knowledge-base': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        bypass(req) {
          if (req.url === '/knowledge-base') return '/index.html'
        },
      },
      '/detectors': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/pool-config': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        bypass(req) {
          if (req.url === '/pool-config') return '/index.html'
        },
      },
      '/system': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        bypass(req) {
          if (req.url === '/system') return '/index.html'
        },
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
