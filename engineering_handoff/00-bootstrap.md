# 00 · 项目脚手架

一次性跑完,以下命令在终端逐个粘贴。预计 15–20 分钟。

> **本文件是 2026-05 在 Linux 沙箱里实际跑通的版本**。和 README 里第一版的差异已经修正,主要变更:
> - React **19** + Vite **8** (Vite 模板默认就给这俩,不能降级)
> - Tailwind **v4**:`tailwind.config.ts` 必须用 `@config` 指令引入,不会自动加载
> - TypeScript **6+** 弃用 `baseUrl`,需加 `ignoreDeprecations: "6.0"`
> - shadcn CLI 4.7 改了 flag(用 `-t vite -p nova`)+ 偶尔会有 registry 鉴权问题,见 §4 替代方案

---

## 1. 创建仓库

```bash
# 选个位置
cd ~/code  # 改成你自己的路径

# Vite + React + TS 模板(默认就是 React 19 + Vite 8)
npm create vite@latest tokenknows-web -- --template react-ts
cd tokenknows-web
npm install
```

跑完应该看到 `package.json` 里 `react: ^19.2.x` + `vite: ^8.x`。如果版本明显更老,你可能装了缓存的旧版,跑一下 `npm cache clean --force` 再试。

---

## 2. 装核心依赖

```bash
# UI / Styling (Tailwind v4 用 @tailwindcss/vite 插件,不再用 postcss)
npm install -D tailwindcss @tailwindcss/vite
npm install class-variance-authority clsx tailwind-merge lucide-react

# 路由 + 状态
npm install react-router-dom zustand @tanstack/react-query
# 注:react-router-dom 现在是 v7;createBrowserRouter API 不变

# 表单 + 校验
npm install react-hook-form zod @hookform/resolvers

# 富文本(T06 需要;TipTap 现在是 v3)
npm install @tiptap/react @tiptap/starter-kit @tiptap/extension-link @tiptap/extension-placeholder

# 工具
npm install date-fns

# Mock 后端
npm install -D msw

# 测试(选装)
npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

---

## 3. 配置 Vite + Tailwind v4

```bash
cat > vite.config.ts << 'EOF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') }
  },
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/sse': { target: 'http://localhost:8000', changeOrigin: true, ws: true }
    }
  }
})
EOF
```

把 **本目录下的 `tailwind.config.ts`** 复制到仓库根。

把 **本目录下的 `tokens.css`** 复制到 `src/styles/tokens.css`。

**关键**:Tailwind v4 不会自动读 `tailwind.config.ts`,要在 CSS 里用 `@config` 显式引入。改 `src/index.css` 为:

```css
@import "tailwindcss";
@config "../tailwind.config.ts";
@import "./styles/tokens.css";
```

> ⚠️ 顺序不能颠倒。`@import "tailwindcss"` 必须最前。

### TypeScript paths 配置

Vite 模板用 references 风格的 tsconfig,paths 要放在 **`tsconfig.app.json`** 里(不是 `tsconfig.json`)。在 `compilerOptions` 里加:

```json
"baseUrl": ".",
"ignoreDeprecations": "6.0",
"paths": { "@/*": ["./src/*"] },
```

> `ignoreDeprecations: "6.0"` 是必须的 — TS 6+ 警告 baseUrl 弃用,不加会让 build 失败。

跑 `npm run build` 验证 — 如果输出 CSS 里能找到 `.bg-bg-card` `.bg-accent-primary` 等 class,token 链路就通了。

---

## 4. 装 shadcn/ui

⚠️ **shadcn 4.7 init 偶尔会有 registry 鉴权问题**(`Not authorized to access ui.shadcn.com/init`)。下面两条路任选其一:

### 路径 A · 标准 init(推荐先试)

```bash
npx shadcn@latest init -t vite -p nova -y
```

参数说明:
- `-t vite` — 使用 vite 模板预设(自动识别 paths/aliases)
- `-p nova` — 默认设计风格(也可选 vega/maia/lyra/mira/luma/sera)
- `-y` — 跳过确认

如果报 `Not authorized`,试旧版:
```bash
npx shadcn@4.6.0 init -t vite -p nova -y
```

成功后会生成 `components.json` + 在 `src/lib/utils.ts` 放 `cn()` helper。

### 路径 B · 手动设置(备份方案)

shadcn 组件本质是 copy-paste 的代码,可以从 [ui.shadcn.com/docs/components](https://ui.shadcn.com/docs/components) 手动复制每个组件到 `src/components/ui/`。先创建一次性骨架:

```bash
mkdir -p src/components/ui src/lib
cat > src/lib/utils.ts << 'EOF'
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
EOF

