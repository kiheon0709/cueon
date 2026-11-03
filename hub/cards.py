from pydantic import BaseModel


class Card(BaseModel):
    """Answer cue shown on the lens: lead line + key points + where it comes from."""

    question: str
    lead: str
    points: list[str]
    source: str | None = None  # "<alias> p.<n>", e.g. "BP p.12"
    live: bool = False  # written on the spot by Spark, not a prepared and checked card
