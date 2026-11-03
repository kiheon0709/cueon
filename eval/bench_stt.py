"""Speech-to-text turn latency: end of speech → speechComplete, with Muse Voice Transcribe.

Streams each WAV (mono 16-bit, 24 kHz) at real time in ENDPOINTING mode and measures from the
moment the last audio frame is sent to the speechComplete event. Needs MODEL_API_KEY.

    uv run python -m eval.bench_stt recordings/*.wav
"""

import asyncio
import os
import statistics
import sys
import time
import wave

from dotenv import load_dotenv

from hub.stt import SAMPLE_RATE, transcribe

FRAME_MS = 80
TRAILING_SILENCE_MS = 1200  # endpointing needs to hear the speaker stop


async def one(path: str, key: str) -> tuple[float | None, str]:
    with wave.open(path) as w:
        if w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit(f"{path}: need mono 16-bit {SAMPLE_RATE} Hz WAV (ffmpeg -i in.m4a -ac 1 -ar 24000 out.wav)")
        audio = w.readframes(w.getnframes())
    audio += b"\x00\x00" * (SAMPLE_RATE * TRAILING_SILENCE_MS // 1000)
    size = SAMPLE_RATE * 2 * FRAME_MS // 1000
    speech_end = len(audio) - SAMPLE_RATE * 2 * TRAILING_SILENCE_MS // 1000
    marks: dict[str, float] = {}

    async def chunks():
        for i in range(0, len(audio), size):
            yield audio[i : i + size]
            if i + size >= speech_end and "speech_end" not in marks:
                marks["speech_end"] = time.perf_counter()
            await asyncio.sleep(FRAME_MS / 1000)

    async for event in transcribe(chunks(), key):
        if event.get("type") == "speechComplete":
            done = time.perf_counter() - marks.get("speech_end", time.perf_counter())
            return done * 1000, event.get("transcript", "")
    return None, ""


async def main(paths: list[str]) -> None:
    load_dotenv()
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise SystemExit("Set MODEL_API_KEY in .env")
    times = []
    for path in paths:
        ms, text = await one(path, key)
        print(f"{ms if ms is not None else float('nan'):7.0f} ms  {path}: {text}")
        if ms is not None:
            times.append(ms)
    if times:
        times.sort()
        p95 = statistics.quantiles(times, n=100, method="inclusive")[94] if len(times) > 1 else times[0]
        print(f"\nend of speech → speechComplete: p50 {statistics.median(times):.0f} ms, p95 {p95:.0f} ms (n={len(times)})")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
