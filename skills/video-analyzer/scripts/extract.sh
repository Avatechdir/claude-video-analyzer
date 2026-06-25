#!/usr/bin/env bash
# extract.sh — извлекает из видео аудио (16k mono wav) и кадры по плану «анализ → план».
# Usage: extract.sh <video> <workdir>
# Результат: $WORK/audio.wav, $WORK/frames/frame_XXXX.jpg, $WORK/frames/timestamps.txt,
#            $WORK/analysis.txt (сводка структуры: сцены/тишина/план).
#
# Стратегия (по мотивам claude-video-vision: «анализ перед извлечением»):
#   1) дёшево размечаем структуру — карта смен сцены (scenedetect) + тишина (silencedetect),
#      без записи кадров;
#   2) строим план таймкодов (scripts/plan_frames.awk): кадр на каждую смену сцены + редкий
#      добор в длинных «дырах» (тишина → 1 кадр, речь → раз в ~INFILL_STEP), бюджет MAX_FRAMES;
#   3) извлекаем кадры ровно по плану одним проходом.
#
# Env (опц.): MAX_FRAMES (80), ANALYZE_THRESH (0.1), MAX_GAP_SEC (45), INFILL_STEP (30),
#   SILENCE_NOISE (-30dB), SILENCE_MIN (2), SPEECH_RATIO (0.3), MIN_GAP (1.5)
#   Фокус-режим: FOCUS_START / FOCUS_END (SS | MM:SS | HH:MM:SS) — разбирать только отрезок.
#   Кадры и аудио режутся по окну (плотность считается от длины окна), таймкоды АБСОЛЮТНЫЕ.
set -euo pipefail

VIDEO="${1:?нужен путь к видео}"
WORK="${2:?нужен рабочий каталог}"
MAX_FRAMES="${MAX_FRAMES:-80}"
MIN_FRAMES="${MIN_FRAMES:-3}"
ANALYZE_THRESH="${ANALYZE_THRESH:-0.1}"  # низкий порог сцен: ловим и плавные переходы слайдов
MAX_GAP_SEC="${MAX_GAP_SEC:-45}"         # «дыра» без смен сцены длиннее → нужен добор
INFILL_STEP="${INFILL_STEP:-30}"         # шаг редкого добора в «говорящих» дырах (сек)
SILENCE_NOISE="${SILENCE_NOISE:--30dB}"  # порог тишины для silencedetect
SILENCE_MIN="${SILENCE_MIN:-2}"          # мин. длительность тишины (сек)
SPEECH_RATIO="${SPEECH_RATIO:-0.3}"      # дыра = «тишина+статика», если речи меньше этой доли
MIN_GAP="${MIN_GAP:-1.5}"                # кадры ближе этого по времени считаем дублем

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMES="$WORK/frames"
mkdir -p "$FRAMES"

