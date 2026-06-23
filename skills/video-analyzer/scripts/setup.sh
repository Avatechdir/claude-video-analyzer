#!/usr/bin/env bash
# setup.sh — разовая установка зависимостей для скилла video-analyzer.
# Идемпотентен: повторный запуск ничего не ломает.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$SKILL_DIR/.venv"
TOKEN_FILE="$SKILL_DIR/.hf_token"

echo "==> video-analyzer setup"
echo "    SKILL_DIR=$SKILL_DIR"

# 1. Системные зависимости через Homebrew -------------------------------------
if ! command -v brew >/dev/null 2>&1; then
  echo "ОШИБКА: Homebrew не найден. Установи с https://brew.sh и повтори." >&2
  exit 1
fi

for pkg in ffmpeg yt-dlp; do
  if command -v "$pkg" >/dev/null 2>&1; then
    echo "    [ok] $pkg уже установлен"
  else
    echo "    [..] brew install $pkg"
    brew install "$pkg"
  fi
done

# 2. Python venv с whisperx ---------------------------------------------------
# Выбираем совместимый Python: torch поддерживает 3.9–3.12; brew-3.14 слишком новый.
pick_python() {
  for cand in python3.12 python3.11 python3.10 python3.9 /usr/bin/python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      ver="$("$cand" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "")"
      case "$ver" in
        3.9|3.10|3.11|3.12) echo "$cand"; return 0 ;;
      esac
    fi
  done
  return 1
}

if [ ! -d "$VENV" ]; then
  PY="$(pick_python)" || { echo "ОШИБКА: нет Python 3.9–3.12 для torch/whisperx." >&2; exit 1; }
  echo "    [..] создаю venv через $PY ($("$PY" --version 2>&1))"
  "$PY" -m venv "$VENV"
else
  echo "    [ok] venv уже существует"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --quiet --upgrade pip

if python -c "import whisperx" 2>/dev/null; then
  echo "    [ok] whisperx уже установлен в venv"
else
  echo "    [..] pip install whisperx (это надолго: тянет torch)"
  python -m pip install whisperx
fi

# Фикс совместимости whisperx/pyannote с torch>=2.6 (weights_only).
# Кладём sitecustomize.py в site-packages — Python подхватит его при старте.
SP="$(python -c 'import site,sys; print(next(p for p in site.getsitepackages() if p.endswith("site-packages")))' 2>/dev/null || true)"
if [ -n "${SP:-}" ] && [ -d "$SP" ]; then
  cat > "$SP/sitecustomize.py" <<'PYEOF'
# Авто-фикс совместимости whisperx/pyannote с torch>=2.6.
# torch 2.6 сменил дефолт torch.load на weights_only=True, из-за чего падает
# загрузка моделей pyannote (omegaconf ListConfig). Модели берутся из локальной
# доверенной установки, поэтому форсируем weights_only=False.
try:
    import torch
    import torch.serialization as _ts

    _orig_load = _ts.load

    def _patched_load(*args, **kwargs):
        kwargs["weights_only"] = False
        return _orig_load(*args, **kwargs)

    _ts.load = _patched_load
    torch.load = _patched_load

    try:
        from omegaconf.listconfig import ListConfig
        from omegaconf.dictconfig import DictConfig
        from omegaconf.base import ContainerMetadata, Metadata
        _ts.add_safe_globals([ListConfig, DictConfig, ContainerMetadata, Metadata])
    except Exception:
        pass
except Exception:
    pass
PYEOF
  echo "    [ok] sitecustomize.py (torch compat) установлен в $SP"
fi

# 3. Токен HuggingFace для диаризации (опционально) ---------------------------
if [ -f "$TOKEN_FILE" ]; then
  echo "    [ok] HF-токен уже сохранён ($TOKEN_FILE)"
else
  echo ""
  echo "    Диаризация (метки говорящих) требует бесплатного токена HuggingFace."
  echo "    Сначала прими условия моделей (один раз, без оплаты):"
  echo "      https://huggingface.co/pyannote/speaker-diarization-3.1"
  echo "      https://huggingface.co/pyannote/segmentation-3.0"
  echo "    Токен: https://huggingface.co/settings/tokens (тип Read)"
  echo ""
  printf "    Вставь токен hf_... (или Enter, чтобы пропустить диаризацию): "
  read -r -s HF_INPUT
  echo ""
  if [ -n "$HF_INPUT" ]; then
    printf '%s' "$HF_INPUT" > "$TOKEN_FILE"
    chmod 600 "$TOKEN_FILE"
    echo "    [ok] токен сохранён в $TOKEN_FILE (chmod 600)"
  else
    echo "    [--] пропущено — скилл будет работать без меток говорящих"
  fi
fi

echo ""
echo "==> Готово. Проверка версий:"
ffmpeg  -version 2>/dev/null | head -1 || true
yt-dlp  --version 2>/dev/null || true
python  -c "import whisperx; print('whisperx ok')" 2>/dev/null || true
