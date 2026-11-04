"""The real Spark client, run against a local OpenAI-compatible fake (no key, no network)."""

import asyncio

import httpx
import pymupdf
import pytest

from hub.models import SparkModel
from hub.prep import build_bank
from hub.sources import Library, parse_file
from tests.fake_openai import make_server

ANSWERS = {
    "review": {"weaknesses": []},
    "questions": {"types": [{"qtype": "latency", "question": "How fast is it?", "variants": ["What's the latency?"],
                             "follow_ups": [{"question": "And p95?", "variants": ["What about the worst case?"]}]}]},
    "card": {"answerable": True, "lead": "Card in 1.4s", "points": ["p95 2.3s"], "source": "DECK p.2"},
    "judge": {"unsupported": []},
    "notes": {"pages": [{"page": 1, "points": ["Live Q&A cue cards"], "bridge": "So how fast?", "short": "Cue cards."}]},
}
LIVE = "LEAD: Card in 1.4s\n- p95 2.3s\nSOURCE: DECK p.2\n"


@pytest.fixture
def library(tmp_path):
    path = tmp_path / "deck.pdf"
    with pymupdf.open() as doc:
        for text in ["Cueon\nLive Q&A cue cards", "Latency\nCard in 1.4s, p95 2.3s"]:
            doc.new_page().insert_text((72, 72), text)
        doc.save(path)
    lib = Library()
    lib.add(parse_file(path, alias="DECK"))
    return lib


def make_model():
    server = make_server(ANSWERS, LIVE)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://spark")
    return SparkModel("LLM|1|test", base_url="http://spark/v1", http_client=client), server


def test_prep_requests_follow_the_cookbook(library):
    model, server = make_model()
    result = asyncio.run(build_bank(model, library))
    assert [e.card.lead for e in result.bank.entries] == ["Card in 1.4s", "Card in 1.4s"]
    assert result.bank.entries[1].parent == result.bank.entries[0].id

    requests = server.state.requests
    assert all(r["model"] == "muse-spark-1.3" for r in requests)
    # One stable prefix and cache key across every call; only the user message changes.
    assert len({r["prompt_cache_key"] for r in requests}) == 1
    assert len({r["messages"][0]["content"] for r in requests}) == 1
    assert requests[0]["messages"][0]["role"] == "developer" and "## DECK p.2" in requests[0]["messages"][0]["content"]
    assert {r["response_format"]["json_schema"]["name"] for r in requests} == {"questions", "card", "judge", "review"}
    assert model.cache_stats[0]["cached"] == 4800


def test_live_answer_streams_with_minimal_effort(library):
    model, server = make_model()

    async def run():
        return "".join([piece async for piece in model.answer_stream(library, "How fast?")])

    assert asyncio.run(run()) == LIVE
    request = server.state.requests[-1]
    assert request["stream"] and request["reasoning_effort"] == "minimal"
    assert request["stream_options"] == {"include_usage": True}
    assert model.cache_stats[-1]["task"] == "live"


def test_notes_and_warm(library):
    model, server = make_model()
    notes = asyncio.run(model.page_notes(library))
    assert notes[0].bridge == "So how fast?"
    asyncio.run(model.warm(library))
    assert server.state.requests[-1]["reasoning_effort"] == "minimal"


def test_glimmer_local_mode_uses_the_same_prompts_without_cloud_fields(library):
    from hub.models import GlimmerModel

    server = make_server(ANSWERS, LIVE)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://local")
    model = GlimmerModel(base_url="http://local/v1", http_client=client)
    result = asyncio.run(build_bank(model, library))
    assert len(result.bank.entries) == 2
    requests = server.state.requests
    assert all(r["model"] == "muse-glimmer-30b" for r in requests)
    assert not any("prompt_cache_key" in r or "reasoning_effort" in r for r in requests)
    assert len({r["messages"][0]["content"] for r in requests}) == 1  # same prefix → runtime KV cache reuse


def test_falls_back_to_json_mode_when_schema_is_rejected(library):
    server = make_server(ANSWERS, LIVE, reject_schema=True)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://spark")
    model = SparkModel("LLM|1|test", base_url="http://spark/v1", http_client=client)
    result = asyncio.run(build_bank(model, library))
    assert [e.card.lead for e in result.bank.entries] == ["Card in 1.4s", "Card in 1.4s"]
    formats = [r["response_format"]["type"] for r in server.state.requests]
    assert formats[0] == "json_schema" and set(formats[1:]) == {"json_object"}  # tried once, then remembered


def test_falls_back_to_system_role(library):
    server = make_server(ANSWERS, LIVE, reject_developer=True)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://spark")
    model = SparkModel("LLM|1|test", base_url="http://spark/v1", http_client=client)
    result = asyncio.run(build_bank(model, library))
    assert len(result.bank.entries) == 2

    async def live():
        return "".join([p async for p in model.answer_stream(library, "How fast?")])

    assert asyncio.run(live()) == LIVE
    roles = [r["messages"][0]["role"] for r in server.state.requests]
    assert roles[0] == "developer" and set(roles[1:]) == {"system"}
