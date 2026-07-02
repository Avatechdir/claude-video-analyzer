#!/usr/bin/env python3
"""frame_windows.py — детерминированный отбор реплик-кандидатов вокруг каждого кадра.

Кадры извлекаются на визуальных событиях (смены сцены/UI), речь живёт в транскрипте.
Этот скрипт для каждого кадра отбирает сегменты транскрипта из временно́го окна вокруг
его таймкода и печатает Markdown-«скаффолд». Это ТОЛЬКО арифметика «какой сегмент рядом
с каким кадром» + гарантия привязки по времени — СМЫСЛОВЫЕ границы мыслей и чистку ASR
дальше делает модель, авторя frames_context.md на основе этого скаффолда.

Окно кандидатов (стратегия D): [t_i - LEAD, max(t_{i+1}, t_i + FLOOR)], потолок CAP.
  LEAD  — лид-ин: речь-анонс перед переключением экрана;
  FLOOR — минимум, чтобы кадр не «голодал» при частых сменах сцены;
  CAP   — предохранитель от гигантских окон в длинных статичных кусках.

Usage: frame_windows.py <workdir>
Читает: <workdir>/frames/timestamps.txt, <workdir>/audio.json, <workdir>/analysis.txt
Пишет:  Markdown в stdout.
Env (опц.): CTX_LEAD (5), CTX_FLOOR (8), CTX_CAP (90)
"""
import json
import os
import sys


def fmt(t):
    """Секунды -> MM:SS (или H:MM:SS для длинных)."""
    t = max(0, int(round(t)))
    h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def main():
    if len(sys.argv) < 2:
        print("usage: frame_windows.py <workdir>", file=sys.stderr)
        sys.exit(2)
    work = sys.argv[1]
    lead = float(os.environ.get("CTX_LEAD", 5))
    floor = float(os.environ.get("CTX_FLOOR", 8))
    cap = float(os.environ.get("CTX_CAP", 90))

    ts_path = os.path.join(work, "frames", "timestamps.txt")
    seg_path = os.path.join(work, "audio.json")
    if not os.path.exists(ts_path):
        print(f"ОШИБКА: нет {ts_path}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(seg_path):
        print(f"ОШИБКА: нет {seg_path} (сначала транскрипция)", file=sys.stderr)
        sys.exit(1)

    frames = [float(x) for x in open(ts_path).read().split()]
    segments = json.load(open(seg_path, encoding="utf-8")).get("segments", [])

    # расширение кадров: из analysis.txt (frame_format), иначе по факту в папке
    ext = "jpg"
    an = os.path.join(work, "analysis.txt")
    if os.path.exists(an):
        for line in open(an):
            if line.startswith("frame_format="):
                ext = line.strip().split("=", 1)[1] or "jpg"
    # конец транскрипта — для окна последнего кадра
    end_all = max((s["end"] for s in segments), default=(frames[-1] if frames else 0))

    out = []
    out.append("# Скаффолд контекста кадров")
    out.append("")
    out.append("Для КАЖДОГО кадра ниже даны кадр-картинка и сегменты речи из его "
               "временно́го окна (кандидаты). Задача модели: посмотреть кадр (Read), "
               "склеить сегменты в законченные мысли ПО СМЫСЛУ, вычистить очевидные "
               "ошибки распознавания и записать результат в frames_context.md "
               "(что на экране + контекст речи с таймкодами). Границы мыслей и обрезку "
               "лишнего решает модель — окно здесь намеренно с запасом.")
    out.append("")

    for i, ti in enumerate(frames):
        tnext = frames[i + 1] if i + 1 < len(frames) else end_all
        w_start = ti - lead
        w_end = max(tnext, ti + floor)
        if w_end - w_start > cap:
            w_end = w_start + cap
        cand = [s for s in segments if s["end"] > w_start and s["start"] < w_end]

        out.append(f"## frame_{i + 1:04d} · {fmt(ti)} · frames/frame_{i + 1:04d}.{ext}")
        out.append(f"_окно кандидатов {fmt(max(0, w_start))}–{fmt(w_end)}_")
        if not cand:
            out.append("- _(речи в окне нет — вероятно пауза/интро)_")
        for s in cand:
            spk = s.get("speaker")
            who = f"{spk} " if spk else ""
            out.append(f"- [{fmt(s['start'])}–{fmt(s['end'])}] {who}{s['text']}")
        out.append("")

    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
