#!/usr/bin/env bash
# set-token.sh — безопасно сохранить/перезаписать токен HuggingFace для диаризации.
# Запуск: bash scripts/set-token.sh
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF="$SKILL_DIR/.hf_token"

echo "Токен берётся здесь: https://huggingface.co/settings/tokens (тип Read)"
printf "Вставь токен hf_... и нажми Enter (ввод скрытый): "
read -rs HF
echo ""

# Вычищаем любые пробелы/переводы строк/табы, которые могли прилипнуть при вставке.
HF="$(printf '%s' "$HF" | tr -d '[:space:]')"

if [ -z "$HF" ]; then
  echo "❌ Пусто — ничего не сохранил."
  exit 1
fi

printf '%s' "$HF" > "$TF"
chmod 600 "$TF"

LEN="$(wc -c < "$TF" | tr -d ' ')"
PREFIX="$(cut -c1-3 "$TF")"
echo "✅ Сохранено в $TF"
echo "   длина=$LEN символов (ожидается ~37), префикс='$PREFIX'"
if [ "$PREFIX" != "hf_" ]; then
  echo "   ⚠️ токен обычно начинается с 'hf_' — проверь, что скопировал правильную строку"
fi
if [ "$LEN" -gt 60 ]; then
  echo "   ⚠️ длина великовата — возможно, вставилось дважды; запусти скрипт ещё раз"
fi
