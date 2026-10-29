"""HUD bus: pushes the current HUD state to every connected glasses/simulator client."""

import json

from fastapi import WebSocket


class HudBus:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.last: dict = {"type": "hud", "state": "idle"}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
        await ws.send_text(json.dumps(self.last))

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def show(self, state: str, **fields) -> None:
        self.last = {"type": "hud", "state": state, **fields}
        text = json.dumps(self.last)
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:
                self.clients.discard(ws)
