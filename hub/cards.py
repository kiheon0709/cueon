from pydantic import BaseModel


class Card(BaseModel):
    """Answer cue shown on the lens (format B: lead line + key points + slide)."""

    question: str
    lead: str
    points: list[str]
    source: str | None = None
