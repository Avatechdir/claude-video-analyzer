#!/usr/bin/env bash
# make_report.sh — собрать PDF-отчёт по созвону из markdown (pandoc → weasyprint).
# Usage: make_report.sh <report.md> <assets_dir> <out.pdf>
#   report.md   — отчёт по шаблону из SKILL.md (обложка + выводы + скрины + диалог по ролям)
#   assets_dir  — папка со скриншотами, на которые ссылается markdown (![..](file.jpg))
#   out.pdf     — куда сохранить PDF
# Требует: pandoc + weasyprint (brew). Кириллица ок.
set -euo pipefail

REPORT="${1:?нужен путь к report.md}"
ASSETS="${2:?нужна папка со скриншотами}"
OUT="${3:?нужен путь к out.pdf}"

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CSS="$SKILL_DIR/scripts/report.css"
export PATH="/opt/homebrew/bin:$PATH"

for bin in pandoc weasyprint; do
  command -v "$bin" >/dev/null || { echo "ОШИБКА: нет $bin (brew install $bin)" >&2; exit 1; }
done

TMP_HTML="$(mktemp -t va_report.XXXXXX).html"
trap 'rm -f "$TMP_HTML"' EXIT

# 1) markdown → автономный HTML (картинки вшиваются base64 через --embed-resources)
pandoc "$REPORT" -o "$TMP_HTML" \
  --standalone --embed-resources \
  --resource-path="$ASSETS:$(dirname "$REPORT"):." \
  --css="$CSS" --metadata lang=ru

# 2) HTML → PDF (weasyprint шумит warning'ами про box-shadow/@media — безобидно)
weasyprint "$TMP_HTML" "$OUT" 2>/dev/null || weasyprint "$TMP_HTML" "$OUT"

echo "PDF готов: $OUT"
