#!/usr/bin/env python3
"""Влить карту пословных правок ослышек в edits.json проекта Transcript Editor.

Вход — JSON-карта {"<id слова>": "<исправленный токен>"} (слой 1: ослышки,
одно слово вместо одного). Пустая строка или null → удаление слова (out: []).

Аккуратно СЛИВАЕТ с существующим edits.json:
  • НЕ трогает speakers / segment_speakers;
  • НЕ перетирает уже существующие правки слов, сделанные пользователем
    (по умолчанию; --overwrite чтобы всё же перезаписать).
Пишет атомарно (temp + rename), делает .bak.

Использование:
  python words_apply.py <project_dir> <map.json> [--overwrite]
  cat map.json | python words_apply.py <project_dir> - [--overwrite]
Карт можно передать несколько: ... <map1.json> <map2.json> ...
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

def main():
    args = [a for a in sys.argv[1:] if a != "--overwrite"]
    overwrite = "--overwrite" in sys.argv
    if len(args) < 2:
        print("usage: words_apply.py <project_dir> <map.json ...> [--overwrite]", file=sys.stderr)
        sys.exit(2)
    proj = args[0]
    maps = args[1:]
    # собрать входную карту
    cmap = {}
    for m in maps:
        raw = sys.stdin.read() if m == "-" else open(m).read()
        cmap.update(json.loads(raw))

    path = os.path.join(proj, "edits.json")
    edits = read_json(path, EMPTY)
    edits.setdefault("schema_version", 2)
    edits.setdefault("words", {})
    words = edits["words"]

    applied = skipped = deleted = 0
    for wid, tok in cmap.items():
        wid = str(wid)
        if wid in words and not overwrite:
            skipped += 1
            continue
        if tok is None or (isinstance(tok, str) and tok.strip() == ""):
            words[wid] = {"out": []}
            deleted += 1
        else:
            words[wid] = {"out": [tok]}
            applied += 1

    if os.path.exists(path):
        try:
            with open(path + ".bak", "w") as f:
                json.dump(read_json(path, EMPTY), f, ensure_ascii=False, indent=2)
        except OSError:
            pass
    write_atomic(path, edits)
    print(f"[words_apply] правок={applied} удалений={deleted} пропущено(уже были)={skipped} -> {path}")

if __name__ == "__main__":
    main()