# --- Фокус-режим: окно [FOCUS_START, FOCUS_END] ------------------------------
to_seconds() {  # SS | MM:SS | HH:MM:SS -> целые секунды (10# чтобы не словить octal)
  local t="$1"; local -a p; IFS=: read -ra p <<< "$t"
  case ${#p[@]} in
    1) echo $(( 10#${p[0]} )) ;;
    2) echo $(( 10#${p[0]}*60 + 10#${p[1]} )) ;;
    3) echo $(( 10#${p[0]}*3600 + 10#${p[1]}*60 + 10#${p[2]} )) ;;
    *) echo 0 ;;
  esac
}

FULL_DUR="$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$VIDEO" 2>/dev/null | cut -d. -f1)"
FULL_DUR="${FULL_DUR:-0}"

OFFSET=0
SEEK_ARGS=()
if [ -n "${FOCUS_START:-}" ] || [ -n "${FOCUS_END:-}" ]; then
  START=$( [ -n "${FOCUS_START:-}" ] && to_seconds "$FOCUS_START" || echo 0 )
  if [ -n "${FOCUS_END:-}" ]; then
    END=$(to_seconds "$FOCUS_END")
  else
    END="$FULL_DUR"
  fi
  if [ "$END" -le "$START" ]; then
    echo "ОШИБКА: FOCUS_END ($END с) должен быть больше FOCUS_START ($START с)" >&2
    exit 1
  fi
  OFFSET="$START"
  WIN=$(( END - START ))
  SEEK_ARGS=(-ss "$START" -t "$WIN")   # -ss/-t как ВХОДНЫЕ опции: быстрый seek, pts с нуля
  echo "[extract] фокус-режим: окно ${START}–${END}с (длина ${WIN}с), таймкоды абсолютные" >&2
fi
# Длительность для плана кадров: в фокусе — длина окна, иначе всё видео.
if [ -n "${SEEK_ARGS[*]:-}" ]; then DUR="$WIN"; else DUR="$FULL_DUR"; fi
echo "$OFFSET" > "$WORK/focus_offset"
# ---------------------------------------------------------------------------

echo "[extract] аудио → audio.wav (16kHz mono)" >&2
ffmpeg -y ${SEEK_ARGS[@]+"${SEEK_ARGS[@]}"} -i "$VIDEO" -vn -ar 16000 -ac 1 "$WORK/audio.wav" 2>/dev/null

# Извлечь кадры по списку таймкодов (один проход). Аргумент — файл с таймкодами окна
# (относительными). Пишет $FRAMES/frame_XXXX.jpg и $FRAMES/timestamps.txt (АБСОЛЮТНЫЕ).
extract_at() {
  local plan="$1"
  local log="$FRAMES/ffmpeg.log"
  # eps = ~0.6 кадра, чтобы select поймал ближайший кадр к каждой цели
  local fps eps expr
  fps="$(ffprobe -v quiet -select_streams v -show_entries stream=avg_frame_rate -of csv=p=0 "$VIDEO" 2>/dev/null)"
  eps="$(awk -v r="$fps" 'BEGIN{n=split(r,a,"/"); f=(n==2&&a[2]!=0)?a[1]/a[2]:(r+0); if(f<=0)f=25; e=0.6/f; if(e<0.02)e=0.02; printf "%.4f", e}')"
  expr="$(awk -v e="$eps" '{lo=$1-e; if(lo<0)lo=0; if(NR>1)printf "+"; printf "between(t,%.3f,%.3f)", lo, $1+e}' "$plan")"
  [ -z "$expr" ] && { : > "$FRAMES/timestamps.txt"; return; }
  # select по времени; запятые внутри between() требуют одинарных кавычек в фильтрографе.
  ffmpeg -y ${SEEK_ARGS[@]+"${SEEK_ARGS[@]}"} -i "$VIDEO" \
    -vf "select='${expr}',showinfo,scale='min(1280,iw)':-2" \
    -vsync vfr -frames:v "$MAX_FRAMES" -q:v 3 \
    "$FRAMES/frame_%04d.jpg" 2>"$log" || true
  # pts_time идёт от нуля окна (вход. seek сбрасывает таймштампы) → прибавляем OFFSET.
  grep -oE 'pts_time:[0-9.]+' "$log" 2>/dev/null | sed 's/pts_time://' \
    | awk -v off="$OFFSET" '{printf "%.3f\n", $1+off}' > "$FRAMES/timestamps.txt" || true
  rm -f "$log"
}

# Равномерный запасной план (длительность неизвестна или анализ ничего не дал).
uniform_plan() {
  local n="$1" out="$2"
  awk -v n="$n" -v dur="$DUR" 'BEGIN{ if(dur<=0)dur=n*10; for(i=0;i<n;i++) printf "%.3f\n", dur*(i+0.5)/n }' > "$out"
}

SCENES="$WORK/_scenes.txt"; SIL="$WORK/_silence.txt"; PLAN="$WORK/_plan.txt"

if [ "$DUR" -gt 0 ]; then
  echo "[analyze] карта сцен (порог=$ANALYZE_THRESH) + тишина (порог=$SILENCE_NOISE, мин=${SILENCE_MIN}с)" >&2
  # 1) Сцены: время + сила, без записи кадров (metadata=print в stderr).
  ffmpeg ${SEEK_ARGS[@]+"${SEEK_ARGS[@]}"} -i "$VIDEO" \
    -vf "select='gt(scene,$ANALYZE_THRESH)',metadata=print" -an -f null - 2>"$WORK/_scenelog" || true
  awk '/pts_time:/{t=$0; sub(/.*pts_time:/,"",t); sub(/[^0-9.].*/,"",t); pend=t}
       /scene_score=/{s=$0; sub(/.*scene_score=/,"",s); sub(/[^0-9.].*/,"",s);
                      if(pend!=""){print pend" "s; pend=""}}' "$WORK/_scenelog" > "$SCENES" || true
  n_scenes=$(wc -l < "$SCENES" | tr -d ' ')

  # 2) Тишина: silence_start/silence_end по аудио окна.
  : > "$SIL"
  if [ -f "$WORK/audio.wav" ]; then
    ffmpeg -i "$WORK/audio.wav" -af "silencedetect=noise=$SILENCE_NOISE:d=$SILENCE_MIN" -f null - 2>"$WORK/_sillog" || true
    awk '/silence_start:/{s=$0; sub(/.*silence_start:[ ]*/,"",s); sub(/[^0-9.].*/,"",s); st=s}
         /silence_end:/{e=$0; sub(/.*silence_end:[ ]*/,"",e); sub(/[^0-9.].*/,"",e);
                        if(st!=""){print st" "e; st=""}}' "$WORK/_sillog" > "$SIL" || true
  fi
  n_sil=$(wc -l < "$SIL" | tr -d ' ')

  # 3) План таймкодов из анализа.
  awk -v DUR="$DUR" -v MAXF="$MAX_FRAMES" -v MAXGAP="$MAX_GAP_SEC" -v STEP="$INFILL_STEP" \
      -v MINF="$MIN_FRAMES" -v MINGAP="$MIN_GAP" -v SPEECH_RATIO="$SPEECH_RATIO" \
      -v SCENES="$SCENES" -v SILENCE="$SIL" \
      -f "$SCRIPT_DIR/plan_frames.awk" > "$PLAN" || true
  n_plan=$(wc -l < "$PLAN" | tr -d ' ')
  echo "[plan] сцен=$n_scenes, интервалов тишины=$n_sil → кадров в плане=$n_plan (лимит $MAX_FRAMES)" >&2
else
  echo "[analyze] длительность неизвестна — равномерный план" >&2
  n_scenes=0; n_sil=0
  uniform_plan "$MIN_FRAMES" "$PLAN"
  n_plan=$(wc -l < "$PLAN" | tr -d ' ')
fi

# Извлечение по плану.
extract_at "$PLAN"
count="$(find "$FRAMES" -name 'frame_*.jpg' | wc -l | tr -d ' ')"

# Подстраховка: план/извлечение ничего не дали — равномерная выборка.
if [ "$count" -lt "$MIN_FRAMES" ]; then
  echo "[extract] кадров мало ($count) — равномерная подстраховка" >&2
  rm -f "$FRAMES"/frame_*.jpg
  N=$(( DUR / 10 )); [ "$N" -lt "$MIN_FRAMES" ] && N=$MIN_FRAMES
  [ "$N" -gt "$MAX_FRAMES" ] && N=$MAX_FRAMES
  uniform_plan "$N" "$PLAN"
  extract_at "$PLAN"
  count="$(find "$FRAMES" -name 'frame_*.jpg' | wc -l | tr -d ' ')"
fi

# Сводка структуры для модели (жанр, подсказки по фокусу) и очистка временных файлов.
{
  echo "duration_sec=$DUR"
  echo "focus_offset_sec=$OFFSET"
  echo "scene_changes=$n_scenes"
  echo "silence_intervals=$n_sil"
  echo "planned_frames=$n_plan"
  echo "extracted_frames=$count"
} > "$WORK/analysis.txt"
rm -f "$SCENES" "$SIL" "$PLAN" "$WORK/_scenelog" "$WORK/_sillog"

echo "[extract] готово: кадров=$count, аудио=$WORK/audio.wav, анализ=$WORK/analysis.txt" >&2
printf '%s\n' "$count"
