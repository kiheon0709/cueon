"""Mandatory card checks, run inside save_card so the agent can't skip them (Agents 102 pattern).

Only deterministic checks live here. The LLM-as-a-judge check plugs in later through Prep.
"""

import re

from hub.cards import Card
from hub.deck import Deck, numbers_in

MAX_LEAD_WORDS = 12
MAX_POINTS = 3


def check_card(card: Card, deck: Deck) -> list[str]:
    """Return problems with the card; empty means it passed."""
    problems = []

    if len(card.lead.split()) > MAX_LEAD_WORDS:
        problems.append(f"Lead has {len(card.lead.split())} words; keep it to {MAX_LEAD_WORDS} or fewer.")
    if len(card.points) > MAX_POINTS:
        problems.append(f"Card has {len(card.points)} points; keep it to {MAX_POINTS} or fewer.")

    match = re.fullmatch(r"Slide (\d+)", card.source or "")
    slide = deck.slide(int(match.group(1))) if match else None
    if slide is None:
        problems.append(f"Source {card.source!r} is not a slide in this deck. Use 'Slide N'.")
        return problems

    # Every number on the card must come from the cited slide (blocks invented figures).
    card_numbers = numbers_in(" ".join([card.lead, *card.points]))
    missing = sorted(card_numbers - slide.numbers)
    if missing:
        problems.append(f"Numbers {', '.join(missing)} are not on Slide {slide.number}.")

    return problems


def save_card(card: Card, deck: Deck, saved: list[Card]) -> list[str]:
    """Save the card only if it passes every check. Returns the problems (empty = saved)."""
    problems = check_card(card, deck)
    if not problems:
        saved.append(card)
    return problems
