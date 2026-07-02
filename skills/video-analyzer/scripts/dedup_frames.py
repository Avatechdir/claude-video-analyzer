#!/usr/bin/env python3
"""dedup_frames.py — дешёвый (CPU, без модели) дедуп кадров по перцептив-сигнатуре.

Схлопывает near-identical кадры (повторы говорящей головы, почти одинаковые кадры одного
экрана), чтобы субагент-скринер потом читал меньше тамбнейлов. НЕ судит ценность — только
убирает уверенные дубли; спорное ОСТАВЛЯЕТ (перекос в охват), тонкое различит скринер/модель.

Сигнатура: кадр → grayscale → 16x16 → вектор 0..255. Расстояние = среднее модульное отклонение.
Жадно в порядке времени: кадр дубль, если его min-расстояние до уже оставленных < DEDUP_THRESH.

Usage: dedup_frames.py <workdir>
Читает: <workdir>/frames/frame_*.<ext>, <workdir>/frames/timestamps.txt, <workdir>/analysis.txt
Пишет:  <workdir>/_kept.tsv  (строки: frame_file<TAB>timestamp_sec)
Env: DEDUP_THRESH (по умолч. 8.0; меньше = агрессивнее режет; консервативно держим низким)
"""
import os
import sys
import numpy as np
from PIL import Image

GRID = 16  # сторона сигнатуры


def sig(path):
    im = Image.open(path).convert("L").resize((GRID, GRID))
    return np.asarray(im, dtype=np.float32).ravel()


def main():
    if len(sys.argv) < 2:
        print("usage: dedup_frames.py <workdir>", file=sys.stderr); sys.exit(2)
    work = sys.argv[1]
    thresh = float(os.environ.get("DEDUP_THRESH", 8.0))
    fdir = os.path.join(work, "frames")
    ts_path = os.path.join(fdir, "timestamps.txt")
    if not os.path.exists(ts_path):
        print(f"ОШИБКА: нет {ts_path}", file=sys.stderr); sys.exit(1)

    ext = "jpg"
    an = os.path.join(work, "analysis.txt")
    if os.path.exists(an):
        for line in open(an):
            if line.startswith("frame_format="):
                ext = line.strip().split("=", 1)[1] or "jpg"

    times = [float(x) for x in open(ts_path).read().split()]
    kept_sigs = []          # сигнатуры оставленных
    kept = []               # (frame_file, timestamp)
    dropped = 0
    for i, t in enumerate(times, 1):
        f = f"frame_{i:04d}.{ext}"
        p = os.path.join(fdir, f)
        if not os.path.exists(p):
            continue
        s = sig(p)
        dup = False
        for ks in kept_sigs:
            if float(np.abs(s - ks).mean()) < thresh:
                dup = True; break
        if dup:
            dropped += 1
        else:
            kept_sigs.append(s); kept.append((f, t))

    with open(os.path.join(work, "_kept.tsv"), "w") as out:
        for f, t in kept:
            out.write(f"{f}\t{t:.3f}\n")
    print(f"[dedup] всего={len(times)} оставлено={len(kept)} дублей={dropped} "
          f"(порог={thresh}) -> {work}/_kept.tsv", file=sys.stderr)


if __name__ == "__main__":
    main()
