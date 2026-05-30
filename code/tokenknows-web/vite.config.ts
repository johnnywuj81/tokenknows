import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

/**
 * Vite dev server
 * - /api → 本地 FastAPI 后端 (tokenknows-api) on :8002
 *   (8000/8001 被 ai-cnc 项目占用; 在 .env.local 用 VITE_API_TARGET 覆盖)
 * - SSE 友好: configure proxyReq 关闭 nginx-style buffering
 *
 * 注意: vite.config 跑在 Node, `.env.local` 不会自动进 process.env, 必须
 * 用 loadEnv 显式加载, 否则 VITE_API_TARGET 静默失效, 代理打到默认端口。
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const API_TARGET =
    env.VITE_API_TARGET ?? process.env.VITE_API_TARGET ?? 'http://localhost:8002'

  return {
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
    // T140: 启动时预编译热路由模块, 减少 cold tab 第一次访问 lazy chunk 时的
    // 即时编译延迟 (https://vite.dev/guide/performance#warm-up-frequently-used-files).
    // 选的都是最常进入的页面 + 它们的核心组件.
    warmup: {
      clientFiles: [
        './src/main.tsx',
        './src/routes/index.tsx',
        './src/components/layouts/AppLayout.tsx',
        './src/components/layouts/AuthLayout.tsx',
        './src/components/guards/RequireAuth.tsx',
        './src/lib/api.ts',
        './src/mocks/browser.ts',
        './src/mocks/handlers.ts',
        './src/features/workbench/WorkbenchPage.tsx',
        './src/features/documents/DocumentPage.tsx',
        './src/features/documents/knowledge-graph/KnowledgeGraphView.tsx',
        './src/features/publish/PublishDialog.tsx',
        './src/features/publish/PublishReceiptPage.tsx',
      ],
    },
  },
  }
})
