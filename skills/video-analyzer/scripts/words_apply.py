#!/usr/bin/env python3
"""Влить карту правок в edits.json проекта Transcript Editor.

Два режима входа:
  • ЗАМЕНЫ (по умолчанию) — карта {"<id>": "<токен>"} (ослышки B / пунктуация C):
    одно слово вместо одного; пустая строка/null → удаление (out: []).
    `--kind punct` пометит записи (провенанс класса C; B — без kind).
  • MERGE-наложения (`--merges`) — карта уже готовых записей
    {"<id>": {"out":[...],"span_to":N,"kind":"norm"}, "<id2>": {"out":[],"into":N}}
    из normalize_transcript.py --emit-merges (класс A, склейка дефисов).
    Защита от коллизий: если у survivor ИЛИ поглощаемого id уже есть правка —
    ВСЯ группа пропускается (не перетираем ручную работу / ослышки).

Аккуратно СЛИВАЕТ с существующим edits.json:
  • НЕ трогает speakers / segment_speakers;
  • НЕ перетирает уже существующие правки слов (по умолчанию; --overwrite — для замен).
Пишет атомарно (temp + rename), делает .bak.

Использование:
  python words_apply.py <project_dir> <map.json ...> [--overwrite] [--kind punct]
  python words_apply.py <project_dir> merges.json --merges
  cat map.json | python words_apply.py <project_dir> -
"""
import json, sys, os, tempfile

EMPTY = {"schema_version": 2, "words": {}, "speakers": {}, "segment_speakers": {}}

def read_json(p, default):
    try:
        with open(p) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return json.loads(json.dumps(default))

def write_atomic(p, obj):
    d = os.path.dirname(p) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)

def _flag_val(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None

def main():
    argv = sys.argv[1:]
    overwrite = "--overwrite" in argv
    merges = "--merges" in argv
    kind = _flag_val(argv, "--kind")
    skip = {"--overwrite", "--merges"}
    args, i = [], 0
    while i < len(argv):
        if argv[i] == "--kind":
            i += 2; continue
        if argv[i] in skip:
            i += 1; continue
        args.append(argv[i]); i += 1
    if len(args) < 2:
        print("usage: words_apply.py <project_dir> <map.json ...> [--overwrite] [--kind K] [--merges]",
              file=sys.stderr)
        sys.exit(2)
    proj = args[0]
    cmap = {}
    for m in args[1:]:
        raw = sys.stdin.read() if m == "-" else open(m).read()
        cmap.update(json.loads(raw))

    path = os.path.join(proj, "edits.json")
    edits = read_json(path, EMPTY)
    edits.setdefault("schema_version", 2)
    edits.setdefault("words", {})
    words = edits["words"]

    applied = skipped = deleted = 0
    if merges:
        # survivor-записи имеют span_to; поглощённые — into. Группа = survivor + into-члены.
        survivors = {wid: rec for wid, rec in cmap.items() if isinstance(rec, dict) and "span_to" in rec}
        for sid, rec in survivors.items():
            group = [str(sid)] + [str(w) for w, r in cmap.items()
                                  if isinstance(r, dict) and str(r.get("into")) == str(sid)]
            if any(g in words for g in group):     # коллизия с существующей правкой → пропуск
                skipped += 1
                continue
            for g in group:
                words[g] = cmap[g]
            applied += 1
    else:
        for wid, tok in cmap.items():
            wid = str(wid)
            if wid in words and not overwrite:
                skipped += 1
                continue
            if tok is None or (isinstance(tok, str) and tok.strip() == ""):
                words[wid] = {"out": []}
                deleted += 1
            else:
                rec = {"out": [tok]}
                if kind:
                    rec["kind"] = kind
                words[wid] = rec
                applied += 1

    if os.path.exists(path):
        try:
            with open(path + ".bak", "w") as f:
                json.dump(read_json(path, EMPTY), f, ensure_ascii=False, indent=2)
        except OSError:
            pass
    write_atomic(path, edits)
    unit = "склеек" if merges else "правок"
    print(f"[words_apply] {unit}={applied} удалений={deleted} пропущено(коллизии/уже были)={skipped} -> {path}")

if __name__ == "__main__":
    main()
