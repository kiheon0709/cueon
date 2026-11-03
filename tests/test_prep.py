import asyncio

import pymupdf
import pytest

from hub.cards import Card
from hub.models import FakeModel
from hub.prep import build_bank, prepare_cards
from hub.sources import Library, numbers_in, parse_csv, parse_file, render_pages
from hub.verify import check_card

SLIDES = [
    "Cueon\nLive Q&A cue cards for presenters",
    "Latency\nCard appears 1.4s after the question (p50)\np95 is 2.3s on Muse Spark",
    "Pricing\nSpeech-to-text costs $0.18 per hour\nUsed by 1,000 presenters",
]


@pytest.fixture
def deck_pdf(tmp_path):
    path = tmp_path / "deck.pdf"
    with pymupdf.open() as doc:
        for text in SLIDES:
            doc.new_page().insert_text((72, 72), text)
        doc.save(path)
    return path


@pytest.fixture
def library(deck_pdf):
    lib = Library()
    lib.add(parse_file(deck_pdf, alias="DECK"))
    lib.add(parse_csv("month,users\nJan,120\nFeb,340\n", alias="DATA", name="users.csv"))
    return lib


def card(lead: str, points: list[str], source: str = "DECK p.2") -> Card:
    return Card(question="q", lead=lead, points=points, source=source)


def test_numbers_ignore_labels_and_commas():
    assert numbers_in("p50 is 1.4s, p95 2.3s, $0.18, 1,000 users, GPT3") == {"1.4", "2.3", "0.18", "1000"}


def test_library_indexes_pdf_and_csv(library, deck_pdf, tmp_path):
    deck = library.doc("DECK")
    assert deck.role == "main" and [p.title for p in deck.pages] == ["Cueon", "Latency", "Pricing"]
    assert deck.page(2).numbers == {"1.4", "2.3"}
    assert library.doc("DATA").role == "evidence" and library.doc("DATA").page(1).numbers == {"120", "340"}
    assert library.resolve("DATA p.1")[1].number == 1
    assert library.resolve("Slide 2") is None
    assert "## DECK p.2" in library.as_prompt()
    assert len(render_pages(deck_pdf, tmp_path / "img")) == 3


def test_check_card(library):
    assert check_card(card("Faster: 1.4s p50", ["p95 2.3s"]), library) == []
    assert check_card(card("340 users in Feb", [], source="DATA p.1"), library) == []

    [problem] = check_card(card("Faster: 0.9s p50", ["p95 2.3s"]), library)
    assert "0.9" in problem and "DECK p.2" in problem

    [problem] = check_card(card("Fast", [], source="DECK p.9"), library)
    assert "not a page" in problem and "DECK, DATA" in problem

    [problem] = check_card(card(" ".join(["word"] * 13), []), library)
    assert "13 words" in problem


def test_prepare_cards_retries_with_feedback_then_gives_up(library):
    feedback_seen = []

    async def write_card(question, feedback):
        feedback_seen.append(feedback)
        if question == "How fast?":
            # First draft invents a number; fixed once the check explains why.
            lead = "Faster: 1.4s p50" if feedback else "Faster: 0.9s p50"
            return card(lead, ["p95 2.3s"])
        if question == "What's the revenue?":
            return card("Revenue is $5M", [], source="DECK p.3")  # never in the material
        return None

    result = asyncio.run(prepare_cards(["How fast?", "What's the revenue?", "Who is the CEO?"], library, write_card))

    assert [c.lead for c in result.cards] == ["Faster: 1.4s p50"]
    assert result.attempts == {"How fast?": 2, "What's the revenue?": 3, "Who is the CEO?": 1}
    assert "0.9" in feedback_seen[1][0]
    assert [g.question for g in result.gaps] == ["What's the revenue?", "Who is the CEO?"]


def test_judge_rejection_feeds_back(library):
    async def write_card(question, feedback):
        return card("Fast" if feedback else "Fastest in the world", [])

    async def judge(c):
        return ["Not supported by DECK p.2: fastest in the world"] if "world" in c.lead else []

    result = asyncio.run(prepare_cards(["How fast?"], library, write_card, judge))
    assert [c.lead for c in result.cards] == ["Fast"] and result.attempts["How fast?"] == 2


def test_build_bank_with_stand_in(library):
    result = asyncio.run(build_bank(FakeModel(delay=0), library))
    parents = [e for e in result.bank.entries if e.parent is None]
    assert {e.qtype for e in parents} == {"latency", "pricing"}
    assert all(e.card.source.startswith("DECK p.") for e in parents)
    assert any(e.parent for e in result.bank.entries)  # follow-ups are linked to their parent
