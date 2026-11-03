"""Live loop: transcript events → (Q&A) card or (presentation) position and missed points → HUD.

Q&A has two paths. The fast path matches the question against the card bank locally and shows the
prepared card unchanged. When no card is close enough, the live path streams a card from Spark
with all of the material in the cached prefix; the lead goes to the lens as soon as its line is
done, and the card is marked as written on the spot.

Latency tricks on the live path:
- Speculative start: a partial transcript that already reads like a whole question starts the
  Spark request before the speaker finishes. If the final question is the same, that request
  is reused; otherwise it is cancelled.
- Fallback: if Spark has no lead line after FALLBACK_S, the nearest bank card is shown marked
  as tentative, and replaced when Spark's card arrives.

Every question is logged with its path and stage timings, which is where the hit rate and
p50/p95 numbers come from.
"""

import asyncio
import contextlib
import json
import logging
import re
import statistics
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

from hub import cardtext
from hub.bank import TENTATIVE_THRESHOLD, Match
from hub.bus import HudBus
from hub.cards import Card
from hub.models import Model
from hub.present import Tracker
from hub.similarity import similarity
from hub.verify import check_card
from hub.workspace import Workspace

log = logging.getLogger("cueon")

Mode = Literal["qa", "present"]

FALLBACK_S = 1.2
SPECULATE_MIN_WORDS = 5
SAME_QUESTION = 0.9  # final transcript close enough to the speculated one to keep its answer
_QUESTION_START = re.compile(
    r"^(what|why|how|when|where|who|which|is|are|do|does|did|can|could|would|will|should|have|has|"
    r"tell|explain|so|and)\b",
    re.I,
)


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1]


def looks_like_question(text: str) -> bool:
    text = text.strip()
    return text.endswith("?") or bool(_QUESTION_START.match(text)) or "?" in text


