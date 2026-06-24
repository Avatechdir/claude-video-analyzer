#!/usr/bin/env bash
# extract.sh — извлекает из видео аудио (16k mono wav) и кадры по смене сцены.
# Usage: extract.sh <video> <workdir>
# Результат: $WORK/audio.wav, $WORK/frames/frame_XXXX.jpg, $WORK/frames/timestamps.txt
# Env (опционально): SCENE_THRESH (0.3), MAX_FRAMES (80)
set -euo pipefail

VIDEO="${1:?нужен путь к видео}"
WORK="${2:?нужен рабочий каталог}"
SCENE_THRESH="${SCENE_THRESH:-0.3}"
SCENE_THRESH_LOW="${SCENE_THRESH_LOW:-0.12}"   # повтор для слайд-видео с плавными фейдами
MAX_FRAMES="${MAX_FRAMES:-80}"
MIN_FRAMES=3
MIN_FRAMES_PER_MIN="${MIN_FRAMES_PER_MIN:-3}"  # ниже этой плотности считаем «кадров мало»

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

DUR="$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$VIDEO" 2>/dev/null | cut -d. -f1)"
DUR="${DUR:-0}"
# Плотность мала, если кадров < MIN_FRAMES_PER_MIN на минуту (count*60 < per_min*DUR).
too_sparse() { [ "$DUR" -gt 0 ] && [ $(( $1 * 60 )) -lt $(( MIN_FRAMES_PER_MIN * DUR )) ]; }

echo "[extract] кадры по смене сцены (порог=$SCENE_THRESH, лимит=$MAX_FRAMES)" >&2
run_frames "select='gt(scene,$SCENE_THRESH)'"
count="$(find "$FRAMES" -name 'frame_*.jpg' | wc -l | tr -d ' ')"

# Слайд-видео (презентация/демо) меняет кадры плавными фейдами ниже порога 0.3 —
# детектор ловит мало сцен. Повторяем с НИЗКИМ порогом: так каждое переключение
# слайда даёт кадр, а почти-дубли убирает уже сам анализ кадров.
if too_sparse "$count"; then
  echo "[extract] кадров мало ($count на $((DUR/60))м) — повтор со сниженным порогом сцен ($SCENE_THRESH_LOW)" >&2
  rm -f "$FRAMES"/frame_*.jpg
  run_frames "select='gt(scene,$SCENE_THRESH_LOW)'"
  count="$(find "$FRAMES" -name 'frame_*.jpg' | wc -l | tr -d ' ')"
fi

# Всё ещё мало (статичное видео: говорящие головы без шаринга экрана) — равномерная
# выборка ПО ВСЕЙ длительности (fps=N/duration, иначе лимит съел бы только начало).
if [ "$count" -lt "$MIN_FRAMES" ] || too_sparse "$count"; then
  if [ "$DUR" -gt 0 ]; then
    N=$(( DUR / 10 )); [ "$N" -lt "$MIN_FRAMES" ] && N=$MIN_FRAMES
    [ "$N" -gt "$MAX_FRAMES" ] && N=$MAX_FRAMES
    FPS="$N/$DUR"
  else
    FPS="1/10"   # длительность неизвестна — запасной вариант
  fi
  echo "[extract] сцен мало ($count) — равномерная выборка по длительности (fps=$FPS)" >&2
  rm -f "$FRAMES"/frame_*.jpg
  run_frames "fps=$FPS"
  count="$(find "$FRAMES" -name 'frame_*.jpg' | wc -l | tr -d ' ')"
fi

echo "[extract] готово: кадров=$count, аудио=$WORK/audio.wav" >&2
printf '%s\n' "$count"
