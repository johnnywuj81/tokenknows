/**
 * AuthLayout · T01 系列(注册/登录/验证邮箱/找回密码)。
 *
 * 设计依据: SharedFoundations.md §7.3
 * 左侧品牌区(bg-warm) + 右侧表单卡
 */

import { Outlet } from 'react-router-dom'

export function AuthLayout() {
  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[5fr_7fr]">
      {/* 左侧品牌区 - 移动端隐藏 */}
      <aside
        className="hidden flex-col justify-between bg-bg-warm p-12 lg:flex"
        aria-hidden="true"
      >
        <div className="space-y-2">
          <p className="font-ui text-eyebrow uppercase tracking-wider text-text-muted">
            TokenKnows
          </p>
          <h1 className="font-content text-display text-text-primary leading-tight">
            把研发过程
            <br />
            沉淀为可发布的
            <br />
            <span className="text-accent-primary-dark">组织资产</span>
          </h1>
        </div>

        <blockquote className="border-l-2 border-accent-primary-border pl-4">
          <p className="font-content text-body-lg text-text-secondary italic">
            "不浪费一滴大模型 token,把每一次 AI 调用都沉淀为可复用、可审计、可发布的知识资产。"
          </p>
          <footer className="mt-2 font-ui text-caption text-text-subtle">
            — 核心理念
          </footer>
        </blockquote>

        <footer className="font-ui text-caption text-text-subtle">
          © 2026 TokenKnows · 私有化部署
        </footer>
      </aside>

      {/* 右侧表单区 */}
      <main className="flex items-center justify-center bg-bg-page p-6 sm:p-12">
        <div className="w-full max-w-md">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
