#!/usr/bin/env python3
"""Выгрузка слов транскрипта для пословной правки ослышек (слой 1).

Читает audio.words.json + audio.json (сегменты со спикерами) из каталога
разбора ($WORK) ИЛИ проекта Transcript Editor и печатает по каждому сегменту:
  §<seg> t=MM:SS <speaker>
  raw: <дословный текст сегмента>
  w: <id>=<token> <id>=<token> ...
Плюс помечает «*» слова с низкой уверенностью (prob < LOW, по умолч. 0.5),
чтобы модель-корректор в первую очередь смотрела на них.

Модель по этой выгрузке возвращает КАРТУ правок {"<id>": "<исправленный токен>"}
ТОЛЬКО для явных ослышек (не сглаживание!) — её потом применяет words_apply.py.

Использование:
  python words_emit.py <dir> [--low 0.5]
"""
import json, sys, os

def load(d):
    wj = json.load(open(os.path.join(d, "audio.words.json")))
    words = wj["words"] if isinstance(wj, dict) and "words" in wj else wj
    segs = json.load(open(os.path.join(d, "audio.json")))["segments"]
    return words, segs

def mmss(t):
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"

def main():
    if len(sys.argv) < 2:
        print("usage: words_emit.py <dir> [--low 0.5]", file=sys.stderr); sys.exit(2)
    d = sys.argv[1]
    low = 0.5
    if "--low" in sys.argv:
        low = float(sys.argv[sys.argv.index("--low") + 1])
    words, segs = load(d)
    # слова принадлежат сегменту, пока не начался следующий (границы = start слов)
    bounds = [s["start"] for s in segs]
    def seg_of(t):
        lo, hi = 0, len(bounds) - 1
        idx = 0
        for i, b in enumerate(bounds):
            if t + 1e-6 >= b:
                idx = i
            else:
                break
        return idx
    buckets = [[] for _ in segs]
    for w in words:
        buckets[seg_of(w["start"])].append(w)
    for si, (seg, ws) in enumerate(zip(segs, buckets)):
        if not ws:
            continue
        sp = seg.get("speaker", "")
        print(f"§{si} t={mmss(seg['start'])} {sp}")
        print("raw: " + seg.get("text", "").strip())
        toks = []
        for w in ws:
            star = "*" if (w.get("prob") is not None and w["prob"] < low) else ""
            toks.append(f'{w["i"]}={w["word"].strip()}{star}')
        print("w: " + " ".join(toks))
        print()

if __name__ == "__main__":
    main()
