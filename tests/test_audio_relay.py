"""/audio keeps transcribing when the speech service closes a session while the mic is still on."""

import asyncio
import json
import threading
import time

from fastapi.testclient import TestClient
from websockets.asyncio.server import serve

import hub.main as main
from hub import config


def test_relay_reconnects_when_session_ends_early(monkeypatch):
    sessions: list[int] = []
    ready = threading.Event()
    port_box: dict = {}

    async def handler(ws):
        sessions.append(1)
        json.loads(await ws.recv())
        await ws.send(json.dumps({"sessionId": f"s{len(sessions)}"}))
        frames = 0
        async for message in ws:
            if isinstance(message, bytes):
                frames += 1
                if len(sessions) == 1 and frames == 2:
                    await ws.close()  # the service ends the session while the mic keeps going
                    return
            elif json.loads(message).get("type") == "endStream":
                await ws.close()
                return

    def serve_forever():
        async def run():
            async with serve(handler, "127.0.0.1", 0) as server:
                port_box["port"] = server.sockets[0].getsockname()[1]
                ready.set()
                await asyncio.Future()

        asyncio.run(run())

    threading.Thread(target=serve_forever, daemon=True).start()
    ready.wait(5)
    monkeypatch.setattr(config, "ASR_URL", f"ws://127.0.0.1:{port_box['port']}")
    monkeypatch.setattr(config, "stt_available", lambda: True)
    monkeypatch.setattr(config, "api_key", lambda: "LLM|1|test")

    with TestClient(main.app) as client, client.websocket_connect("/audio") as ws:
        for _ in range(12):
            ws.send_bytes(b"\x00\x00" * 1920)
            time.sleep(0.05)
    assert len(sessions) >= 2
