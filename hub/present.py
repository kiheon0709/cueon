"""Presentation mode: follow the talk through the slides and flag points the presenter skipped.

No model call happens during the talk. Spark writes the page notes beforehand (key points, a
bridge line, a short version); live, each spoken sentence is compared with the notes to find the
current page and tick off points. Moving on with points still open raises a "missed" cue.
"""

import time

from pydantic import BaseModel

from hub.models import PageNotes
from hub.similarity import similarity

COVER_THRESHOLD = 0.38  # sentence says this point
MOVE_THRESHOLD = 0.30  # sentence belongs to another page
STRONG_MOVE = 0.5  # move at once instead of waiting for a second sentence
LOW_TIME_S = 60  # show the short version of the page when less than this is left


class PageState(BaseModel):
    page: int
    title: str
    points: list[str]
    covered: list[bool]
    bridge: str = ""
    short: str = ""


class Update(BaseModel):
    page: int
    moved: bool = False
    missed: list[str] = []  # open points on the page the presenter just left


class Tracker:
    def __init__(self, notes: list[PageNotes], titles: dict[int, str], target_s: int = 0) -> None:
        self.target_s = target_s  # planned talk length; 0 = no timer
        self.started_at: float | None = None  # wall clock, set by the first sentence or start()
        self.pages = [
            PageState(
                page=n.page,
                title=titles.get(n.page, f"p.{n.page}"),
                points=n.points,
                covered=[False] * len(n.points),
                bridge=n.bridge,
                short=n.short,
            )
            for n in sorted(notes, key=lambda n: n.page)
        ]
        self.index = 0
        self._candidate: int | None = None

    @property
    def current(self) -> PageState | None:
        return self.pages[self.index] if self.pages else None

    def _page_score(self, sentence: str, state: PageState) -> float:
        scores = [similarity(sentence, p) for p in state.points]
        scores.append(similarity(sentence, state.title) * 0.8)
        return max(scores)

    def start(self, now: float | None = None) -> None:
        self.started_at = now if now is not None else time.time()

    def hear(self, sentence: str) -> Update | None:
        state = self.current
        if state is None or not sentence.strip():
            return None
        if self.started_at is None:
            self.start()

        for i, point in enumerate(state.points):
            if similarity(sentence, point) >= COVER_THRESHOLD:
                state.covered[i] = True

        here = self._page_score(sentence, state)
        window = range(max(0, self.index - 1), min(len(self.pages), self.index + 3))
        best_index, best = max(((i, self._page_score(sentence, self.pages[i])) for i in window), key=lambda s: s[1])

        if best_index == self.index or best < MOVE_THRESHOLD or best <= here + 0.05:
            self._candidate = None
            return Update(page=state.page)
        if best < STRONG_MOVE and self._candidate != best_index:
            self._candidate = best_index  # wait for one more sentence before moving
            return Update(page=state.page)
        return self.goto(best_index, sentence)

    def goto(self, index: int, sentence: str = "") -> Update:
        index = max(0, min(index, len(self.pages) - 1))
        left = self.pages[self.index]
        missed = [p for p, done in zip(left.points, left.covered) if not done] if index > self.index else []
        self.index = index
        self._candidate = None
        if sentence:
            state = self.pages[index]
            for i, point in enumerate(state.points):
                if similarity(sentence, point) >= COVER_THRESHOLD:
                    state.covered[i] = True
        return Update(page=self.pages[index].page, moved=True, missed=missed)

    def timing(self, now: float | None = None) -> dict:
        """Time left and whether the talk is behind: fewer pages done than the clock says."""
        if not self.target_s or self.started_at is None:
            return {}
        now = now if now is not None else time.time()
        elapsed = now - self.started_at
        left = self.target_s - elapsed
        expected_index = elapsed / self.target_s * len(self.pages)
        return {
            "ends_at": int((self.started_at + self.target_s) * 1000),  # the glasses count down locally
            "left_s": int(left),
            "pages_left": len(self.pages) - self.index - 1,
            "behind": self.index + 1 < expected_index - 0.5,
            "low_time": left < LOW_TIME_S,
        }

    def hud(self, now: float | None = None) -> dict:
        state = self.current
        if state is None:
            return {}
        timing = self.timing(now)
        fields = {
            "page": state.page,
            "total": len(self.pages),
            "title": state.title,
            "points": [{"text": p, "done": d} for p, d in zip(state.points, state.covered)],
            "bridge": state.bridge,
            **timing,
        }
        if timing.get("low_time") and state.short:
            fields["short"] = state.short  # running out of time: say this instead
        return fields
