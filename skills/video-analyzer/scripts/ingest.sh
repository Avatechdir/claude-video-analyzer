#!/usr/bin/env bash
# ingest.sh — приводит вход (YouTube-URL или локальный файл) к локальному видеофайлу.
# Usage: ingest.sh <url-or-path> <workdir>
# Печатает в stdout путь к готовому видеофайлу (последней строкой).
set -euo pipefail

INPUT="${1:?нужен URL или путь к видео}"
WORK="${2:?нужен рабочий каталог}"

mkdir -p "$WORK"

if printf '%s' "$INPUT" | grep -qiE '^https?://'; then
  echo "[ingest] источник: URL → качаю через yt-dlp" >&2
  # YouTube часто требует куки («подтвердите, что не бот»). По умолчанию берём
  # куки из Chrome (пользователь там залогинен); переопределить можно через
  # YTDLP_COOKIES_BROWSER (chrome/safari/firefox) или отключить значением "none".
  BROWSER="${YTDLP_COOKIES_BROWSER:-chrome}"
  COOKIE_ARGS=()
  if [ "$BROWSER" != "none" ]; then
    COOKIE_ARGS=(--cookies-from-browser "$BROWSER")
    echo "[ingest] куки из браузера: $BROWSER" >&2
  fi
  # -f: лучшее видео+аудио в mp4; ограничиваем высоту 1080 (для анализа UI хватает)
  yt-dlp \
    "${COOKIE_ARGS[@]}" \
    -f 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best' \
    --merge-output-format mp4 \
    -o "$WORK/source.%(ext)s" \
    "$INPUT" >&2
  VIDEO="$(ls "$WORK"/source.* 2>/dev/null | head -1)"
else
  echo "[ingest] источник: локальный файл" >&2
  if [ ! -f "$INPUT" ]; then
    echo "ОШИБКА: файл не найден: $INPUT" >&2
    exit 1
  fi
  VIDEO="$INPUT"
fi

if [ -z "${VIDEO:-}" ] || [ ! -f "$VIDEO" ]; then
  echo "ОШИБКА: не удалось получить видеофайл" >&2
  exit 1
fi

echo "[ingest] видео готово: $VIDEO" >&2
printf '%s\n' "$VIDEO"
