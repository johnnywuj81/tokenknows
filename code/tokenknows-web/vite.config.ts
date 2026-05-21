import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

/**
 * Vite dev server
 * - /api → 本地 FastAPI 后端 (tokenknows-api) on :8001
 *   (8000 被 ai-cnc 项目占用; 用 VITE_API_TARGET 覆盖)
 * - SSE 友好: configure proxyReq 关闭 nginx-style buffering
 */
const API_TARGET = process.env.VITE_API_TARGET ?? 'http://localhost:8001'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        // SSE: 关代理 buffering 让 event 实时透传
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('X-Accel-Buffering', 'no')
          })
        },
      },
      '/sse': { target: API_TARGET, changeOrigin: true, ws: true },
    },
  },
})
