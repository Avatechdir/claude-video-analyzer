#!/usr/bin/env python3
"""put_layers.py — залить слои понимания в проект Transcript Editor.

Слои («Смысл» и «Саммари») генерирует МОДЕЛЬ (это синтез, не выход пайплайна);
этот скрипт лишь кладёт готовый JSON в проект — на сервер (PUT) или прямо в файлы.

Схемы (валидируются мягко):
  semantic  {"schema_version":1,"chunks":[{"id","start","end","speaker","text"}]}
  summary   {"schema_version":1,"format":"call|demo|interview|custom",
             "blocks":[{"kind":"about|section|key_points|action_items","title",
                        "body"?|"items"?}]}

Usage:
  # прямо в файлы проекта (сервер не нужен):
  python put_layers.py <project_dir> --semantic sem.json --summary sum.json
  # или на поднятый сервер:
  python put_layers.py <project_dir> --semantic sem.json --summary sum.json \
      --server http://localhost:8787
Любой из --semantic/--summary можно опустить. Только stdlib.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _put(server, slug, sub, body):
    # slug может содержать не-ASCII (кириллица) — percent-кодируем путь, иначе
    # urllib падает на request.encode('ascii').
    url = "%s/api/projects/%s/%s" % (server.rstrip("/"), urllib.parse.quote(slug), sub)
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PUT",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))


def _write_atomic(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
                   encoding="utf-8")
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser(description="Залить semantic.json/summary.json в проект редактора")
    ap.add_argument("project_dir", help="каталог проекта (projects/<slug>)")
    ap.add_argument("--semantic", help="JSON со слоем «Смысл» ({chunks:[...]})")
    ap.add_argument("--summary", help="JSON со слоем «Саммари» ({format,blocks})")
    ap.add_argument("--server", help="URL сервера (например http://localhost:8787); иначе пишем в файлы")
    args = ap.parse_args()

    proj = Path(args.project_dir).resolve()
    if not (proj / "project.json").exists():
        sys.exit("не похоже на проект (нет project.json): %s" % proj)
    slug = proj.name
    if not args.semantic and not args.summary:
        sys.exit("нечего заливать: задай --semantic и/или --summary")

    if args.semantic:
        sem = _load(args.semantic)
        chunks = sem.get("chunks", sem if isinstance(sem, list) else [])
        n = len(chunks)
        if args.server:
            _put(args.server, slug, "meaning", {"chunks": chunks})
        else:
            chunks = sorted(chunks, key=lambda c: c.get("start", 0))
            _write_atomic(proj / "semantic.json", {"schema_version": 1, "chunks": chunks})
        print("[layers] Смысл: %d кусков → %s" % (n, "сервер" if args.server else "semantic.json"))

    if args.summary:
        sm = _load(args.summary)
        fmt = sm.get("format", "custom")
        blocks = sm.get("blocks", [])
        if args.server:
            _put(args.server, slug, "summary", {"format": fmt, "blocks": blocks})
        else:
            _write_atomic(proj / "summary.json",
                          {"schema_version": 1, "format": fmt, "blocks": blocks})
        print("[layers] Саммари: format=%s, блоков=%d → %s"
              % (fmt, len(blocks), "сервер" if args.server else "summary.json"))


if __name__ == "__main__":
    main()
