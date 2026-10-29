"""Live Q&A loop: transcript stream → question → answer card → HUD, with per-stage timestamps."""

import logging
import time
import uuid

from hub.bus import HudBus
from hub.fakes import fake_answer, fake_transcribe

log = logging.getLogger("cueon")


class Pipeline:
    def __init__(self, bus: HudBus) -> None:
        self.bus = bus
        self.listening = False
        # card id -> stage timings in ms since the question was complete
        self.timings: dict[str, dict[str, float]] = {}
        self._started: dict[str, float] = {}

    async def toggle_listen(self) -> None:
        self.listening = not self.listening
        await self.bus.show("listening" if self.listening else "idle", partial="")

    async def ask(self, text: str) -> str:
        """Run one spoken question through the loop. Returns the card id."""
        question = text
        async for transcript, final in fake_transcribe(text):
            if final:
                question = transcript
            else:
                await self.bus.show("listening", partial=transcript)

        card_id = uuid.uuid4().hex[:8]
        t0 = time.perf_counter()
        await self.bus.show("thinking", question=question)

        card = await fake_answer(question)
        if card is None:
            await self.bus.show("repeat", partial=question)
            return card_id

        self._started[card_id] = t0
        self.timings[card_id] = {"card_sent": (time.perf_counter() - t0) * 1000}
        await self.bus.show("card", id=card_id, **card.model_dump())
        return card_id

    def mark_rendered(self, card_id: str) -> None:
        t0 = self._started.pop(card_id, None)
        if t0 is None:
            return
        timing = self.timings[card_id]
        timing["rendered"] = (time.perf_counter() - t0) * 1000
        log.info("card %s: sent %.0f ms, rendered %.0f ms", card_id, timing["card_sent"], timing["rendered"])
