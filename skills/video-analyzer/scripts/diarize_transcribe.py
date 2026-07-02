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


def transcribe(audio, model, language, threads, initial_prompt=""):
    """Возвращает (words, native): слова с таймкодами/уверенностью и нативные
    сегменты-фразы whisper (их границы нужны, чтобы в plain-режиме не схлопывать
    транскрипт в один блок). initial_prompt — подсказка-глоссарий (термины,
    имена, жаргон): whisper заметно точнее пишет названия из подсказки."""
    from faster_whisper import WhisperModel
    wm = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads)
    segs, _ = wm.transcribe(audio, language=language, word_timestamps=True, beam_size=5,
                            initial_prompt=initial_prompt or None)
    words = []    # плоский список слов: (start, end, text, probability)
    native = []   # нативные фразы whisper: {start, end, text}
    for s in segs:
        native.append({"start": float(s.start), "end": float(s.end),
                        "text": s.text.strip(), "speaker": None})
        for w in (s.words or []):
            words.append((float(w.start), float(w.end), w.word, float(w.probability)))
    return words, native


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
    for ws, we, wt, _wp in words:
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


def write_words(out_dir, base, words, language):
    """Пословный тайминг — источник истины (для frame_windows.py и будущего редактора
    транскрипции). i — стабильный id слова, prob — уверенность распознавания."""
    os.makedirs(out_dir, exist_ok=True)
    data = {
        "schema_version": 1,
        "audio": base + ".wav",
        "language": language,
        "words": [
            {"i": i, "start": round(s, 3), "end": round(e, 3),
             "word": w, "prob": round(p, 4)}
            for i, (s, e, w, p) in enumerate(words)
        ],
    }
    with open(os.path.join(out_dir, base + ".words.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
    ap.add_argument("--time-offset", type=float, default=0.0,
                    help="прибавить к таймкодам (фокус-режим: старт окна в сек)")
    ap.add_argument("--initial-prompt", default="",
                    help="подсказка whisper: словарь терминов/имён (глоссарий)")
    args = ap.parse_args()

    print(f"[py] транскрипция (faster-whisper {args.model})...", file=sys.stderr)
    words, native = transcribe(args.audio, args.model, args.language, args.threads,
                               args.initial_prompt)
    print(f"[py] слов с таймкодами: {len(words)}, нативных фраз: {len(native)}",
          file=sys.stderr)

    turns = []
    if args.hf_token:
        print("[py] диаризация (pyannote)...", file=sys.stderr)
        turns = diarize(args.audio, args.hf_token)
        n_spk = len({t[2] for t in turns})
        print(f"[py] речевых интервалов: {len(turns)}, говорящих: {n_spk}", file=sys.stderr)
    else:
        print("[py] без диаризации (токен не передан)", file=sys.stderr)

    # С диаризацией — склейка слов по спикеру; без неё — НЕ схлопываем в один блок,
    # а сохраняем нативные фразы whisper (границы предложений/дыханий ~2.5с).
    if turns:
        segments = group_segments(words, turns)
    else:
        segments = native

    if args.time_offset:
        for s in segments:
            s["start"] += args.time_offset
            s["end"] += args.time_offset
        words = [(s + args.time_offset, e + args.time_offset, w, p)
                 for (s, e, w, p) in words]

    base = os.path.splitext(os.path.basename(args.audio))[0]
    write_words(args.out, base, words, args.language)
    write_outputs(args.out, base, segments)
    print(f"[py] готово: {len(segments)} сегментов, {len(words)} слов -> "
          f"{args.out}/{base}.{{txt,srt,json,words.json}}", file=sys.stderr)


if __name__ == "__main__":
    main()
