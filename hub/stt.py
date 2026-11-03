"""Muse Voice Transcribe over the realtime WebSocket (ENDPOINTING mode), per the Meta cookbook.

Audio is raw PCM16 mono at 24 kHz, sent as binary frames. The handshake carries the key in JSON
because browsers can't set WebSocket headers. Events come back as JSON: cumulative `transcript`
partials, and a `speechComplete` with the whole turn once the model hears the speaker stop.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from hub import config

log = logging.getLogger("cueon.stt")

SAMPLE_RATE = 24_000


class TranscribeError(RuntimeError):
    pass


async def transcribe(
    chunks: AsyncIterator[bytes],
    api_key: str,
    keywords: list[str] | None = None,
    mode: str = "ENDPOINTING",
) -> AsyncIterator[dict]:
    """Stream PCM chunks to the ASR endpoint and yield its events until the audio ends."""
    import websockets

    handshake = {
        "mode": mode,
        "authorization": {"accessToken": api_key},
        "audioEncoding": "PCM_24KHZ",
        "model": config.ASR_MODEL,
        "partialMode": "CUMULATIVE",
        "emitAudioProgress": False,
    }
    if keywords:
        handshake["keywords"] = keywords[:50]  # the endpoint takes at most 50

    async with websockets.connect(config.ASR_URL, max_size=None) as ws:
        await ws.send(json.dumps(handshake))
        ack = json.loads(await ws.recv())
        if ack.get("type") == "error":
            raise TranscribeError(ack.get("message", "handshake rejected"))
        log.info("ASR session %s", ack.get("sessionId"))

        async def upload() -> None:
            async for chunk in chunks:
                await ws.send(chunk)
            await ws.send(json.dumps({"type": "endStream"}))

        sender = asyncio.create_task(upload())
        try:
            async for message in ws:
                if isinstance(message, bytes):
                    continue
                event = json.loads(message)
                if event.get("type") == "error":
                    raise TranscribeError(event.get("message", "transcription error"))
                yield event
        finally:
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
