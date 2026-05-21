#!/usr/bin/env bash
# 把 demo-screenshots/*.png 合成 5 分钟 mp4 视频, 每帧 25s + 顶部标题
#
# 输入:  engineering_handoff/demo-screenshots/*.png  (12 张)
# 输出:  engineering_handoff/walkthrough.mp4

set -euo pipefail

SCREENSHOTS_DIR="$(cd "$(dirname "$0")/../../../engineering_handoff/demo-screenshots" && pwd)"
OUTPUT="$(cd "$(dirname "$0")/../../../engineering_handoff" && pwd)/walkthrough.mp4"
PER_SLIDE_SEC=25
# 1280x800 @2x → 实际 2560x1600. ffmpeg 输出 1280x800.

# ─── 找系统中文字体 ─────────────────────────────────────────
# macOS PingFang 优先, 退化 Helvetica
FONT=""
for f in \
  "/System/Library/Fonts/PingFang.ttc" \
  "/System/Library/Fonts/STHeiti Medium.ttc" \
  "/Library/Fonts/Arial Unicode.ttf"; do
  if [[ -f "$f" ]]; then FONT="$f"; break; fi
done
[[ -z "${FONT}" ]] && { echo "✗ 未找到中文字体"; exit 1; }
echo "▸ 字体: ${FONT}"

# ─── 标题映射 ─────────────────────────────────────────────
declare -a TITLES=(
  "01 · T03 工作台 · 多源研发事件汇聚"
  "02 · T04 事件详情抽屉 · 一键回到原始 PR"
  "03 · T05 文档列表 · 项目知识资产"
  "04 · T06 文档结果页 · 真 LLM 生成"
  "05 · T07 证据链抽屉 · 切换不重 query"
  "06 · T08 章节重生成 · 用指令重写"
  "07 · T09 审批视图 · 章节级粒度通过/退回"
  "08 · T10 脱敏确认 · PII 正则 + 豁免审计"
  "09 · T11 发布对话框 · 多渠道发布"
  "10 · T12 发布回执 · uuid token + 复制"
  "11 · T14 LLM 与出域 · 三层门禁 + dry-run"
  "12 · T15 实例管理 · 私有化部署控制台"
)

# ─── 单帧加 overlay 后输出临时 mp4 ─────────────────────────
TMP=$(mktemp -d)
trap "rm -rf ${TMP}" EXIT

i=0
for png in "${SCREENSHOTS_DIR}"/*.png; do
  TITLE="${TITLES[$i]}"
  OUTSEG="${TMP}/seg-$(printf '%02d' $((i+1))).mp4"
  echo "▸ [$((i+1))/12] ${TITLE}"
  # 单图 → 25s 视频 + 半透明顶部标题条
  ffmpeg -y -loglevel error \
    -loop 1 -t ${PER_SLIDE_SEC} \
    -i "${png}" \
    -vf "scale=1280:800:force_original_aspect_ratio=decrease,pad=1280:800:(ow-iw)/2:(oh-ih)/2:color=#f5f4ed,drawbox=y=0:width=1280:height=64:color=#141413@0.92:t=fill,drawtext=fontfile='${FONT}':text='${TITLE}':fontcolor=#faf9f5:fontsize=28:x=24:y=18:line_spacing=4" \
    -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p -r 30 \
    "${OUTSEG}"
  i=$((i+1))
done

# ─── concat 所有 segments ─────────────────────────────────
echo "▸ concat 12 segments..."
LIST="${TMP}/concat.txt"
for seg in "${TMP}"/seg-*.mp4; do
  echo "file '${seg}'" >> "${LIST}"
done

ffmpeg -y -loglevel error -f concat -safe 0 -i "${LIST}" -c copy "${OUTPUT}"

# 报告
DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "${OUTPUT}" | cut -d. -f1)
SIZE=$(ls -lh "${OUTPUT}" | awk '{print $5}')
echo
echo "✓ 视频已生成: ${OUTPUT}"
echo "  duration: ${DURATION}s (${PER_SLIDE_SEC}s × 12 = $((PER_SLIDE_SEC*12))s)"
echo "  size: ${SIZE}"
