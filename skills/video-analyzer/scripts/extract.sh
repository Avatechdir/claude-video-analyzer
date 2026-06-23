#!/usr/bin/env bash
# extract.sh — извлекает из видео аудио (16k mono wav) и кадры по смене сцены.
# Usage: extract.sh <video> <workdir>
# Результат: $WORK/audio.wav, $WORK/frames/frame_XXXX.jpg, $WORK/frames/timestamps.txt
# Env (опционально): SCENE_THRESH (0.3), MAX_FRAMES (80)
set -euo pipefail

VIDEO="${1:?нужен путь к видео}"
WORK="${2:?нужен рабочий каталог}"
SCENE_THRESH="${SCENE_THRESH:-0.3}"
MAX_FRAMES="${MAX_FRAMES:-80}"
MIN_FRAMES=3

FRAMES="$WORK/frames"
mkdir -p "$FRAMES"

echo "[extract] аудио → audio.wav (16kHz mono)" >&2
ffmpeg -y -i "$VIDEO" -vn -ar 16000 -ac 1 "$WORK/audio.wav" 2>/dev/null

# Кадры. Фильтр showinfo логирует pts_time каждого выводимого кадра в stderr
# (после select → только отобранные кадры, в том же порядке, что и файлы).
# Парсим лог в timestamps.txt: строка N = таймкод (сек) кадра frame_000N.
run_frames() {
  local vf="$1"
  local log="$FRAMES/ffmpeg.log"
  ffmpeg -y -i "$VIDEO" \
    -vf "${vf},showinfo,scale='min(1280,iw)':-2" \
    -vsync vfr -frames:v "$MAX_FRAMES" -q:v 3 \
    "$FRAMES/frame_%04d.jpg" 2>"$log"
  grep -oE 'pts_time:[0-9.]+' "$log" | sed 's/pts_time://' > "$FRAMES/timestamps.txt"
  rm -f "$log"
}

echo "[extract] кадры по смене сцены (порог=$SCENE_THRESH, лимит=$MAX_FRAMES)" >&2
run_frames "select='gt(scene,$SCENE_THRESH)'"

count="$(find "$FRAMES" -name 'frame_*.jpg' | wc -l | tr -d ' ')"
if [ "$count" -lt "$MIN_FRAMES" ]; then
  # Сцен мало (статичное видео, напр. говорящие головы). Берём равномерную выборку
  # ПО ВСЕЙ длительности: N кадров (не более MAX_FRAMES), fps=N/duration — иначе
  # жёсткий лимит съел бы только начало длинного видео.
  DUR="$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$VIDEO" 2>/dev/null | cut -d. -f1)"
  DUR="${DUR:-0}"
  if [ "$DUR" -gt 0 ]; then
    N=$(( DUR / 5 )); [ "$N" -lt "$MIN_FRAMES" ] && N=$MIN_FRAMES
    [ "$N" -gt "$MAX_FRAMES" ] && N=$MAX_FRAMES
    FPS="$N/$DUR"
  else
    FPS="1/5"   # длительность неизвестна — запасной вариант
  fi
  echo "[extract] сцен мало ($count) — равномерная выборка по всей длительности (fps=$FPS)" >&2
  rm -f "$FRAMES"/frame_*.jpg
  run_frames "fps=$FPS"
  count="$(find "$FRAMES" -name 'frame_*.jpg' | wc -l | tr -d ' ')"
fi

echo "[extract] готово: кадров=$count, аудио=$WORK/audio.wav" >&2
printf '%s\n' "$count"
