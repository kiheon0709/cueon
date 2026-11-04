"""Live-path behaviour: fallback card, speculative start, swiping candidates, repeat card."""

import asyncio

from hub.bank import Bank
from hub.cards import Card
from hub.pipeline import Pipeline
from hub.sources import Document, Library, Page
from hub.workspace import Workspace


class Bus:
    def __init__(self):
        self.shown: list[dict] = []
        self.last: dict = {}

    async def show(self, state, **fields):
        self.last = {"type": "hud", "state": state, **fields}
        self.shown.append({"state": state, **fields})


class SlowModel:
    """Streams a fixed card after `delay` seconds; counts how many answers were started."""

    def __init__(self, delay: float):
        self.delay = delay
        self.calls: list[str] = []

    async def answer_stream(self, library, question):
        self.calls.append(question)
        await asyncio.sleep(self.delay)
        for piece in ["LEAD: Spark answer\n", "- point\n", "SOURCE: DECK p.1\n"]:
            yield piece


def workspace() -> Workspace:
    library = Library(documents=[Document(alias="DECK", name="d", pages=[Page(number=1, title="t", text="t", numbers=set())])])
    bank = Bank()
    bank.add("latency", Card(question="How fast is it?", lead="1.5s", points=[], source="DECK p.1"), ["What's the latency?"])
    bank.add("pricing", Card(question="How much does it cost?", lead="$0.18/h", points=[], source="DECK p.1"), ["What's the price?"])
    return Workspace(library=library, bank=bank)


def test_slow_spark_shows_tentative_bank_card_then_replaces_it(monkeypatch):
    monkeypatch.setattr("hub.pipeline.FALLBACK_S", 0.05)
    bus = Bus()
    pipeline = Pipeline(bus, SlowModel(delay=0.2), workspace())
    asyncio.run(pipeline.answer("does it stay fast on a weak conference wifi network"))
    cards = [m for m in bus.shown if m["state"] == "card"]
    assert cards[0].get("tentative") and cards[0]["lead"] == "1.5s"
    assert cards[-1]["lead"] == "Spark answer" and cards[-1]["live"]
    record = next(iter(pipeline.records.values()))
    assert record["tentative_ms"] < record["first"]


def test_speculative_start_is_reused_for_the_same_question():
    model = SlowModel(delay=0.05)
    pipeline = Pipeline(Bus(), model, workspace())
    pipeline.listening = True
    question = "Who is your biggest competitor in this market?"

    async def run():
        await pipeline.on_event({"type": "transcript", "transcript": question, "final": False})
        await asyncio.sleep(0.03)
        await pipeline.on_event({"type": "speechComplete", "transcript": question})
        await pipeline.wait_idle()

    asyncio.run(run())
    record = next(iter(pipeline.records.values()))
    assert model.calls == [question] and record["speculative"]


def test_speculation_is_cancelled_when_the_question_changes():
    model = SlowModel(delay=0.05)
    pipeline = Pipeline(Bus(), model, workspace())
    pipeline.listening = True

    async def run():
        await pipeline.on_event({"type": "transcript", "transcript": "Who is your biggest competitor here", "final": False})
        await asyncio.sleep(0.01)
        await pipeline.on_event({"type": "speechComplete", "transcript": "Who is your biggest competitor here, and why do you win against Otter and the teleprompter?"})
        await pipeline.wait_idle()

    asyncio.run(run())
    assert len(model.calls) == 2
    assert not next(iter(pipeline.records.values()))["speculative"]


def test_swipe_flips_to_runner_up_and_short_input_asks_to_repeat():
    bus = Bus()
    pipeline = Pipeline(bus, SlowModel(delay=0), workspace())

    async def run():
        await pipeline.answer("What's the latency and price?")
        await pipeline.swipe(1)
        await pipeline.answer("uh")

    asyncio.run(run())
    cards = [m for m in bus.shown if m["state"] == "card"]
    assert cards[0]["choices"] == 2 and cards[1]["choice"] == 2
    assert {cards[0]["lead"], cards[1]["lead"]} == {"1.5s", "$0.18/h"}
    assert bus.shown[-1]["state"] == "repeat"


def test_card_dims_after_reading_time(monkeypatch):
    monkeypatch.setattr("hub.pipeline.DIM_AFTER_S", 0.01)
    bus = Bus()
    pipeline = Pipeline(bus, SlowModel(delay=0), workspace())

    async def run():
        await pipeline.answer("What's the latency?")
        await asyncio.sleep(0.05)

    asyncio.run(run())
    assert bus.shown[-1]["dimmed"] and bus.shown[-1]["lead"] == "1.5s"


def test_spark_failure_still_shows_closest_card_and_swipe_is_reset():
    class FailingModel:
        async def answer_stream(self, library, question):
            raise RuntimeError("503")
            yield ""

    bus = Bus()
    pipeline = Pipeline(bus, FailingModel(), workspace())

    async def run():
        await pipeline.answer("What's the latency?")  # bank card, two candidates
        await pipeline.answer("does it stay fast on a weak conference wifi network")
        shown = len(bus.shown)
        await pipeline.answer("uh")
        await pipeline.swipe(1)  # nothing to swipe for the new question
        return shown

    shown = asyncio.run(run())
    fallback = bus.shown[shown - 1]
    assert fallback["state"] == "card" and fallback["tentative"] and fallback["lead"] == "1.5s"
    assert bus.shown[-1]["state"] == "repeat"


def test_tapping_listen_cancels_the_answer_being_written():
    pipeline = Pipeline(Bus(), SlowModel(delay=1.0), workspace())
    pipeline.listening = True

    async def run():
        await pipeline.on_event({"type": "speechComplete", "transcript": "Who is your biggest competitor here?"})
        await asyncio.sleep(0.05)
        await pipeline.toggle_listen()
        await asyncio.sleep(0.05)

    asyncio.run(run())
    assert next(iter(pipeline.records.values()))["path"] == "cancelled"
    assert pipeline.bus.shown[-1]["state"] == "listening"


def test_question_detection_english_and_korean():
    from hub.pipeline import looks_like_question

    assert looks_like_question("how fast is it")
    assert looks_like_question("레이턴시가 얼마나 되나요")
    assert looks_like_question("경쟁사 대비 뭐가 다른가요")
    assert not looks_like_question("오늘 발표 잘 들었습니다")
    assert not looks_like_question("thanks for the talk")
