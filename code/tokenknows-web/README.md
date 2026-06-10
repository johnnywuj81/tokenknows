# tokenknows-web

TokenKnows 前端 —— React 19 SPA。完整产品说明见 [仓库根 README](../../README.md)。

## 技术栈

React 19 · TypeScript · Vite 8 · Tailwind CSS v4 · shadcn/ui · TanStack Query(server state)· Zustand(client state)· React Router v7 · TipTap v3(富文本/证据角标)· @xyflow/react(知识图谱)· MSW(可选 mock)· Vitest + Playwright

## 命令

```bash
npm install
npm run dev            # Vite dev server · http://127.0.0.1:5173
npm run build          # tsc -b + vite build
npm run lint           # ESLint (CI 严格执行, 0 error)
npx tsc --noEmit       # 类型检查
npm run test           # Vitest 单测
npm run test:coverage  # 带覆盖率
npm run test:visual    # Playwright 视觉回归
```

## 配置

```bash
cp .env.local.example .env.local
# VITE_API_TARGET=http://localhost:8001   ← /api 代理目标 (后端地址)
```

`vite.config.ts` 用 `loadEnv` 读 `.env.local`;不配置时默认代理到 `http://localhost:8001`。

## Mock(MSW)· 默认关闭

前端**默认直连真后端**。只有显式 opt-in 才启用 MSW mock:

- URL 加 `?msw=1` → 启用并持久(localStorage `tk-msw-enabled`)
- URL 加 `?msw=0` → 关闭并清掉标记

mock handler 在 `src/mocks/`,仅覆盖部分端点(未覆盖的 bypass 到真后端)。

## 目录约定

每个业务屏一个 feature 目录(`src/features/<屏>/`,含 components/hooks/types);共享 UI 在 `src/components/`(shadcn 原件在 `ui/`);服务端数据一律 TanStack Query,禁止塞 Zustand。详见 [CLAUDE.md](CLAUDE.md)。
