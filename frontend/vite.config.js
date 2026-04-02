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
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass(req) {
          // 仅代理 API 子路径, 跳过前端页面路由
          if (req.url === '/alert' || req.url === '/alert/') return '/index.html'
        },
      },
      '/rule-chain': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        bypass(req) {
          // 仅代理 API 子路径 (如 /rule-chain/chains), 跳过前端 SPA 路由
          if (req.url === '/rule-chain') return '/index.html'
        },
      },
    },
  },
  build: {
    outDir: 'dist',
  },
})
