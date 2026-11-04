"""Transcribe audio/video to text with faster-whisper (CPU, Apple Silicon).

Runs entirely locally -- nothing is uploaded. Accepts any container ffmpeg can
read (mp3, m4a, wav, mp4, webm, mov, ...) or, with --url, pulls the audio track
itself via yt-dlp.

    scripts/transcribe.py clip.m4a
    scripts/transcribe.py --url 'https://www.youtube.com/watch?v=zspMXJVbfAY'
    scripts/transcribe.py clip.m4a --model large-v3      # slower, most accurate

Writes <out>/<stem>.txt (flowing text), .srt (timestamped) and .json (segments)
next to each other, so a claim in the text can always be traced to a timecode.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# Whisper conditions on this text, so domain vocabulary that would otherwise be
# mangled ("ATR" -> "80R", "pips" -> "pips/peeps") gets anchored. It is a
# nudge, not a constraint: nothing here is inserted into the output on its own.
TRADING_PROMPT = (
    "Trading strategy walkthrough. Terms: candle, candlestick, wick, body, "
    "opening range, pivot, support, resistance, breakout, entry, stop loss, "
    "take profit, risk reward, R multiple, pips, points, ticks, lot size, "
    "position sizing, drawdown, backtest, timeframe, 15-minute chart, session, "
    "London open, New York open, forex, gold, XAUUSD, NAS100, indices, "
    "long, short, buy stop, sell stop, ATR, moving average, EMA, liquidity."
)


def fetch_audio(url: str, dest_dir: Path) -> Path:
    """Download the best audio-only stream for ``url`` via yt-dlp."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    ytdlp = Path(sys.argv[0]).resolve().parent.parent / ".venv-whisper/bin/yt-dlp"
    cmd = [
        str(ytdlp) if ytdlp.exists() else "yt-dlp",
        "-x", "--audio-format", "m4a", "--audio-quality", "0",
        "-o", str(dest_dir / "%(id)s.%(ext)s"), "--no-playlist", url,
    ]
    print(f"[yt-dlp] {url}", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        # The failure is almost always network/bot-check, not a bad URL, and the
        # useful next step is for the human to download it themselves.
        sys.exit(f"yt-dlp failed:\n{r.stderr.strip()[-1500:]}\n\n"
                 "Download the audio manually and pass the file path instead.")
    files = sorted(dest_dir.glob("*.m4a"), key=lambda p: p.stat().st_mtime)
    if not files:
        sys.exit("yt-dlp reported success but produced no .m4a")
    return files[-1]


def ts(seconds: float, sep: str = ",") -> str:
    """Seconds -> SRT/VTT timestamp."""
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("audio", nargs="?", help="path to an audio or video file")
    src.add_argument("--url", help="fetch the audio with yt-dlp first")
    p.add_argument("--model", default="distil-large-v3",
                   help="distil-large-v3 (fast, English) | large-v3 (most accurate) "
                        "| medium | small")
    p.add_argument("--language", default="en", help="force a language, or 'auto'")
    p.add_argument("--out", default="output/transcripts")
    p.add_argument("--beam", type=int, default=5)
    p.add_argument("--threads", type=int, default=0, help="0 = all cores")
    p.add_argument("--no-vad", action="store_true",
                   help="disable voice-activity filtering (keep dead air)")
    p.add_argument("--prompt", default=TRADING_PROMPT,
                   help="vocabulary hint; pass '' to disable")
    a = p.parse_args()

    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = fetch_audio(a.url, out_dir / "audio") if a.url else Path(a.audio)
    if not path.exists():
        sys.exit(f"no such file: {path}")

    from faster_whisper import WhisperModel

    print(f"[model] {a.model} (int8, cpu)", flush=True)
    t0 = time.time()
    model = WhisperModel(a.model, device="cpu", compute_type="int8",
                         cpu_threads=a.threads)
    print(f"[model] loaded in {time.time() - t0:.1f}s", flush=True)

    print(f"[audio] {path}  ({path.stat().st_size / 1e6:.1f} MB)", flush=True)
    t0 = time.time()
    segments, info = model.transcribe(
        str(path),
        language=None if a.language == "auto" else a.language,
        beam_size=a.beam,
        vad_filter=not a.no_vad,
        # Whisper loops on music stings and silence; these are the standard
        # guards against a repeated phrase filling minutes of output.
        condition_on_previous_text=False,
        no_speech_threshold=0.6,
        compression_ratio_threshold=2.4,
        initial_prompt=a.prompt or None,
    )
    print(f"[audio] {info.duration / 60:.1f} min, language={info.language} "
          f"({info.language_probability:.2f})\n", flush=True)

    rows = []
    for seg in segments:  # generator: work happens as we iterate
        text = seg.text.strip()
        rows.append({"start": seg.start, "end": seg.end, "text": text})
        print(f"[{ts(seg.start, '.')[:-4]}] {text}", flush=True)

    elapsed = time.time() - t0
    stem = path.stem
    (out_dir / f"{stem}.txt").write_text(
        "\n".join(r["text"] for r in rows) + "\n", encoding="utf-8")
    (out_dir / f"{stem}.srt").write_text(
        "".join(f"{i}\n{ts(r['start'])} --> {ts(r['end'])}\n{r['text']}\n\n"
                for i, r in enumerate(rows, 1)), encoding="utf-8")
    (out_dir / f"{stem}.json").write_text(
        json.dumps({"source": str(path), "model": a.model,
                    "duration_sec": info.duration, "language": info.language,
                    "segments": rows}, indent=2), encoding="utf-8")

    speed = info.duration / elapsed if elapsed else 0
    print(f"\n[done] {len(rows)} segments in {elapsed / 60:.1f} min "
          f"({speed:.1f}x realtime)")
    print(f"[done] {out_dir}/{stem}.{{txt,srt,json}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
