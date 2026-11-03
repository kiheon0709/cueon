"""Muse Spark calls behind one interface, plus a stand-in that runs without an API key.

The whole library goes into one fixed developer message that every call shares, so Spark's
prompt cache (keyed by prompt_cache_key) serves it after the first call. Only the task in the
user message changes. There is no retrieval step: Spark sees all of the material every time.
"""

import asyncio
import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel

from hub import cardtext, config
from hub.cards import Card
from hub.similarity import similarity
from hub.sources import Library, Page

log = logging.getLogger("cueon.models")


class FollowUp(BaseModel):
    question: str
    variants: list[str] = []


class QuestionPlan(BaseModel):
    """One question type: the canonical question, how people might phrase it, and what comes next."""

    qtype: str
    question: str
    variants: list[str] = []
    follow_ups: list[FollowUp] = []


class PageNotes(BaseModel):
    page: int
    points: list[str]  # what the presenter must say on this page
    bridge: str = ""  # line into the next page
    short: str = ""  # one-sentence version for when time runs out


class Model(Protocol):
    async def expected_questions(self, library: Library, limit: int) -> list[QuestionPlan]: ...

    async def write_card(self, library: Library, question: str, feedback: list[str]) -> Card | None: ...

    async def judge(self, library: Library, card: Card) -> list[str]: ...

    def answer_stream(self, library: Library, question: str) -> AsyncIterator[str]: ...

    async def page_notes(self, library: Library) -> list[PageNotes]: ...


# ---------------------------------------------------------------------------------------------
# Prompts

INSTRUCTIONS = """You are Cueon, the assistant for a presenter who wears smart glasses during a talk.
The presenter's material follows. Everything you write must come from this material.
Cite pages exactly as the headings show them: "<alias> p.<n>", for example "BP p.12".
Never invent numbers, names, dates, or facts. Write in the language the material is written in.
Cards are read at a glance on a small lens: short phrases, no full sentences, no filler.

=== MATERIAL ===
"""

QUESTIONS_TASK = """List the questions the audience or a judging panel is most likely to ask after this talk.
Give at most {limit} question types, most likely first. Include the hard ones: weaknesses, competitors,
numbers, risks, what's next. For each type give:
- qtype: a short slug (e.g. "latency", "competitors")
- question: the canonical question
- variants: 4 different ways a person might actually say it out loud (short, spoken style)
- follow_ups: up to 2 likely follow-up questions, each with 3 spoken variants"""

CARD_TASK = """Write a cue card that answers this question from the material.
Question: {question}

- lead: the answer itself, at most 10 words
- points: up to 3 supporting points, at most 8 words each
- source: the one page that supports the card, as "<alias> p.<n>"
Every number on the card must appear on the cited page.
If the material can't answer the question, set answerable to false."""

FEEDBACK = "\n\nYour last draft was rejected. Fix these problems:\n{problems}"

JUDGE_TASK = """Check this cue card against page {source} of the material, and only that page.
Card: {card}
List every statement on the card that page does not support. Return an empty list if everything is supported."""

LIVE_TASK = """Someone in the audience just asked: "{question}"
Answer as a cue card in exactly this plain-text format, nothing else:
LEAD: <the answer, at most 10 words>
- <point, at most 8 words>
- <point, at most 8 words>
SOURCE: <alias> p.<n>
If the material doesn't cover it, write "LEAD: Not in your material" and one point on how to respond honestly."""

NOTES_TASK = """For every page of the main document ({alias}), write the notes the presenter glances at while showing it:
- page: the page number
- points: 2-4 key points the presenter must say on this page, at most 8 words each
- bridge: one short line that leads into the next page
- short: a one-sentence version of the page for when time runs out"""

QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "types": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "qtype": {"type": "string"},
                    "question": {"type": "string"},
                    "variants": {"type": "array", "items": {"type": "string"}},
                    "follow_ups": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "variants": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["question", "variants"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["qtype", "question", "variants", "follow_ups"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["types"],
    "additionalProperties": False,
}

CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "answerable": {"type": "boolean"},
        "lead": {"type": "string"},
        "points": {"type": "array", "items": {"type": "string"}},
        "source": {"type": "string"},
    },
    "required": ["answerable", "lead", "points", "source"],
    "additionalProperties": False,
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"unsupported": {"type": "array", "items": {"type": "string"}}},
    "required": ["unsupported"],
    "additionalProperties": False,
}

NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer"},
                    "points": {"type": "array", "items": {"type": "string"}},
                    "bridge": {"type": "string"},
                    "short": {"type": "string"},
                },
                "required": ["page", "points", "bridge", "short"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["pages"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------------------------
# Muse Spark


class SparkModel:
    def __init__(self, api_key: str, base_url: str = config.BASE_URL, model: str = config.SPARK_MODEL) -> None:
        from openai import AsyncOpenAI  # the SDK does not read MODEL_API_KEY itself

        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=60, max_retries=2)
        self.model = model
        self.cache_stats: list[dict] = []  # per call: prompt and cached tokens, for the console

    def _messages(self, library: Library, task: str) -> tuple[list[dict], str]:
        prefix = INSTRUCTIONS + library.as_prompt()
        key = "cueon-" + hashlib.sha256(prefix.encode()).hexdigest()[:16]
        return [{"role": "developer", "content": prefix}, {"role": "user", "content": task}], key

    def _record(self, task: str, usage, started: float) -> None:
        if usage is None:
            return
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details else 0
        self.cache_stats.append(
            {"task": task, "prompt": usage.prompt_tokens, "cached": cached or 0, "ms": (time.perf_counter() - started) * 1000}
        )
        self.cache_stats = self.cache_stats[-200:]

    async def _json(self, library: Library, task_name: str, task: str, schema: dict, effort: str) -> dict:
        messages, key = self._messages(library, task)
        started = time.perf_counter()
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            prompt_cache_key=key,
            reasoning_effort=effort,
            response_format={"type": "json_schema", "json_schema": {"name": task_name, "schema": schema, "strict": True}},
        )
        self._record(task_name, response.usage, started)
        return json.loads(response.choices[0].message.content or "{}")

    async def expected_questions(self, library: Library, limit: int) -> list[QuestionPlan]:
        data = await self._json(library, "questions", QUESTIONS_TASK.format(limit=limit), QUESTIONS_SCHEMA, "medium")
        return [QuestionPlan.model_validate(t) for t in data.get("types", [])][:limit]

    async def write_card(self, library: Library, question: str, feedback: list[str]) -> Card | None:
        task = CARD_TASK.format(question=question)
        if feedback:
            task += FEEDBACK.format(problems="\n".join(f"- {p}" for p in feedback))
        data = await self._json(library, "card", task, CARD_SCHEMA, "low")
        if not data.get("answerable"):
            return None
        return Card(question=question, lead=data["lead"], points=data["points"], source=data["source"])

    async def judge(self, library: Library, card: Card) -> list[str]:
        shown = cardtext.format(card).strip().replace("\n", " | ")
        data = await self._json(library, "judge", JUDGE_TASK.format(source=card.source, card=shown), JUDGE_SCHEMA, "low")
        return [f"Not supported by {card.source}: {s}" for s in data.get("unsupported", [])]

    async def answer_stream(self, library: Library, question: str) -> AsyncIterator[str]:
        messages, key = self._messages(library, LIVE_TASK.format(question=question))
        started = time.perf_counter()
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            prompt_cache_key=key,
            reasoning_effort="minimal",
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
            if chunk.usage:
                self._record("live", chunk.usage, started)

    async def page_notes(self, library: Library) -> list[PageNotes]:
        main = library.main()
        if main is None:
            return []
        data = await self._json(library, "notes", NOTES_TASK.format(alias=main.alias), NOTES_SCHEMA, "low")
        return [PageNotes.model_validate(p) for p in data.get("pages", [])]

    async def warm(self, library: Library) -> None:
        """Send the prefix once so the first live question hits a warm cache."""
        messages, key = self._messages(library, "Reply with OK.")
        started = time.perf_counter()
        response = await self.client.chat.completions.create(
            model=self.model, messages=messages, prompt_cache_key=key, reasoning_effort="minimal", max_tokens=5
        )
        self._record("warm", response.usage, started)


# ---------------------------------------------------------------------------------------------
# Stand-in


def _clip(text: str, words: int) -> str:
    parts = text.split()
    return " ".join(parts[:words])


def _content_lines(page: Page) -> list[str]:
    lines = [line.strip(" •-*\t") for line in page.text.splitlines()]
    return [line for line in lines if line and line != page.title][:6]


class FakeModel:
    """Answers from the material with plain text matching, so the whole app runs without a key."""

    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.cache_stats: list[dict] = []

    def _best_page(self, library: Library, question: str) -> tuple[str, Page] | None:
        scored = [
            (similarity(question, page.title + " " + page.text), doc.alias, page)
            for doc in library.documents
            for page in doc.pages
        ]
        if not scored:
            return None
        score, alias, page = max(scored, key=lambda s: s[0])
        return (alias, page) if score >= 0.12 else None

    async def expected_questions(self, library: Library, limit: int) -> list[QuestionPlan]:
        await asyncio.sleep(self.delay)
        main = library.main()
        plans = []
        for page in (main.pages[1:] if main else [])[:limit]:
            topic = page.title.rstrip("?.!:")
            plans.append(
                QuestionPlan(
                    qtype=re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-") or f"p{page.number}",
                    question=f"Can you say more about {topic.lower()}?",
                    variants=[f"How does {topic.lower()} work?", f"What about {topic.lower()}?", f"Tell me about {topic.lower()}"],
                    follow_ups=[FollowUp(question=f"What backs up your {topic.lower()} numbers?", variants=[f"How do you know that about {topic.lower()}?"])],
                )
            )
        return plans

    async def write_card(self, library: Library, question: str, feedback: list[str]) -> Card | None:
        await asyncio.sleep(self.delay)
        found = self._best_page(library, question)
        if found is None:
            return None
        alias, page = found
        lines = _content_lines(page) or [page.title]
        return Card(
            question=question,
            lead=_clip(lines[0], 10),
            points=[_clip(line, 8) for line in lines[1:4]],
            source=f"{alias} p.{page.number}",
        )

    async def judge(self, library: Library, card: Card) -> list[str]:
        return []

    async def answer_stream(self, library: Library, question: str) -> AsyncIterator[str]:
        card = await self.write_card(library, question, [])
        if card is None:
            text = "LEAD: Not in your material\n- Say you'll follow up after the talk\n"
        else:
            text = cardtext.format(card)
        for i in range(0, len(text), 12):
            await asyncio.sleep(self.delay / 5)
            yield text[i : i + 12]

    async def page_notes(self, library: Library) -> list[PageNotes]:
        await asyncio.sleep(self.delay)
        main = library.main()
        notes = []
        for page in main.pages if main else []:
            lines = _content_lines(page) or [page.title]
            notes.append(PageNotes(page=page.number, points=[_clip(line, 8) for line in lines[:3]], short=_clip(lines[0], 15)))
        return notes

    async def warm(self, library: Library) -> None:
        return None


def make_model() -> Model:
    key = config.api_key()
    if config.fake_mode() or key is None:
        log.info("Using the stand-in model (no MODEL_API_KEY or CUEON_FAKE=1)")
        return FakeModel()
    log.info("Using Muse Spark (%s)", config.SPARK_MODEL)
    return SparkModel(key)
