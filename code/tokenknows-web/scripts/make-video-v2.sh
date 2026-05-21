#!/usr/bin/env bash
# v2 · 加 macOS say TTS 中文配音 + SRT 字幕 (burn-in)
#
# 流程:
#   1. 读 narration.json → 每段调 say -v Tingting 生成 AIFF
#   2. 转 WAV + 末尾 padding 到固定 25s/slide
#   3. concat 12 段音频 → narration.wav
#   4. 生成 walkthrough.srt 字幕 (基于段时间戳)
#   5. ffmpeg 重新拼视频: 截图 + 标题 overlay + subtitles 烧入 + 音频
#
# 输出: engineering_handoff/walkthrough.mp4 (覆盖 v1, 5 分钟, 含语音 + 字幕)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCREENSHOTS_DIR="${ROOT}/engineering_handoff/demo-screenshots"
OUTPUT="${ROOT}/engineering_handoff/walkthrough.mp4"
SRT_FILE="${ROOT}/engineering_handoff/walkthrough.srt"
NARRATION_JSON="${ROOT}/code/tokenknows-web/scripts/narration.json"
PER_SLIDE_SEC=25

# ─── 字体 ─────────────────────────────────────────────────
FONT=""
for f in \
  "/System/Library/Fonts/PingFang.ttc" \
  "/System/Library/Fonts/STHeiti Medium.ttc" \
  "/Library/Fonts/Arial Unicode.ttf"; do
  if [[ -f "$f" ]]; then FONT="$f"; break; fi
done
[[ -z "${FONT}" ]] && { echo "✗ 未找到中文字体"; exit 1; }
echo "▸ 字体: ${FONT}"

TMP=$(mktemp -d)
trap "rm -rf ${TMP}" EXIT
echo "▸ TMP: ${TMP}"

# ─── 1. 生成 12 段 TTS 音频 ────────────────────────────────
echo "▸ 步骤 1: 生成 12 段 TTS 音频..."
python3 - "${NARRATION_JSON}" "${TMP}" <<'PYEOF'
import json, subprocess, sys, os
nj, tmp_dir = sys.argv[1], sys.argv[2]
with open(nj, encoding='utf-8') as f:
    data = json.load(f)
voice = data.get('voice', 'Tingting')
rate = data.get('rate', 195)
for s in data['slides']:
    n = s['n']
    text = s['text']
    aiff = os.path.join(tmp_dir, f'slide-{n:02d}.aiff')
    print(f'  [{n}] say -v {voice} -r {rate} ({len(text)} 字)', flush=True)
    subprocess.run(
        ['say', '-v', voice, '-r', str(rate), '-o', aiff, text],
        check=True,
    )
PYEOF

# ─── 2. AIFF → WAV padded to 25s ─────────────────────────
echo "▸ 步骤 2: AIFF → WAV padding 到 ${PER_SLIDE_SEC}s/slide..."
for i in 01 02 03 04 05 06 07 08 09 10 11 12; do
  AIFF="${TMP}/slide-${i}.aiff"
  WAV="${TMP}/slide-${i}.wav"
  # apad 让音频补静音到 PER_SLIDE_SEC, atrim 截到正好 PER_SLIDE_SEC
  ffmpeg -y -loglevel error -i "${AIFF}" \
    -af "apad=pad_dur=${PER_SLIDE_SEC},atrim=0:${PER_SLIDE_SEC},asetpts=N/SR/TB" \
    -ar 44100 -ac 2 -c:a pcm_s16le \
    "${WAV}"
done

# ─── 3. concat → narration.wav ────────────────────────────
echo "▸ 步骤 3: concat 12 段..."
CONCAT_LIST="${TMP}/audio_concat.txt"
for i in 01 02 03 04 05 06 07 08 09 10 11 12; do
  echo "file '${TMP}/slide-${i}.wav'" >> "${CONCAT_LIST}"
done
ffmpeg -y -loglevel error -f concat -safe 0 -i "${CONCAT_LIST}" \
  -c:a aac -b:a 128k \
  "${TMP}/narration.m4a"

