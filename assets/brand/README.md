# TokenKnows 品牌资产

## 色板

| 用途 | 色值 |
|---|---|
| 主色 · 赤陶 (terracotta) | `#d97757` |
| 主色深 | `#b8623f` |
| 主色浅 / 高光 | `#f3b08c` |
| 深色瓷砖渐变 | `#241b15` → `#171010` |
| 米白 (深底文字) | `#f5efe8` |

与 web 设计 token `accent-primary` 一致(见 `code/tokenknows-web/tailwind.config.ts`)。

## 文件清单

| 文件 | 用途 |
|---|---|
| `tokenknows-logo.svg` + `png/logo-512/256` | 主 logo · 蒸馏漏斗,透明底线条 glyph(Codex 插件市场风格) |
| `tokenknows-logo-tile.svg` + `png/logo-tile-512` | 深色瓷砖版 · README 头图 / app 图标 |
| `tokenknows-mark.svg` + `png/mark-256` `favicon-64/32/16` | 六边形字标 · favicon / composer icon |
| `tokenknows-wordmark(.‑dark).svg` + `png/wordmark(-dark)-1200` | 横版 lockup(字标 + "TokenKnows") |
| `social-preview.svg` + `png/social-preview` | GitHub social preview(1280×640) |

## 字体与许可

Wordmark / social preview 中的文字已**轮廓化为 path**(GitHub 的 SVG CSP 会拦
webfont,轮廓化保证任何环境渲染一致):

- 字体:**Poppins** SemiBold(标题)/ Regular(辅文)
- 来源:[google/fonts/ofl/poppins](https://github.com/google/fonts/tree/main/ofl/poppins)
- 许可:SIL Open Font License 1.1 —— 轮廓嵌入 logo 属明确允许的使用方式

重新生成:`scripts/brand/build-wordmark.mjs`(用法见脚本头注释)。

## 使用规则

- 浅色背景 → `tokenknows-wordmark.svg`(墨色文字);深色背景 → `-dark` 变体
- 瓷砖版用于需要"app 图标"观感的场合;行内/导航用透明 glyph 或六边形字标
- 不要拉伸变形、不要改色、不要给瓷砖版再加圆角容器