cat > components.json << 'EOF'
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/index.css",
    "baseColor": "stone",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui"
  }
}
EOF
```

然后让 Claude Code 帮你逐个加组件:把官网的组件源码粘给它,放到 `src/components/ui/`。

### 一次性装常用组件(init 成功后)

```bash
npx shadcn@latest add button card input label dialog drawer dropdown-menu \
  badge tabs separator avatar progress switch tooltip \
  form select textarea checkbox radio-group scroll-area sheet
```

(去掉了 toast — 新版用 sonner 代替,需要时再加。)

> 注:shadcn 组件代码到 `src/components/ui/`,你可以改。CLAUDE.md 里有写。

---

## 5. 配置字体(Lora + Poppins + JetBrains Mono)

在 `index.html` 的 `<head>` 加:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Lora:wght@400;500;600;700&family=Poppins:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
```

(国内访问慢的话,改 `https://fonts.font.im/css2?...` 或者打包到本地。)

---

## 6. 目录结构(让 AI 知道往哪里放东西)

```bash
mkdir -p src/{features,components/shared,hooks,mocks,routes,stores,types}
# (src/components/ui 由 shadcn 创建;src/lib 由路径 B 或 shadcn 创建)

# 占位 README,免得空目录被 git 忽略
for d in features components/shared hooks mocks routes stores types; do
  echo "# $d" > src/$d/README.md
done
```

最终结构:

```
src/
├── components/
│   ├── ui/             ← shadcn 生成的基础组件 (Button, Card, ...)
│   └── shared/         ← 业务通用 (EmptyState, ErrorBoundary, PageHeader, ...)
├── features/           ← 按业务域拆,每屏一个文件夹
│   ├── auth/           ← T01
│   ├── projects/       ← T02
│   ├── workbench/      ← T03
│   ├── events/         ← T04
│   ├── documents/      ← T05, T06
│   ├── evidence/       ← T07
│   ├── generation/     ← T08
│   ├── review/         ← T09
│   ├── redaction/      ← T10
│   ├── publish/        ← T11, T12
│   ├── settings/       ← T13
│   └── admin/          ← T14, T15
├── hooks/              ← useAuth, useProject, useSse, ...
├── lib/                ← api 客户端、format、constants(含 shadcn 的 utils.ts)
├── mocks/              ← MSW handlers
├── routes/             ← React Router 配置
├── stores/             ← Zustand stores
├── styles/             ← tokens.css
└── types/              ← 全局 TS 类型(API DTO 等)
```

---

## 7. 配置 React Router

```bash
cat > src/routes/index.tsx << 'EOF'
import { createBrowserRouter } from 'react-router-dom'

// 占位 lazy 加载,后续每屏完成后填入
export const router = createBrowserRouter([
  { path: '/', element: <div>Workbench placeholder</div> },
  { path: '/login', element: <div>Login placeholder</div> },
  { path: '/register', element: <div>Register placeholder</div> },
  { path: '/projects/new', element: <div>New project placeholder</div> },
  { path: '/projects/:id', element: <div>Project workbench</div> },
  { path: '/projects/:id/documents', element: <div>Document list</div> },
  { path: '/projects/:id/documents/:docId', element: <div>Document page</div> },
  { path: '/projects/:id/settings', element: <div>Project settings</div> },
  { path: '/admin', element: <div>Admin</div> },
])
EOF
```

