"""Everything prepared before the talk, saved under data/ so a restart keeps it."""

import re
from pathlib import Path

from pydantic import BaseModel

from hub.bank import Bank
from hub.models import PageNotes
from hub.prep import Gap
from hub.sources import Library

MAX_KEYWORD = 30  # Voice Transcribe rejects the whole session over a longer keyword
CITATION = re.compile(r"\s*[—–-]\s*\S+ p\.\d+\s*$")


class Workspace(BaseModel):
    library: Library = Library()
    bank: Bank = Bank()
    gaps: list[Gap] = []
    notes: list[PageNotes] = []
    attempts: dict[str, int] = {}
    stt_terms: list[str] = []  # picked by the model during prep
    talk_minutes: float = 0  # planned talk length for the presentation timer; 0 = off

    def save(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "workspace.json").write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, data_dir: Path) -> "Workspace":
        path = data_dir / "workspace.json"
        return cls.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else cls()

    def keywords(self) -> list[str]:
        """Terms to bias speech recognition toward: document aliases and page titles."""
        terms: list[str] = list(self.stt_terms)
        for doc in self.library.documents:
            terms.append(doc.alias)
            terms += [p.title for p in doc.pages if p.title.strip()]
        seen: list[str] = []
        for term in terms:
            term = CITATION.sub("", term).strip()  # the model tends to cite its terms too
            if term and len(term) <= MAX_KEYWORD and term not in seen:
                seen.append(term)
        return seen[:50]
