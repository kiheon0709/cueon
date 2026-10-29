"""Prep Agent loop: write a card per expected question, verify it, retry with feedback, give up to the presenter.

The model calls (generating expected questions, writing a card, judging a claim) come in as
functions so the loop runs the same with Muse Spark, Muse Glimmer, or a test double.
"""

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from hub.cards import Card
from hub.deck import Deck
from hub.verify import save_card

MAX_ATTEMPTS = 3

# (question, feedback from the last failed attempt) -> card, or None if the deck can't answer it
WriteCard = Callable[[str, list[str]], Awaitable[Card | None]]


class Gap(BaseModel):
    """A question the deck couldn't support; the presenter reviews these before the talk."""

    question: str
    problems: list[str]


class PrepResult(BaseModel):
    cards: list[Card]
    gaps: list[Gap]
    attempts: dict[str, int]  # question -> attempts used, for the rejection-rate numbers


async def prepare_cards(questions: list[str], deck: Deck, write_card: WriteCard) -> PrepResult:
    cards: list[Card] = []
    gaps: list[Gap] = []
    attempts: dict[str, int] = {}

    for question in questions:
        feedback: list[str] = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            attempts[question] = attempt
            card = await write_card(question, feedback)
            if card is None:
                feedback = ["The deck has no material for this question."]
                break
            feedback = save_card(card, deck, cards)
            if not feedback:
                break
        if feedback:
            gaps.append(Gap(question=question, problems=feedback))

    return PrepResult(cards=cards, gaps=gaps, attempts=attempts)
