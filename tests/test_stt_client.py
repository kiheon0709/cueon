"""The real Voice Transcribe client against a local fake ASR WebSocket (no key, no network)."""

import asyncio
import json

from websockets.asyncio.server import serve

from hub import config, stt
from hub.workspace import Workspace


def test_transcribe_handshake_audio_and_events(monkeypatch):
    seen: dict = {"audio": 0}

    async def handler(ws):
        seen["handshake"] = json.loads(await ws.recv())
        await ws.send(json.dumps({"sessionId": "s1"}))
        async for message in ws:
            if isinstance(message, bytes):
                seen["audio"] += len(message)
                if seen["audio"] == 3840:  # two 80 ms frames: send a partial
                    await ws.send(json.dumps({"type": "transcript", "transcript": "How fast", "final": False, "audioProcessedMs": 160}))
            elif json.loads(message).get("type") == "endStream":
                await ws.send(json.dumps({"type": "transcript", "transcript": "How fast is it?", "final": True, "audioProcessedMs": 240}))
                await ws.send(json.dumps({"type": "speechComplete", "transcript": "How fast is it?", "turnId": 1, "audioProcessedMs": 240}))
                await ws.close()

    async def run():
        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            monkeypatch.setattr(config, "ASR_URL", f"ws://127.0.0.1:{port}")

            async def chunks():
                for _ in range(3):
                    yield b"\x00\x00" * 960

            return [e async for e in stt.transcribe(chunks(), "LLM|1|test", keywords=["Cueon", "Spark"])]

    events = asyncio.run(run())
    assert [e["type"] for e in events] == ["transcript", "transcript", "speechComplete"]
    assert events[-1]["transcript"] == "How fast is it?"
    handshake = seen["handshake"]
    assert handshake["authorization"] == {"accessToken": "LLM|1|test"}
    assert handshake["mode"] == "ENDPOINTING" and handshake["audioEncoding"] == "PCM_24KHZ"
    assert handshake["model"] == "muse-voice-transcribe-1.0" and handshake["keywords"] == ["Cueon", "Spark"]
    assert seen["audio"] == 3 * 1920


def test_keywords_fit_the_speech_service():
    workspace = Workspace(stt_terms=["Muse Voice Transcribe — DECK p.1", "Academy of Management Journal — RESEARCH p.5", "Cueon"])
    assert workspace.keywords() == ["Muse Voice Transcribe", "Academy of Management Journal", "Cueon"]
    workspace = Workspace(stt_terms=["a term much longer than the thirty characters allowed"])
    assert workspace.keywords() == []
