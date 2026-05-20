import type { Config } from 'tailwindcss'

/**
 * TokenKnows MVP Tailwind config
 * 颜色 / 字体 / 间距来自 DesignHandoff_TokenKnows_MVP.md §2
 *
 * 用法示例:
 *   <div className="bg-bg-card text-text-primary border border-border-subtle">
 *   <h1 className="font-content text-h1 text-text-primary">
 *   <button className="bg-accent-primary text-inverse-text rounded-md px-4 py-2">
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      colors: {
        // ===== 中性 =====
        'bg-page':       '#f5f4ed',
        'bg-card':       '#faf9f5',
        'bg-warm':       '#e8e6dc',
        'text-primary':  '#141413',
        'text-secondary':'#3a3a37',
        'text-muted':    '#5d5d57',
        'text-subtle':   '#85857c',
        'text-disabled': '#b0aea5',
        'border-subtle': '#e8e6dc',
        'border-medium': '#d4d2c7',

        // ===== 品牌(陶土橙)=====
        'accent-primary':        '#d97757',
        'accent-primary-dark':   '#b8623f',
        'accent-primary-light':  '#fbeae0',
        'accent-primary-border': '#f5d4be',

        // ===== 状态 · 成功(暖橄榄绿)=====
        'success':        '#788c5d',
        'success-dark':   '#5d6e45',
        'success-bg':     '#eef2e3',
        'success-border': '#bdc9a3',

        // ===== 状态 · 警告 =====
        'warning':        '#856226',
        'warning-bg':     '#f5ecd8',
        'warning-border': '#d9c587',

        // ===== 状态 · 危险 =====
        'danger':        '#8a3a2a',
        'danger-strong': '#b94a3a',
        'danger-bg':     '#f5e0dc',
        'danger-border': '#e8c7be',

        // ===== 状态 · 信息 =====
        'info':    '#3d6a96',
        'info-bg': '#e8eef5',

        // ===== 反色(深色容器)=====
        'inverse-bg':     '#141413',
        'inverse-text':   '#faf9f5',
        'inverse-muted':  '#b0aea5',
        'inverse-accent': '#d97757',
      },
      fontFamily: {
        ui:      ['Poppins', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        content: ['Lora', 'Georgia', 'serif'],
        mono:    ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        display:  ['36px', { lineHeight: '1.1',  fontWeight: '600' }],
        h1:       ['30px', { lineHeight: '1.2',  fontWeight: '600' }],
        h2:       ['22px', { lineHeight: '1.3',  fontWeight: '600' }],
        h3:       ['18px', { lineHeight: '1.4',  fontWeight: '600' }],
        'body-lg':['16px', { lineHeight: '1.65', fontWeight: '400' }],
        body:     ['14px', { lineHeight: '1.5',  fontWeight: '400' }],
        'body-sm':['13px', { lineHeight: '1.5',  fontWeight: '400' }],
        caption:  ['12px', { lineHeight: '1.45', fontWeight: '400' }],
        micro:    ['11px', { lineHeight: '1.4',  fontWeight: '500' }],
        eyebrow:  ['11px', { lineHeight: '1.3',  fontWeight: '600', letterSpacing: '0.08em' }],
      },
      spacing: {
        // 4px 基础网格,大部分 Tailwind 默认值已经匹配
        '0.5': '2px',
        '1.5': '6px',
        '2.5': '10px',
      },
      borderRadius: {
        none: '0',
        sm:   '4px',
        DEFAULT: '6px',
        md:   '8px',
        lg:   '12px',
        xl:   '16px',
        '2xl':'20px',
        full: '9999px',
      },
      boxShadow: {
        // DesignHandoff §2.5
        'elev-0': 'none',
        'elev-1': '0 1px 2px rgba(20, 20, 19, 0.06)',
        'elev-2': '0 2px 8px rgba(20, 20, 19, 0.08)',
        'elev-3': '0 8px 24px rgba(20, 20, 19, 0.10)',
        'elev-4': '0 20px 48px rgba(20, 20, 19, 0.14)',
      },
      transitionDuration: {
        fast: '120ms',
        DEFAULT: '180ms',
        slow: '280ms',
      },
    },
  },
  plugins: [],
} satisfies Config
