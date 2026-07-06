#!/usr/bin/env python3
"""report_to_semantic.py — БЭКФИЛЛ: импорт моих реконструкций (слой 2) из report.md
в semantic.json проекта редактора.

Для УЖЕ разобранных проектов, чьи реконструкции лежат прозой в отчёте (до появления
semantic.json). Для НОВЫХ видео слой-2-проход скилла пишет semantic.json напрямую —
этот скрипт им не нужен.

Что делает: парсит строки диалога отчёта `| [Имя]{.cls} | `[MM:SS]` текст |`, каждую
сопоставляет с турном транскрипта по таймкоду (турн = непрерывный ход одного спикера),
берёт оттуда точные start/end и speaker_id, а text — мою реконструкцию. Пишет semantic.json.

Usage: python report_to_semantic.py <report.md> <project_dir> <transcript_editor_server_dir>
"""
import sys, os, re, argparse

ROW = re.compile(r"^\|\s*\[([^\]]+)\]\{\.\w+\}\s*\|\s*(.+?)\s*\|\s*$")
TC = re.compile(r"\[(\d+):(\d+)\]")

def parse_report(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        m = ROW.match(line.rstrip("\n"))
        if not m:
            continue
        name, cell = m.group(1), m.group(2)
        tc = TC.search(cell)
        if not tc:
            continue
        start = int(tc.group(1)) * 60 + int(tc.group(2))
        text = TC.sub("", cell, count=1)          # убрать `[MM:SS]`
        text = text.replace("`", "").strip()
        rows.append({"name": name, "start": start, "text": text})
    return rows

def build_turns(server_dir, slug):
    sys.path.insert(0, server_dir)
    import storage, merge
    proj = storage.Project(slug)
    tr = merge.build_transcript(proj, storage.global_glossary())
    turns = []
    for seg in tr["segments"]:
        if seg.get("hidden") or not seg["words"]:
            continue
        sp, st, en = seg.get("speaker_id"), seg.get("start"), seg.get("end")
        if turns and turns[-1]["speaker"] == sp:
            turns[-1]["end"] = en
        else:
            turns.append({"speaker": sp, "start": st, "end": en})
    return proj, turns

def nearest_turn(turns, t):
    return min(turns, key=lambda x: abs((x["start"] or 0) - t))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report"); ap.add_argument("project_dir"); ap.add_argument("server_dir")
    a = ap.parse_args()
    slug = os.path.basename(a.project_dir.rstrip("/"))
    rows = parse_report(a.report)
    proj, turns = build_turns(a.server_dir, slug)
    chunks = []
    for i, r in enumerate(rows, 1):
        turn = nearest_turn(turns, r["start"])
        chunks.append({"id": "m_%04d" % i,
                       "start": turn["start"], "end": turn["end"],
                       "speaker": turn["speaker"], "text": r["text"]})
    proj.save_meaning({"schema_version": 1, "chunks": chunks})
    print(f"[report_to_semantic] реконструкций импортировано: {len(chunks)} -> {proj.dir}/semantic.json")

if __name__ == "__main__":
    main()
