#!/usr/bin/env bash
# transcribe.sh — транскрибирует аудио (faster-whisper) + опц. диаризация (pyannote).
# Usage: transcribe.sh <audio.wav> <workdir> [diarize|plain] [language]
# Результат в $WORK: <base>.srt / <base>.txt / <base>.json (+ метки SPEAKER_xx при diarize)
# Env (опц.): WHISPER_MODEL (large-v3-turbo), WHISPER_THREADS (4)
set -euo pipefail

AUDIO="${1:?нужен путь к audio.wav}"
WORK="${2:?нужен рабочий каталог}"
MODE="${3:-plain}"          # diarize | plain
LANG="${4:-ru}"

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$SKILL_DIR/.venv"
TOKEN_FILE="$SKILL_DIR/.hf_token"
PYSCRIPT="$SKILL_DIR/scripts/diarize_transcribe.py"
MODEL="${WHISPER_MODEL:-small}"
THREADS="${WHISPER_THREADS:-4}"

if [ ! -d "$VENV" ]; then
  echo "ОШИБКА: venv не найден. Сначала запусти scripts/setup.sh" >&2
  exit 1
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# Фикс дедлока ctranslate2/faster-whisper на macOS: без ограничения числа
# потоков транскрипция зависает на этапе декодирования.
export OMP_NUM_THREADS="$THREADS"
export KMP_DUPLICATE_LIB_OK=TRUE

ARGS=(--audio "$AUDIO" --out "$WORK" --model "$MODEL" --language "$LANG" --threads "$THREADS")

if [ "$MODE" = "diarize" ]; then
  if [ -f "$TOKEN_FILE" ] && [ -s "$TOKEN_FILE" ]; then
    echo "[transcribe] режим: диаризация (метки говорящих)" >&2
    ARGS+=(--hf-token "$(cat "$TOKEN_FILE")")
  else
    echo "[transcribe] токен HF не найден — транскрипция БЕЗ меток говорящих" >&2
  fi
else
  echo "[transcribe] режим: простая транскрипция" >&2
fi

echo "[transcribe] модель=$MODEL потоков=$THREADS язык=$LANG" >&2
python "$PYSCRIPT" "${ARGS[@]}" >&2

BASE="$(basename "${AUDIO%.*}")"
echo "[transcribe] готово. Файлы: $WORK/$BASE.{srt,txt,json}" >&2
printf '%s\n' "$WORK/$BASE.srt"