class LiveRun:
    """One streaming Spark answer, collected in the background so it can start early."""

    def __init__(self, model: Model, workspace: Workspace, question: str) -> None:
        self.question = question
        self.text = ""
        self.error: str | None = None
        self.done = False
        self.changed = asyncio.Event()
        self.started = time.perf_counter()
        self.task = asyncio.create_task(self._run(model, workspace))

    async def _run(self, model: Model, workspace: Workspace) -> None:
        try:
            async for piece in model.answer_stream(workspace.library, self.question):
                self.text += piece
                self.changed.set()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # network or API failure
            log.exception("live answer failed")
            self.error = str(error)
        finally:
            self.done = True
            self.changed.set()

    def cancel(self) -> None:
        self.task.cancel()


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
        self._speculative: LiveRun | None = None
        # Cards the presenter can swipe through for the current question: (qid, cards, index)
        self._choices: tuple[str, list[dict], int] | None = None

    # --- modes ---------------------------------------------------------------------------

    async def set_mode(self, mode: Mode) -> None:
        self.mode = mode
        self.listening = False
        self._drop_speculation()
        if mode == "present":
            main = self.ws.library.main()
            titles = {p.number: p.title for p in main.pages} if main else {}
            self.tracker = Tracker(self.ws.notes, titles, target_s=int(self.ws.talk_minutes * 60))
            await self.bus.show("present", **self.tracker.hud())
        else:
            await self.bus.show("idle")

    async def toggle_listen(self) -> None:
        if self.mode == "present":
            return
        self.listening = not self.listening
        if not self.listening:
            self._drop_speculation()
        await self.bus.show("listening" if self.listening else "idle", partial="")

    async def swipe(self, delta: int) -> None:
        """Left/right on the Neural Band: correct the page, or flip to the next candidate card."""
        if self.mode == "present":
            await self.goto_page(delta)
            return
        if not self._choices:
            return
        qid, cards, index = self._choices
        index = (index + delta) % len(cards)
        self._choices = (qid, cards, index)
        card = cards[index]
        self.last_shown = card.get("entry")
        await self.bus.show("card", id=qid, choice=index + 1, choices=len(cards), **card["card"])

    # --- transcript events -------------------------------------------------------------

    async def on_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "transcript" and not event.get("final"):
            if self.mode == "qa" and self.listening:
                partial = event.get("transcript", "")
                await self.bus.show("listening", partial=partial)
                self._maybe_speculate(partial)
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

    def _maybe_speculate(self, partial: str) -> None:
        if len(partial.split()) < SPECULATE_MIN_WORDS or not looks_like_question(partial):
            return
        if self.ws.bank.match(partial, self.last_shown):
            return  # the fast path will handle it; no need to spend a Spark call
        current = self._speculative
        if current and similarity(current.question, partial) >= SAME_QUESTION:
            return
        self._drop_speculation()
        self._speculative = LiveRun(self.model, self.ws, partial)

    def _drop_speculation(self) -> None:
        if self._speculative:
            self._speculative.cancel()
            self._speculative = None

    # --- presentation mode -------------------------------------------------------------

    async def hear(self, sentence: str) -> None:
        if self.tracker is None:
            return
        update = self.tracker.hear(sentence)
        if update and update.missed:
            await self.bus.show("missed", missed=update.missed, **self.tracker.hud())
        elif update:
            await self.bus.show("present", **self.tracker.hud())

    async def start_talk(self) -> None:
        """Start the clock now (the presenter's first word also starts it)."""
        if self.tracker is None:
            await self.set_mode("present")
        assert self.tracker is not None
        self.tracker.start()
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

        if len(re.findall(r"\w+", question)) < 2:
            self._drop_speculation()
            record.update(path="none", reason="too short")
            await self.bus.show("repeat", partial=question)
            self._log(record)
            return qid

        ranked = self.ws.bank.rank(question, self.last_shown)
        match = self.ws.bank.match(question, self.last_shown)
        if match:
            self._drop_speculation()
            await self._show_bank(qid, question, match, ranked, record, ms)
            self._log(record)
            return qid

        record.update(path="live", score=round(ranked[0].score, 3) if ranked else None)
        run = self._take_speculation(question)
        record["speculative"] = run is not None
        if run is None:
            run = LiveRun(self.model, self.ws, question)
        await self.bus.show("thinking", question=question)

        shown: Card | None = None
        tentative = ranked[0] if ranked and ranked[0].score >= TENTATIVE_THRESHOLD else None
        deadline = t0 + FALLBACK_S
        while True:
            card = cardtext.parse(run.text, question)
            if card and card != shown:
                if shown is None:
                    record["first"] = ms()
                shown = card
                await self.bus.show("card", id=qid, path="live", **card.model_dump())
            if run.done:
                break
            timeout = None
            if shown is None and tentative is not None:
                timeout = max(0.0, deadline - time.perf_counter())
                if timeout == 0:
                    record["tentative"] = tentative.entry.id
                    record["tentative_ms"] = ms()
                    await self.bus.show(
                        "card", id=qid, path="bank", tentative=True, **self._bank_card(tentative, question)
                    )
                    tentative = None
                    continue
            run.changed.clear()
            if not run.done:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(run.changed.wait(), timeout)

        if run.error:
            record["error"] = run.error
        final = cardtext.parse(run.text + "\n", question)
        if final is None:
            if "tentative" not in record:
                await self.bus.show("repeat", partial=question)
                record["path"] = "none"
        else:
            if final.source and self.ws.library.resolve(final.source) is None:
                final.source = None  # never show a citation that doesn't exist
            record["checks"] = check_card(final, self.ws.library) if final.source else ["no source"]
            await self.bus.show("card", id=qid, path="live", **final.model_dump())
            choices = [{"card": final.model_dump()}] + [
                {"card": self._bank_card(m, question), "entry": m.entry.id} for m in ranked[:2] if m.score >= TENTATIVE_THRESHOLD
            ]
            self._choices = (qid, choices, 0)
        record["card"] = ms()
        self.last_shown = None
        self._log(record)
        return qid

    def _bank_card(self, match: Match, question: str) -> dict:
        card = match.entry.card.model_dump()
        card["question"] = question
        return card

    async def _show_bank(self, qid: str, question: str, match: Match, ranked: list[Match], record: dict, ms) -> None:
        entry = match.entry
        entry.hits += 1
        self.last_shown = entry.id
        record.update(path="bank", entry=entry.id, qtype=entry.qtype, score=round(match.score, 3))
        others = [m for m in ranked if m.entry.id != entry.id and m.score >= TENTATIVE_THRESHOLD][:1]
        if others:
            record["runner_up"] = {"entry": others[0].entry.id, "score": round(others[0].score, 3)}
        choices = [{"card": self._bank_card(m, question), "entry": m.entry.id} for m in [match, *others]]
        self._choices = (qid, choices, 0)
        record["first"] = record["card"] = ms()
        extra = {"choices": len(choices)} if len(choices) > 1 else {}
        await self.bus.show("card", id=qid, path="bank", choice=1, **extra, **choices[0]["card"])

    def _take_speculation(self, question: str) -> LiveRun | None:
        run = self._speculative
        self._speculative = None
        if run is None:
            return None
        if similarity(run.question, question) >= SAME_QUESTION and not run.error:
            return run
        run.cancel()
        return None

    def mark_rendered(self, qid: str) -> None:
        # First render only: that's when the presenter can start reading (the lead line).
        t0 = self._started.pop(qid, None)
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
            "speculative": sum(1 for r in records if r.get("speculative")),
            "tentative": sum(1 for r in records if r.get("tentative")),
            "paths": by_path,
            "recent": records[-20:][::-1],
            "cache": getattr(self.model, "cache_stats", [])[-20:][::-1],
        }
