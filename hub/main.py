"""Cueon hub: serves the HUD WebSocket and accepts questions.

Until the Meta API key works, questions come in as text via POST /ask and run through fake STT/LLM.
"""

import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from hub.bus import HudBus
from hub.pipeline import Pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

app = FastAPI(title="Cueon hub")
bus = HudBus()
pipeline = Pipeline(bus)


class Ask(BaseModel):
    text: str


@app.post("/ask")
async def ask(body: Ask) -> dict:
    card_id = await pipeline.ask(body.text)
    return {"id": card_id, "timings": pipeline.timings.get(card_id)}


@app.get("/timings")
def timings() -> dict:
    return pipeline.timings


@app.websocket("/hud")
async def hud(ws: WebSocket) -> None:
    await bus.connect(ws)
    try:
        while True:
            message = json.loads(await ws.receive_text())
            if message.get("type") == "rendered":
                pipeline.mark_rendered(message.get("id", ""))
            elif message.get("type") == "toggle_listen":
                await pipeline.toggle_listen()
    except WebSocketDisconnect:
        bus.disconnect(ws)
