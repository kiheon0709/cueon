"""Stand-in for Muse Voice Transcribe so the pipeline runs from typed text without an API key.

It follows the realtime ENDPOINTING shape: cumulative partial transcripts, then speechComplete.
"""

import asyncio
from collections.abc import AsyncIterator


async def fake_transcribe(text: str, word_ms: int = 80) -> AsyncIterator[dict]:
    words = text.split()
    for i in range(1, len(words) + 1):
        await asyncio.sleep(word_ms / 1000)
        yield {"type": "transcript", "transcript": " ".join(words[:i]), "final": False}
    yield {"type": "transcript", "transcript": text, "final": True}
    yield {"type": "speechComplete", "transcript": text, "turnId": 0}
