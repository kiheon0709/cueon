"""Prep Agent: expected questions → a checked card per question → the card bank, before the talk.

Each card goes through save_card: deterministic checks, then the LLM judge. A rejected card goes
back to the writer with the problems, up to MAX_ATTEMPTS. What still fails becomes a gap the
presenter reviews in the console ("the material doesn't support this").
"""

import asyncio
import re
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from hub.bank import Bank
from hub.cards import Card
from hub.models import Model
from hub.sources import Library
from hub.verify import Judge, save_card

MAX_ATTEMPTS = 3
PARALLEL = 4
Review = Callable[[str, Card], Awaitable[list[str]]]
SHORTHAND = re.compile(r"\bp\.\s*\d+")

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
    question: str, library: Library, write_card: WriteCard, judge: Judge | None = None, review: Review | None = None
) -> tuple[Card | None, list[str], int]:
    """Write one card and keep revising it until it passes. Returns (card, problems, attempts)."""
    passed: Card | None = None  # a weak card is improved while tries remain, but it's still true: never a gap
    feedback: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        card = await write_card(question, feedback)
        if card is None:
            return passed, [] if passed else ["The material has no answer for this question."], attempt
        feedback = await save_card(card, library, [], judge)
        if not feedback:
            passed = card
            try:
                feedback = await review(question, card) if review and attempt < MAX_ATTEMPTS else []
            except Exception:  # a review that fails must not cost a card that passed its checks
                feedback = []
            if not feedback:
                return card, [], attempt
    return passed, [] if passed else feedback, MAX_ATTEMPTS


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


def spoken(variants: list[str]) -> list[str]:
    """Only phrasings someone could really say: cited or two-word shorthand would just match by accident."""
    return [v for v in variants if not SHORTHAND.search(v) and len(v.split()) >= 3]


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

    def review(question: str, card: Card):
        return model.review(library, question, card)

    bank = Bank()
    gaps: list[Gap] = []
    attempts: dict[str, int] = {}
    gate = asyncio.Semaphore(PARALLEL)

    async def one(question: str) -> tuple[Card | None, list[str]]:
        async with gate:
            try:
                card, problems, used = await write_checked(question, library, write, judge, review)
            except Exception as error:  # one failed call becomes a gap; the rest of prep goes on
                card, problems, used = None, [f"Model call failed: {error}"], MAX_ATTEMPTS
        attempts[question] = used
        if card is None:
            gaps.append(Gap(question=question, problems=problems))
        else:
            card.question = question  # match on the spoken question, not the writer's shorthand
        return card, problems

    parents = await asyncio.gather(*(one(plan.question) for plan in plans))
    done = 0
    for plan, (card, _) in zip(plans, parents):
        done += 1
        if card is None:
            continue
        entry = bank.add(plan.qtype, card, spoken(plan.variants), audience=plan.audience)
        children = await asyncio.gather(*(one(f.question) for f in plan.follow_ups))
        for follow, (child, _) in zip(plan.follow_ups, children):
            if child is not None:
                bank.add(plan.qtype, child, spoken(follow.variants), parent=entry.id, audience=plan.audience)
        await report(f"Question type {done} of {len(plans)}, {len(bank.entries)} cards so far")

    await report(f"Done: {len(bank.entries)} cards, {len(gaps)} gaps")
    return BankResult(bank=bank, gaps=gaps, attempts=attempts)


# --- the whole prep run ---------------------------------------------------------------------

VISION_PARALLEL = 4


async def read_charts(model: Model, library: Library) -> int:
    """Add numbers printed in charts and tables to each page, so cards may cite them. Returns pages read."""
    from hub.sources import numbers_in, page_png, pages_with_visuals

    jobs = []
    for doc in library.documents:
        if doc.path and doc.path.lower().endswith(".pdf"):
            jobs += [(doc, n) for n in pages_with_visuals(doc.path)]
    gate = asyncio.Semaphore(VISION_PARALLEL)

    async def one(doc, number: int) -> None:
        async with gate:
            try:
                found = await model.chart_numbers(page_png(doc.path, number))
            except Exception:
                return  # a page we can't read keeps its text numbers
        page = doc.page(number)
        if page:
            page.numbers |= numbers_in(" ".join(found))

    await asyncio.gather(*(one(doc, n) for doc, n in jobs))
    return len(jobs)


def check_notes(notes: list, library: Library) -> list:
    """Same number check as cards: a supporting line must cite a real page that has its numbers."""
    from hub.sources import numbers_in

    main = library.main()
    for note in notes:
        if note.support:
            found = library.resolve(note.support_source)
            if found is None or not numbers_in(note.support) <= found[1].numbers:
                note.support, note.support_source = "", ""
        page = main.page(note.page) if main else None
        if page:
            note.points = [p for p in note.points if numbers_in(p) <= page.numbers]
    return notes


def prep_stats(attempts: dict[str, int], gaps: list[Gap]) -> dict:
    total = len(attempts)
    gap_questions = {g.question for g in gaps}
    passed = {q: n for q, n in attempts.items() if q not in gap_questions}
    return {
        "questions": total,
        "cards": len(passed),
        "first_try": sum(1 for n in passed.values() if n == 1),
        "retried": sum(1 for n in passed.values() if n > 1),
        "gaps": len(gap_questions),
        "drafts": sum(attempts.values()),
    }
