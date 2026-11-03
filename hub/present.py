"""Presentation mode: follow the talk through the slides and flag points the presenter skipped.

No model call happens during the talk. Spark writes the page notes beforehand (key points, a
bridge line, a short version); live, each spoken sentence is compared with the notes to find the
current page and tick off points. Moving on with points still open raises a "missed" cue.
"""

from pydantic import BaseModel

from hub.models import PageNotes
from hub.similarity import similarity

COVER_THRESHOLD = 0.38  # sentence says this point
MOVE_THRESHOLD = 0.30  # sentence belongs to another page
STRONG_MOVE = 0.5  # move at once instead of waiting for a second sentence


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
    def __init__(self, notes: list[PageNotes], titles: dict[int, str]) -> None:
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

    def hear(self, sentence: str) -> Update | None:
        state = self.current
        if state is None or not sentence.strip():
            return None

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

    def hud(self) -> dict:
        state = self.current
        if state is None:
            return {}
        return {
            "page": state.page,
            "total": len(self.pages),
            "title": state.title,
            "points": [{"text": p, "done": d} for p, d in zip(state.points, state.covered)],
            "bridge": state.bridge,
        }
