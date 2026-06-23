#!/usr/bin/env python3
"""Транскрипция (faster-whisper) + опциональная диаризация (pyannote).

Минует медленное wav2vec2-выравнивание whisperx: пословные таймкоды берём прямо
из faster-whisper (word_timestamps=True), а спикеров назначаем по перекрытию слов
с речевыми интервалами pyannote. На CPU это в десятки раз быстрее whisperx --diarize.

Usage:
  diarize_transcribe.py --audio A.wav --out DIR [--model large-v3-turbo]
                        [--language ru] [--threads 4] [--hf-token TOKEN]
Без --hf-token диаризация пропускается (просто транскрипт).
Пишет в DIR: <base>.txt, <base>.srt, <base>.json
"""
import argparse
import json
import os
import sys


def fmt_ts(t: float) -> str:
    """Секунды -> SRT-таймкод HH:MM:SS,mmm."""
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcribe(audio, model, language, threads):
    from faster_whisper import WhisperModel
    wm = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads)
    segs, _ = wm.transcribe(audio, language=language, word_timestamps=True, beam_size=5)
    words = []   # плоский список слов: (start, end, text)
    for s in segs:
        for w in (s.words or []):
            words.append((float(w.start), float(w.end), w.word))
    return words


def diarize(audio, token):
    """Возвращает список речевых интервалов: (start, end, speaker)."""
    from pyannote.audio import Pipeline
    pipe = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", use_auth_token=token
    )
    annotation = pipe(audio)
    turns = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        turns.append((float(turn.start), float(turn.end), speaker))
    turns.sort(key=lambda x: x[0])
    return turns


def speaker_for(w_start, w_end, turns):
    """Спикер с максимальным перекрытием со словом; иначе ближайший по времени."""
    best, best_ov = None, 0.0
    for ts, te, sp in turns:
        ov = min(w_end, te) - max(w_start, ts)
        if ov > best_ov:
            best_ov, best = ov, sp
    if best is not None:
        return best
    # перекрытий нет — берём ближайший интервал
    mid = (w_start + w_end) / 2
    nearest, nd = None, float("inf")
    for ts, te, sp in turns:
        d = 0 if ts <= mid <= te else min(abs(mid - ts), abs(mid - te))
        if d < nd:
            nd, nearest = d, sp
    return nearest


def group_segments(words, turns):
    """Группируем подряд идущие слова одного спикера в сегменты."""
    segments = []
    cur = None
    for ws, we, wt in words:
        sp = speaker_for(ws, we, turns) if turns else None
        if cur and cur["speaker"] == sp:
            cur["end"] = we
            cur["text"] += wt
        else:
            if cur:
                segments.append(cur)
            cur = {"start": ws, "end": we, "speaker": sp, "text": wt}
    if cur:
        segments.append(cur)
    for s in segments:
        s["text"] = s["text"].strip()
    return segments


def write_outputs(out_dir, base, segments):
    os.makedirs(out_dir, exist_ok=True)
    # JSON
    with open(os.path.join(out_dir, base + ".json"), "w", encoding="utf-8") as f:
        json.dump({"segments": segments}, f, ensure_ascii=False, indent=2)
    # TXT (с метками говорящих, если есть)
    with open(os.path.join(out_dir, base + ".txt"), "w", encoding="utf-8") as f:
        for s in segments:
            prefix = (s["speaker"] + ": ") if s.get("speaker") else ""
            f.write(prefix + s["text"] + "\n")
    # SRT
    with open(os.path.join(out_dir, base + ".srt"), "w", encoding="utf-8") as f:
        for i, s in enumerate(segments, 1):
            prefix = ("[" + s["speaker"] + "] ") if s.get("speaker") else ""
            f.write(f"{i}\n{fmt_ts(s['start'])} --> {fmt_ts(s['end'])}\n"
                    f"{prefix}{s['text']}\n\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="medium")
    ap.add_argument("--language", default="ru")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--hf-token", default="")
    args = ap.parse_args()

    print(f"[py] транскрипция (faster-whisper {args.model})...", file=sys.stderr)
    words = transcribe(args.audio, args.model, args.language, args.threads)
    print(f"[py] слов с таймкодами: {len(words)}", file=sys.stderr)

    turns = []
    if args.hf_token:
        print("[py] диаризация (pyannote)...", file=sys.stderr)
        turns = diarize(args.audio, args.hf_token)
        n_spk = len({t[2] for t in turns})
        print(f"[py] речевых интервалов: {len(turns)}, говорящих: {n_spk}", file=sys.stderr)
    else:
        print("[py] без диаризации (токен не передан)", file=sys.stderr)

    segments = group_segments(words, turns)
    base = os.path.splitext(os.path.basename(args.audio))[0]
    write_outputs(args.out, base, segments)
    print(f"[py] готово: {len(segments)} сегментов -> {args.out}/{base}.{{txt,srt,json}}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
