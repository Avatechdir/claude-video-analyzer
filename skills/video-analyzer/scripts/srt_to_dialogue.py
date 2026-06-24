#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""srt_to_dialogue.py — превратить размеченный audio.srt ([SPEAKER_xx] ...) в ЧЕРНОВИК
диалога: склеивает подряд идущие реплики одного спикера в реплики-абзацы и печатает
готовый markdown-блок диалога для вставки в отчёт.

Это только СТАРТОВАЯ заготовка: метки SPEAKER_xx модель потом сводит к реальным людям
(по смыслу + по роду глаголов) и проставляет имена через [Имя]{.p}/{.v}/{.k}.

Usage: python srt_to_dialogue.py <audio.srt> [--gap 1.2]
  --gap  макс. пауза (сек) внутри одной реплики; больше — новая реплика того же спикера
"""
import sys, re, argparse

def parse_srt(path):
    cues = []
    block = []
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.strip() == "":
            if block: cues.append(block); block = []
        else:
            block.append(line)
    if block: cues.append(block)
    out = []
    for b in cues:
        ts = next((l for l in b if "-->" in l), None)
        if not ts: continue
        txt_lines = [l for l in b if "-->" not in l and not re.fullmatch(r"\d+", l.strip())]
        text = " ".join(txt_lines).strip()
        m = re.match(r"\[(SPEAKER_\d+)\]\s*(.*)", text)
        spk = m.group(1) if m else "SPEAKER_??"
        text = m.group(2) if m else text
        start = ts.split("-->")[0].strip().replace(",", ".")
        end = ts.split("-->")[1].strip().replace(",", ".")
        out.append((to_sec(start), to_sec(end), spk, text))
    return out

def to_sec(t):
    h, m, s = t.split(":")
    return int(h)*3600 + int(m)*60 + float(s)

def fmt(sec):
    m = int(sec // 60); s = int(sec % 60)
    return f"{m:02d}:{s:02d}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srt")
    ap.add_argument("--gap", type=float, default=1.2)
    a = ap.parse_args()
    cues = parse_srt(a.srt)
    turns = []
    for st, en, spk, txt in cues:
        if not txt: continue
        if turns and turns[-1][2] == spk and st - turns[-1][1] <= a.gap:
            turns[-1] = (turns[-1][0], en, spk, (turns[-1][3] + " " + txt).strip())
        else:
            turns.append((st, en, spk, txt))
    speakers = sorted({t[2] for t in turns})
    print(f"<!-- ЧЕРНОВИК ДИАЛОГА. Найдено спикеров: {len(speakers)} ({', '.join(speakers)}).")
    print("     Сведи метки SPEAKER_xx к реальным людям и замени на [Имя]{.p|.v|.k}.")
    print("     Если людей в комнате на одном микрофоне несколько — их часто не разделить;")
    print("     честно помечай неуверенные как одного «коллегу». -->")
    print()
    print("::: dialogue")
    print("| Кто | Реплика |")
    print("|-----|---------|")
    for st, en, spk, txt in turns:
        cls = {"SPEAKER_00":"k","SPEAKER_01":"v","SPEAKER_02":"p"}.get(spk, "k")
        print(f"| [{spk} {fmt(st)}]{{.{cls}}} | {txt} |")
    print(":::")

if __name__ == "__main__":
    main()
