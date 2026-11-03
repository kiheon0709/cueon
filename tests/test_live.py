import asyncio

from hub import cardtext
from hub.bank import Bank
from hub.cards import Card
from hub.models import PageNotes
from hub.present import Tracker


def test_cardtext_streams_lead_first():
    assert cardtext.parse("LEAD: Card in 1.5", "q") is None  # line not finished yet
    partial = cardtext.parse("LEAD: Card in 1.5s\n- Prepared", "q")
    assert partial.lead == "Card in 1.5s" and partial.points == [] and partial.live
    done = cardtext.parse("LEAD: Card in 1.5s\n- Prepared 0.3s\n- No retrieval\nSOURCE: DECK p.7\n", "q")
    assert done.points == ["Prepared 0.3s", "No retrieval"] and done.source == "DECK p.7"
    assert cardtext.parse(cardtext.format(done), "q") == done


def make_bank() -> Bank:
    bank = Bank()
    latency = bank.add("latency", Card(question="How fast is it?", lead="1.5s", points=[]), ["What's the latency?", "How quickly do cards show up?"])
    bank.add("latency", Card(question="What about on bad wifi?", lead="Local mode", points=[]), ["What if the network is slow?"], parent=latency.id)
    bank.add("privacy", Card(question="Do you record audio?", lead="Nothing stored", points=[]), ["Is the audio saved?", "What about privacy?"])
    return bank


def test_bank_matches_paraphrase_and_rejects_unrelated():
    bank = make_bank()
    assert bank.match("so what's the latency like?").entry.qtype == "latency"
    assert bank.match("is any of the audio saved anywhere?").entry.qtype == "privacy"
    assert bank.match("where did you buy that shirt?") is None


def test_follow_up_gets_priority_after_parent():
    bank = make_bank()
    parent = bank.entries[0]
    plain = bank.match("and if the network is slow?")
    boosted = bank.match("and if the network is slow?", last_shown=parent.id)
    assert boosted.entry.parent == parent.id and boosted.score > plain.score


def test_tracker_follows_talk_and_flags_missed_points():
    notes = [
        PageNotes(page=1, points=["Presenters freeze on hard questions", "Q&A decides the score"]),
        PageNotes(page=2, points=["Cards from your own material", "Shown on the glasses lens"]),
        PageNotes(page=3, points=["Prepared cards in 0.3 seconds", "Live cards stream from Spark"]),
    ]
    tracker = Tracker(notes, {1: "Problem", 2: "Solution", 3: "Latency"})
    tracker.hear("Many presenters freeze when they get hard questions")
    assert tracker.current.covered == [True, False]

    update = tracker.hear("Cueon builds cards from your own material")
    if not update.moved:  # a weaker match waits for a second sentence
        update = tracker.hear("and they are shown right on the glasses lens")
    assert update.moved and update.page == 2
    assert update.missed == ["Q&A decides the score"]
    assert tracker.hud()["points"][0]["done"]
