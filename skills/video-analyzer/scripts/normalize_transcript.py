#!/usr/bin/env python3
"""Нормализация транскрипта, класс A (механика) — детерминированно, без модели.

Ядро — склейка дефисных клитик, оторванных Whisper: «что -то»→«что-то»,
«во -вторых»→«во-вторых», «по -моему»→«по-моему». Токен сливается с ПРЕДЫДУЩИМ
словом, если начинается с дефиса + БУКВА (`^-[А-Яа-яЁёA-Za-z]`).

Исключения (НЕ сливать): дефис+цифра («-4-4-4…» — галлюцинация ASR); одиночное
тире / «слово - слово» (не матчит правило); граница предложения перед токеном
(предыдущее слово кончается на .?!…); первый токен сегмента (нет предыдущего).

Два режима:
  --emit-merges <project_dir>   → JSON-карта merge-НАЛОЖЕНИЙ для edits.json
                                  (survivor {out,span_to,kind:"norm"} + {into}),
                                  формат как ручной merge редактора; применяет
                                  words_apply.py --merges. Источник НЕ мутируется.
  --text <файл|->               → нормализованная плоская строка (склейка +
                                  схлопывание кратных пробелов + пробел-перед-знаком);
                                  для отчёта/transcript.md.
"""
import json, sys, os, re, datetime

DASH_CLITIC = re.compile(r"^-[А-Яа-яЁёA-Za-z]")   # дефис + буква
SENT_END = ("...", ".", "?", "!", "…", ".»", "?»", "!»")

def _load(d):
    wj = json.load(open(os.path.join(d, "audio.words.json")))
    words = wj["words"] if isinstance(wj, dict) and "words" in wj else wj
    segs = json.load(open(os.path.join(d, "audio.json")))["segments"]
    return words, segs

def _seg_index(words, segs):
    """id слова -> индекс сегмента (границы = start сегментов)."""
    bounds = [s["start"] for s in segs]
    idx = {}
    for w in words:
        si = 0
        for i, b in enumerate(bounds):
            if w["start"] + 1e-6 >= b:
                si = i
            else:
                break
        idx[w["i"]] = si
    return idx

def emit_merges(d):
    words, segs = _load(d)
    seg_of = _seg_index(words, segs)
    out = {}
    n = len(words)
    k = 0
    while k < n:
        w = words[k]
        tok = w["word"].strip()
        # начать группу, если следующий токен — дефис-клитика в том же сегменте
        group = [w]
        j = k + 1
        while j < n:
            nxt = words[j]
            if seg_of[nxt["i"]] != seg_of[w["i"]]:
                break
            if not DASH_CLITIC.match(nxt["word"].strip()):
                break
            # не клеим через границу предложения
            if group[-1]["word"].strip().endswith(SENT_END):
                break
            group.append(nxt)
            j += 1
        if len(group) > 1:
            survivor = group[0]["i"]
            span_to = group[-1]["i"]
            joined = "".join(g["word"].strip() for g in group)
            out[str(survivor)] = {"out": [joined], "span_to": span_to, "kind": "norm",
                                  "at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}
            for g in group[1:]:
                out[str(g["i"])] = {"out": [], "into": survivor}
            k = j
        else:
            k += 1
    return out

def normalize_text(s):
    # склейка «слово -буква» → «слово-буква»
    s = re.sub(r"(\S)\s+(-[А-Яа-яЁёA-Za-z])", r"\1\2", s)
    # пробел перед знаком препинания
    s = re.sub(r"\s+([,.?!…])", r"\1", s)
    # схлопывание кратных пробелов (не трогая переводы строк)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s

def main():
    a = sys.argv[1:]
    if "--emit-merges" in a:
        d = a[a.index("--emit-merges") + 1]
        print(json.dumps(emit_merges(d), ensure_ascii=False, indent=2))
    elif "--text" in a:
        f = a[a.index("--text") + 1]
        raw = sys.stdin.read() if f == "-" else open(f).read()
        sys.stdout.write(normalize_text(raw))
    else:
        print("usage: normalize_transcript.py --emit-merges <project_dir> | --text <file|->",
              file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
