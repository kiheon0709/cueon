"""Mandatory card checks, run inside save_card so the agent can't skip them (Agents 102 pattern).

The deterministic checks run first; the LLM judge only sees cards that already passed them.
"""

from collections.abc import Awaitable, Callable

from hub.cards import Card
from hub.sources import Library, numbers_in

MAX_LEAD_WORDS = 12
MAX_POINTS = 3

Judge = Callable[[Card], Awaitable[list[str]]]


def check_card(card: Card, library: Library) -> list[str]:
    """Return problems with the card; empty means it passed."""
    problems = []

    if len(card.lead.split()) > MAX_LEAD_WORDS:
        problems.append(f"Lead has {len(card.lead.split())} words; keep it to {MAX_LEAD_WORDS} or fewer.")
    if len(card.points) > MAX_POINTS:
        problems.append(f"Card has {len(card.points)} points; keep it to {MAX_POINTS} or fewer.")

    found = library.resolve(card.source)
    if found is None:
        aliases = ", ".join(d.alias for d in library.documents)
        problems.append(f"Source {card.source!r} is not a page in the material. Use '<alias> p.<n>' with one of: {aliases}.")
        return problems
    doc, page = found

    # Every number on the card must come from the cited page (blocks invented figures).
    card_numbers = numbers_in(" ".join([card.lead, *card.points]))
    missing = sorted(card_numbers - page.numbers)
    if missing:
        problems.append(f"Numbers {', '.join(missing)} are not on {doc.alias} p.{page.number}.")

    return problems


async def save_card(card: Card, library: Library, saved: list[Card], judge: Judge | None = None) -> list[str]:
    """Save the card only if it passes every check. Returns the problems (empty = saved)."""
    problems = check_card(card, library)
    if not problems and judge is not None:
        problems = await judge(card)
    if not problems:
        saved.append(card)
    return problems