修改 `src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { router } from './routes'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } }
})

async function enableMocking() {
  if (!import.meta.env.DEV) return
  const { worker } = await import('./mocks/browser')
  return worker.start({ onUnhandledRequest: 'bypass' })
}

enableMocking().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </StrictMode>
  )
})
```

---

## 8. 启动 MSW(已验证)

```bash
npx msw init public/ --save
```

(成功标志:`public/mockServiceWorker.js` 被生成,`package.json` 多了 `msw.workerDirectory` 字段。)

`src/mocks/browser.ts`:

```ts
import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'
export const worker = setupWorker(...handlers)
```

`src/mocks/handlers.ts`(初始版,先放一个 /me 端点确认能跑):

```ts
import { http, HttpResponse } from 'msw'

export const handlers = [
  http.get('/api/v1/me', () => HttpResponse.json({
    id: 'u1', email: 'dev@local', display_name: '开发者', email_verified: true
  })),
]
```

---

## 9. 把 mockup + handoff 文件夹接进来

```bash
# 假设 TokenKnows 文件夹和 tokenknows-web 仓库同级
mkdir -p docs
ln -s ../../TokenKnows/mockups docs/mockups
ln -s ../../TokenKnows/engineering_handoff docs/engineering_handoff
ln -s ../../TokenKnows/PRD_TokenKnows_MVP.md docs/PRD.md
ln -s ../../TokenKnows/TDD_TokenKnows_MVP.md docs/TDD.md
ln -s ../../TokenKnows/DesignHandoff_TokenKnows_MVP.md docs/DesignHandoff.md

# 把 CLAUDE.md 放到仓库根
cp ../TokenKnows/engineering_handoff/CLAUDE.md ./CLAUDE.md
```

(Windows 用户:用 PowerShell `New-Item -ItemType SymbolicLink -Path docs\mockups -Target ..\..\TokenKnows\mockups`,或者直接复制文件夹。)

---

## 10. 跑起来确认

```bash
npm run dev
# 打开 http://localhost:5173
# 应该看到 "Workbench placeholder"
# 打开 devtools, network 看到 GET /api/v1/me 返回 200 (Service Worker fulfilled)
```

---

## ✅ 完成标志

- [ ] `npm run build` 不报错
- [ ] `npm run dev` 不报错
- [ ] 浏览器看到任一占位页
- [ ] DevTools 里 `/api/v1/me` 被 MSW mock 拦截
- [ ] `src/components/ui/` 下能看到 button.tsx 等 shadcn 文件
- [ ] dist/assets/*.css 里 grep `bg-bg-card` 能匹配到 — 说明 token 链路通了
- [ ] `CLAUDE.md` 在仓库根
- [ ] git 初始化好,首次 commit 完成

---

## 🚨 常见报错排雷

| 报错 | 原因 | 解法 |
|---|---|---|
| `Cannot find module '@/...'` | TS paths 没配 | `tsconfig.app.json` 加 `baseUrl + paths + ignoreDeprecations` |
| `Option 'baseUrl' is deprecated` | TS 6+ | 加 `"ignoreDeprecations": "6.0"` |
| 自定义 token class 没生效(`bg-bg-card` 不工作) | Tailwind v4 没读 config | `src/index.css` 顶部加 `@config "../tailwind.config.ts";` |
| shadcn init 报 `Not authorized` | registry 鉴权偶发问题 | 试 `npx shadcn@4.6.0 ...`,或走路径 B 手动设置 |
| MSW worker 404 | `mockServiceWorker.js` 没 init | 重跑 `npx msw init public/ --save` |
| `npm install` 卡很久 | 国内 registry 慢 | `npm config set registry https://registry.npmmirror.com` |

---

接下来:`cat docs/engineering_handoff/tasks/T01-auth.md`,喂给 Claude Code 开始第一屏。