# ─── 4. 生成 SRT 字幕 ──────────────────────────────────────
echo "▸ 步骤 4: 写 SRT..."
python3 - "${NARRATION_JSON}" "${SRT_FILE}" "${PER_SLIDE_SEC}" <<'PYEOF'
import json, sys
nj, srt_out, per_slide = sys.argv[1], sys.argv[2], int(sys.argv[3])

def fmt(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60); ms = int((t * 1000) % 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def chunk(text, max_chars=22):
    """把一段 narration 切成多个字幕条 (≤22 字, 标点切)."""
    parts = []
    buf = ''
    for ch in text:
        buf += ch
        if (len(buf) >= max_chars and ch in '，。、！？；：') or (len(buf) >= max_chars + 6):
            parts.append(buf.strip('，。、 '))
            buf = ''
    if buf.strip(): parts.append(buf.strip('，。、 '))
    return [p for p in parts if p]

with open(nj, encoding='utf-8') as f:
    data = json.load(f)

with open(srt_out, 'w', encoding='utf-8') as out:
    idx = 0
    for i, s in enumerate(data['slides']):
        start_slide = i * per_slide
        parts = chunk(s['text'])
        if not parts: continue
        # 平均分配时间到每个 chunk
        per_part = (per_slide - 1.5) / len(parts)  # 留 1.5s 末尾缓冲
        for j, part in enumerate(parts):
            t0 = start_slide + j * per_part
            t1 = start_slide + (j + 1) * per_part
            idx += 1
            out.write(f"{idx}\n{fmt(t0)} --> {fmt(t1)}\n{part}\n\n")
print(f"  写入 {idx} 条字幕")
PYEOF

# ─── 5. 重新合成视频 ───────────────────────────────────────
echo "▸ 步骤 5: 拼新视频 (含 audio + burned subs)..."
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

i=0
for png in "${SCREENSHOTS_DIR}"/*.png; do
  TITLE="${TITLES[$i]}"
  OUTSEG="${TMP}/seg-$(printf '%02d' $((i+1))).mp4"
  ffmpeg -y -loglevel error \
    -loop 1 -t ${PER_SLIDE_SEC} \
    -i "${png}" \
    -vf "scale=1280:800:force_original_aspect_ratio=decrease,pad=1280:800:(ow-iw)/2:(oh-ih)/2:color=#f5f4ed,drawbox=y=0:width=1280:height=64:color=#141413@0.92:t=fill,drawtext=fontfile='${FONT}':text='${TITLE}':fontcolor=#faf9f5:fontsize=28:x=24:y=18" \
    -c:v libx264 -preset fast -crf 22 -pix_fmt yuv420p -r 30 \
    "${OUTSEG}"
  i=$((i+1))
done

VIDEO_LIST="${TMP}/video_concat.txt"
for seg in "${TMP}"/seg-*.mp4; do
  echo "file '${seg}'" >> "${VIDEO_LIST}"
done
ffmpeg -y -loglevel error -f concat -safe 0 -i "${VIDEO_LIST}" -c copy "${TMP}/video_silent.mp4"

# burn 字幕进视频 + 混入音频
# subtitles filter 路径要转义 (Windows ':' 问题 / macOS 单引号包裹够)
ffmpeg -y -loglevel error \
  -i "${TMP}/video_silent.mp4" \
  -i "${TMP}/narration.m4a" \
  -vf "subtitles='${SRT_FILE}':force_style='FontName=STHeiti Medium,FontSize=20,PrimaryColour=&H00FAF9F5&,BackColour=&HA0141413&,BorderStyle=4,Outline=0,Shadow=0,Alignment=2,MarginV=40'" \
  -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p \
  -c:a aac -b:a 128k \
  -map 0:v:0 -map 1:a:0 \
  "${OUTPUT}"

# ─── 报告 ─────────────────────────────────────────────────
DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "${OUTPUT}" | cut -d. -f1)
SIZE=$(ls -lh "${OUTPUT}" | awk '{print $5}')
echo
echo "✓ 视频已生成 (含 TTS 配音 + 字幕):"
echo "  ${OUTPUT}"
echo "  duration: ${DURATION}s ($((PER_SLIDE_SEC*12))s 目标 = 5:00)"
echo "  size: ${SIZE}"
echo "  字幕 (软字幕版本): ${SRT_FILE}"
