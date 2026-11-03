"""Prep Agent: expected questions → a checked card per question → the card bank, before the talk.

Each card goes through save_card: deterministic checks, then the LLM judge. A rejected card goes
back to the writer with the problems, up to MAX_ATTEMPTS. What still fails becomes a gap the
presenter reviews in the console ("the material doesn't support this").
"""

import asyncio
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from hub.bank import Bank
from hub.cards import Card
from hub.models import Model
from hub.sources import Library
from hub.verify import Judge, save_card

MAX_ATTEMPTS = 3
PARALLEL = 4

# (question, feedback from the last failed attempt) -> card, or None if the material can't answer it
WriteCard = Callable[[str, list[str]], Awaitable[Card | None]]
Progress = Callable[[str], Awaitable[None] | None]


class Gap(BaseModel):
    """A question the material couldn't support; the presenter reviews these before the talk."""

    question: str
    problems: list[str]


class PrepResult(BaseModel):
    cards: list[Card]
    gaps: list[Gap]
    attempts: dict[str, int]  # question -> attempts used, for the rejection-rate numbers


async def write_checked(
    question: str, library: Library, write_card: WriteCard, judge: Judge | None = None
) -> tuple[Card | None, list[str], int]:
    """Write one card and keep revising it until it passes. Returns (card, problems, attempts)."""
    saved: list[Card] = []
    feedback: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        card = await write_card(question, feedback)
        if card is None:
            return None, ["The material has no answer for this question."], attempt
        feedback = await save_card(card, library, saved, judge)
        if not feedback:
            return saved[0], [], attempt
    return None, feedback, MAX_ATTEMPTS


async def prepare_cards(
    questions: list[str], library: Library, write_card: WriteCard, judge: Judge | None = None
) -> PrepResult:
    cards: list[Card] = []
    gaps: list[Gap] = []
    attempts: dict[str, int] = {}
    for question in questions:
        card, problems, used = await write_checked(question, library, write_card, judge)
        attempts[question] = used
        if card:
            cards.append(card)
        else:
            gaps.append(Gap(question=question, problems=problems))
    return PrepResult(cards=cards, gaps=gaps, attempts=attempts)


class BankResult(BaseModel):
    bank: Bank
    gaps: list[Gap]
    attempts: dict[str, int]


async def build_bank(model: Model, library: Library, limit: int = 12, progress: Progress | None = None) -> BankResult:
    async def report(text: str) -> None:
        if progress:
            result = progress(text)
            if asyncio.iscoroutine(result):
                await result

    await report("Predicting questions")
    plans = await model.expected_questions(library, limit)
    await report(f"Writing cards for {len(plans)} question types")

    def write(question: str, feedback: list[str]):
        return model.write_card(library, question, feedback)

    def judge(card: Card):
        return model.judge(library, card)

    bank = Bank()
    gaps: list[Gap] = []
    attempts: dict[str, int] = {}
    gate = asyncio.Semaphore(PARALLEL)

    async def one(question: str) -> tuple[Card | None, list[str]]:
        async with gate:
            card, problems, used = await write_checked(question, library, write, judge)
        attempts[question] = used
        if card is None:
            gaps.append(Gap(question=question, problems=problems))
        return card, problems

    parents = await asyncio.gather(*(one(plan.question) for plan in plans))
    done = 0
    for plan, (card, _) in zip(plans, parents):
        done += 1
        if card is None:
            continue
        entry = bank.add(plan.qtype, card, plan.variants)
        children = await asyncio.gather(*(one(f.question) for f in plan.follow_ups))
        for follow, (child, _) in zip(plan.follow_ups, children):
            if child is not None:
                bank.add(plan.qtype, child, follow.variants, parent=entry.id)
        await report(f"Cards {done}/{len(plans)}")

    await report(f"Done: {len(bank.entries)} cards, {len(gaps)} gaps")
    return BankResult(bank=bank, gaps=gaps, attempts=attempts)
