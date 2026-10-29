import asyncio

import pymupdf
import pytest

from hub.cards import Card
from hub.deck import numbers_in, parse_pdf, render_slides
from hub.prep import prepare_cards
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


def card(lead: str, points: list[str], source: str = "Slide 2") -> Card:
    return Card(question="q", lead=lead, points=points, source=source)


def test_numbers_ignore_labels_and_commas():
    assert numbers_in("p50 is 1.4s, p95 2.3s, $0.18, 1,000 users, GPT3") == {"1.4", "2.3", "0.18", "1000"}


def test_parse_pdf_builds_slide_index(deck_pdf, tmp_path):
    deck = parse_pdf(deck_pdf)
    assert [s.title for s in deck.slides] == ["Cueon", "Latency", "Pricing"]
    assert deck.slide(2).numbers == {"1.4", "2.3"}
    assert deck.slide(3).numbers == {"0.18", "1000"}
    assert len(render_slides(deck_pdf, tmp_path / "img")) == 3


def test_check_card(deck_pdf):
    deck = parse_pdf(deck_pdf)
    assert check_card(card("Faster: 1.4s p50", ["p95 2.3s"]), deck) == []

    [problem] = check_card(card("Faster: 0.9s p50", ["p95 2.3s"]), deck)
    assert "0.9" in problem and "Slide 2" in problem

    [problem] = check_card(card("Fast", [], source="Slide 9"), deck)
    assert "not a slide" in problem

    [problem] = check_card(card(" ".join(["word"] * 13), []), deck)
    assert "13 words" in problem


def test_prepare_cards_retries_with_feedback_then_gives_up(deck_pdf):
    deck = parse_pdf(deck_pdf)
    feedback_seen = []

    async def write_card(question, feedback):
        feedback_seen.append(feedback)
        if question == "How fast?":
            # First draft invents a number; fixed once the check explains why.
            lead = "Faster: 1.4s p50" if feedback else "Faster: 0.9s p50"
            return card(lead, ["p95 2.3s"])
        if question == "What's the revenue?":
            return card("Revenue is $5M", [], source="Slide 3")  # never on the deck
        return None

    result = asyncio.run(prepare_cards(["How fast?", "What's the revenue?", "Who is the CEO?"], deck, write_card))

    assert [c.lead for c in result.cards] == ["Faster: 1.4s p50"]
    assert result.attempts == {"How fast?": 2, "What's the revenue?": 3, "Who is the CEO?": 1}
    assert "0.9" in feedback_seen[1][0]
    assert [g.question for g in result.gaps] == ["What's the revenue?", "Who is the CEO?"]
