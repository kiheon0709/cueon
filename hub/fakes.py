"""Stand-ins for Muse Voice Transcribe and Muse Spark so the pipeline runs without an API key.

They follow the same shape the real clients will: the STT yields cumulative partial transcripts
and then the final sentence; the agent turns a question into a Card.
"""

import asyncio
import re
from collections.abc import AsyncIterator

from hub.cards import Card


async def fake_transcribe(text: str, word_ms: int = 80) -> AsyncIterator[tuple[str, bool]]:
    """Yield (transcript, is_final) like ENDPOINTING mode: cumulative partials, then speechComplete."""
    words = text.split()
    for i in range(1, len(words) + 1):
        await asyncio.sleep(word_ms / 1000)
        yield " ".join(words[:i]), False
    yield text, True


# Demo deck = Cueon's own pitch, so these mirror questions a judge might ask.
_CARDS = [
    (
        {"latency", "fast", "slow", "speed"},
        Card(
            question="How fast is it?",
            lead="Card in ~1.5s after the question",
            points=["Prepared cards show in ~0.3s", "Cached deck, no retrieval step", "p50/p95 logged per stage"],
            source="Slide 7",
        ),
    ),
    (
        {"different", "competitor", "conversate", "teleprompter"},
        Card(
            question="How is this different?",
            lead="Built only for live Q&A",
            points=["Teleprompter can't react to questions", "Answers come from your own deck", "Tested: no help vs Cueon"],
            source="Slide 3",
        ),
    ),
    (
        {"privacy", "record", "data", "audio"},
        Card(
            question="What about privacy?",
            lead="Push-to-listen, nothing stored",
            points=["Audio is never saved", "Local mode keeps the deck on device", "No speaker identification"],
            source="Slide 9",
        ),
    ),
]


async def fake_answer(question: str) -> Card | None:
    """Return the prepared card whose keywords overlap the question, or None if nothing fits."""
    await asyncio.sleep(0.3)
    words = set(re.findall(r"[a-z]+", question.lower()))
    best = max(_CARDS, key=lambda item: len(item[0] & words))
    if not best[0] & words:
        return None
    return best[1].model_copy(update={"question": question})
