"""Q&A card bank: one checked card per question type, the phrasings it matches, and its follow-ups.

Matching is local and fast (no model call). A matched card is shown exactly as prepared. After a
card is shown, its follow-ups get priority, because the next question usually builds on it.
"""

import uuid
from pathlib import Path

from pydantic import BaseModel

from hub.cards import Card
from hub.similarity import cosine, features

MATCH_THRESHOLD = 0.42  # below this the live path writes a card on the spot
FOLLOW_UP_BONUS = 0.08


class Entry(BaseModel):
    id: str
    qtype: str
    question: str
    variants: list[str] = []
    card: Card
    parent: str | None = None  # set on follow-up entries
    edited: bool = False  # the presenter changed it in the console
    hits: int = 0


class Match(BaseModel):
    entry: Entry
    score: float
    phrase: str  # the question or variant that matched best


class Bank(BaseModel):
    entries: list[Entry] = []

    def add(self, qtype: str, card: Card, variants: list[str], parent: str | None = None) -> Entry:
        entry = Entry(id=uuid.uuid4().hex[:8], qtype=qtype, question=card.question, variants=variants, card=card, parent=parent)
        self.entries.append(entry)
        return entry

    def get(self, entry_id: str) -> Entry | None:
        return next((e for e in self.entries if e.id == entry_id), None)

    def remove(self, entry_id: str) -> None:
        self.entries = [e for e in self.entries if e.id != entry_id and e.parent != entry_id]

    def follow_ups(self, entry_id: str) -> list[Entry]:
        return [e for e in self.entries if e.parent == entry_id]

    def match(self, question: str, last_shown: str | None = None) -> Match | None:
        """Best entry for the question, or None if nothing is close enough to show as is."""
        heard = features(question)
        best: Match | None = None
        for entry in self.entries:
            bonus = FOLLOW_UP_BONUS if last_shown and entry.parent == last_shown else 0.0
            for phrase in [entry.question, *entry.variants]:
                score = cosine(heard, features(phrase)) + bonus
                if best is None or score > best.score:
                    best = Match(entry=entry, score=score, phrase=phrase)
        if best is None or best.score < MATCH_THRESHOLD:
            return None
        return best

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Bank":
        return cls.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else cls()
