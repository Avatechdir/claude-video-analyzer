#!/usr/bin/env python3
"""contact_sheets.py — собирает контактные листы (montage) из дедуплицированных кадров.

Токен-экономия: субагент-скринер читает ОДИН лист (~30 пронумерованных тамбнейлов) вместо
30 отдельных картинок. Номера рисуем на кадрах, чтобы скринер ссылался на них однозначно;
дубли видны бок о бок → отбор точнее.

Usage: contact_sheets.py <workdir>
Читает: <workdir>/_kept.tsv (из dedup_frames.py), кадры в <workdir>/frames/
Пишет:  <workdir>/_sheet_01.png ... и <workdir>/_sheet_index.tsv
        (столбцы: idx  frame_file  timestamp_sec  sheet_file)
Env: CONTACT_COLS (5), CONTACT_ROWS (6) → кадров/лист; THUMB_W (360)
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont


def load_font(size):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
              "/Library/Fonts/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def fmt(t):
    t = int(round(t)); h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def main():
    if len(sys.argv) < 2:
        print("usage: contact_sheets.py <workdir>", file=sys.stderr); sys.exit(2)
    work = sys.argv[1]
    cols = int(os.environ.get("CONTACT_COLS", 5))
    rows = int(os.environ.get("CONTACT_ROWS", 6))
    tw = int(os.environ.get("THUMB_W", 360))
    th = int(tw * 9 / 16)
    per = cols * rows
    fdir = os.path.join(work, "frames")

    kept_path = os.path.join(work, "_kept.tsv")
    if not os.path.exists(kept_path):
        print(f"ОШИБКА: нет {kept_path} (сначала dedup_frames.py)", file=sys.stderr); sys.exit(1)
    items = []
    for line in open(kept_path):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 2:
            items.append((parts[0], float(parts[1])))
    if not items:
        print("ОШИБКА: _kept.tsv пуст", file=sys.stderr); sys.exit(1)

    font = load_font(26)
    small = load_font(20)
    idx_rows = []
    sheets = []
    nsheets = (len(items) + per - 1) // per
    for sh in range(nsheets):
        chunk = items[sh * per:(sh + 1) * per]
        canvas = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
        draw = ImageDraw.Draw(canvas)
        for j, (f, t) in enumerate(chunk):
            gidx = sh * per + j + 1                       # глобальный номер (1-based)
            r, c = j // cols, j % cols
            x, y = c * tw, r * th
            try:
                im = Image.open(os.path.join(fdir, f)).convert("RGB").resize((tw, th))
                canvas.paste(im, (x, y))
            except Exception:
                pass
            # плашка с номером (крупно) + таймкод
            label = str(gidx)
            tb = draw.textbbox((0, 0), label, font=font)
            lw, lh = tb[2] - tb[0], tb[3] - tb[1]
            draw.rectangle([x, y, x + lw + 16, y + lh + 14], fill=(0, 0, 0))
            draw.text((x + 8, y + 4), label, fill=(0, 255, 150), font=font)
            tc = fmt(t)
            draw.text((x + lw + 24, y + 6), tc, fill=(200, 200, 200), font=small)
            idx_rows.append((gidx, f, t, f"_sheet_{sh + 1:02d}.png"))
        sheet_file = os.path.join(work, f"_sheet_{sh + 1:02d}.png")
        canvas.save(sheet_file)
        sheets.append(sheet_file)

    with open(os.path.join(work, "_sheet_index.tsv"), "w") as out:
        out.write("idx\tframe_file\ttimestamp_sec\tsheet_file\n")
        for gidx, f, t, sf in idx_rows:
            out.write(f"{gidx}\t{f}\t{t:.3f}\t{os.path.basename(sf)}\n")

    print(f"[sheets] кадров={len(items)} листов={nsheets} "
          f"(сетка {cols}x{rows}) -> {', '.join(os.path.basename(s) for s in sheets)}",
          file=sys.stderr)
    for s in sheets:
        print(s)


if __name__ == "__main__":
    main()
