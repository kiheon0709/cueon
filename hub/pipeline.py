"""Live loop: transcript events → (Q&A) card or (presentation) position and missed points → HUD.

Q&A has two paths. The fast path matches the question against the card bank locally and shows the
prepared card unchanged. When no card is close enough, the live path streams a card from Spark
with all of the material in the cached prefix; the lead goes to the lens as soon as its line is
done, and the card is marked as written on the spot. Every question is logged with its path and
stage timings, which is where the hit rate and p50/p95 numbers come from.
"""

import json
import logging
import statistics
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

from hub import cardtext
from hub.bus import HudBus
from hub.models import Model
from hub.present import Tracker
from hub.verify import check_card
from hub.workspace import Workspace

log = logging.getLogger("cueon")

Mode = Literal["qa", "present"]


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1]


class Pipeline:
    def __init__(self, bus: HudBus, model: Model, workspace: Workspace, log_path: Path | None = None) -> None:
        self.bus = bus
        self.model = model
        self.ws = workspace
        self.mode: Mode = "qa"
        self.listening = False
        self.last_shown: str | None = None  # bank entry id of the card on the lens
        self.tracker: Tracker | None = None
        self.log_path = log_path
        # question id -> record (question, path, score, timings in ms since the question was complete)
        self.records: dict[str, dict] = {}
        self._started: dict[str, float] = {}

    # --- modes ---------------------------------------------------------------------------

    async def set_mode(self, mode: Mode) -> None:
        self.mode = mode
        self.listening = False
        if mode == "present":
            main = self.ws.library.main()
            titles = {p.number: p.title for p in main.pages} if main else {}
            self.tracker = Tracker(self.ws.notes, titles)
            await self.bus.show("present", **self.tracker.hud())
        else:
            await self.bus.show("idle")

    async def toggle_listen(self) -> None:
        if self.mode == "present":
            return
        self.listening = not self.listening
        await self.bus.show("listening" if self.listening else "idle", partial="")

    # --- transcript events -------------------------------------------------------------

    async def on_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "transcript" and not event.get("final"):
            if self.mode == "qa" and self.listening:
                await self.bus.show("listening", partial=event.get("transcript", ""))
        elif kind == "speechComplete":
            text = event.get("transcript", "").strip()
            if self.mode == "present":
                await self.hear(text)
            elif self.listening and text:
                self.listening = False
                await self.answer(text)

    async def run_stream(self, events: AsyncIterator[dict]) -> None:
        async for event in events:
            await self.on_event(event)

    # --- presentation mode -------------------------------------------------------------

    async def hear(self, sentence: str) -> None:
        if self.tracker is None:
            return
        update = self.tracker.hear(sentence)
        if update and update.missed:
            await self.bus.show("missed", missed=update.missed, **self.tracker.hud())
        elif update:
            await self.bus.show("present", **self.tracker.hud())

    async def goto_page(self, delta: int) -> None:
        if self.tracker is None:
            return
        update = self.tracker.goto(self.tracker.index + delta)
        state = "missed" if update.missed else "present"
        await self.bus.show(state, missed=update.missed, **self.tracker.hud())

    # --- Q&A mode ----------------------------------------------------------------------

    async def answer(self, question: str) -> str:
        """Answer one question that has finished. Returns the question id."""
        qid = uuid.uuid4().hex[:8]
        t0 = time.perf_counter()
        self._started[qid] = t0
        record: dict = {"id": qid, "question": question, "at": time.time()}
        self.records[qid] = record

        def ms() -> float:
            return round((time.perf_counter() - t0) * 1000, 1)

        match = self.ws.bank.match(question, self.last_shown)
        if match:
            entry = match.entry
            entry.hits += 1
            self.last_shown = entry.id
            record.update(path="bank", entry=entry.id, qtype=entry.qtype, score=round(match.score, 3))
            card = entry.card.model_dump()
            card["question"] = question
            record["first"] = record["card"] = ms()
            await self.bus.show("card", id=qid, path="bank", **card)
            self._log(record)
            return qid

        record.update(path="live", score=None)
        await self.bus.show("thinking", question=question)
        text = ""
        shown = None
        try:
            async for piece in self.model.answer_stream(self.ws.library, question):
                text += piece
                card = cardtext.parse(text, question)
                if card and (shown is None or card != shown):
                    if shown is None:
                        record["first"] = ms()
                    shown = card
                    await self.bus.show("card", id=qid, path="live", **card.model_dump())
        except Exception as error:  # network or API failure: don't leave the lens on "thinking"
            log.exception("live answer failed")
            record["error"] = str(error)

        final = cardtext.parse(text + "\n", question)
        if final is None:
            await self.bus.show("repeat", partial=question)
            record["path"] = "none"
        else:
            if final.source and self.ws.library.resolve(final.source) is None:
                final.source = None  # never show a citation that doesn't exist
            record["checks"] = check_card(final, self.ws.library) if final.source else ["no source"]
            await self.bus.show("card", id=qid, path="live", **final.model_dump())
        record["card"] = ms()
        self.last_shown = None
        self._log(record)
        return qid

    def mark_rendered(self, qid: str) -> None:
        t0 = self._started.get(qid)
        record = self.records.get(qid)
        if t0 is None or record is None:
            return
        record["rendered"] = round((time.perf_counter() - t0) * 1000, 1)
        log.info("%s %s: first %.0f ms, rendered %.0f ms", qid, record.get("path"), record.get("first", -1), record["rendered"])

    def _log(self, record: dict) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def stats(self) -> dict:
        records = list(self.records.values())
        by_path: dict[str, dict] = {}
        for path in ("bank", "live"):
            firsts = [r["first"] for r in records if r.get("path") == path and "first" in r]
            rendered = [r["rendered"] for r in records if r.get("path") == path and "rendered" in r]
            by_path[path] = {
                "count": len([r for r in records if r.get("path") == path]),
                "first_p50": percentile(firsts, 50),
                "first_p95": percentile(firsts, 95),
                "rendered_p50": percentile(rendered, 50),
                "rendered_p95": percentile(rendered, 95),
            }
        total = len(records)
        hits = by_path["bank"]["count"]
        return {
            "questions": total,
            "hit_rate": hits / total if total else None,
            "paths": by_path,
            "recent": records[-20:][::-1],
            "cache": getattr(self.model, "cache_stats", [])[-20:][::-1],
        }
