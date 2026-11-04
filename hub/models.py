"""Muse Spark calls behind one interface, plus a stand-in that runs without an API key.

The whole library goes into one fixed developer message that every call shares, so Spark's
prompt cache (keyed by prompt_cache_key) serves it after the first call. Only the task in the
user message changes. There is no retrieval step: Spark sees all of the material every time.
"""

import asyncio
import base64
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
    audience: str = ""  # who tends to ask it: investor, technical judge, general audience
    question: str
    variants: list[str] = []
    follow_ups: list[FollowUp] = []


class PageNotes(BaseModel):
    page: int
    points: list[str]  # what the presenter must say on this page
    bridge: str = ""  # line into the next page
    short: str = ""  # one-sentence version for when time runs out
    support: str = ""  # a backing fact from the evidence documents (보충 멘트)
    support_source: str = ""  # where that fact is, "<alias> p.<n>"


class Model(Protocol):
    async def expected_questions(self, library: Library, limit: int) -> list[QuestionPlan]: ...

    async def write_card(self, library: Library, question: str, feedback: list[str]) -> Card | None: ...

    async def judge(self, library: Library, card: Card) -> list[str]: ...

    async def review(self, library: Library, question: str, card: Card) -> list[str]: ...

    def answer_stream(self, library: Library, question: str) -> AsyncIterator[str]: ...

    async def page_notes(self, library: Library) -> list[PageNotes]: ...

    async def keywords(self, library: Library) -> list[str]: ...

    async def chart_numbers(self, image_png: bytes) -> list[str]: ...


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
Think from three seats in the room: an investor (market, business model, competition, traction),
a technical judge (how it works, latency, accuracy, limits), and the general audience (who it's for,
privacy, what it feels like to use). Give at most {limit} question types, most likely first, mixing
the three. Include the hard ones: weaknesses, competitors, numbers, risks, what's next, and the sharp,
multi-part questions an experienced investor asks to test a founder. For each type give:
- qtype: a short slug (e.g. "latency", "competitors")
- audience: "investor", "technical", or "general"
- question: the canonical question
- variants: 4 different ways a person might actually say it out loud (short, spoken style)
- follow_ups: up to 2 likely follow-up questions, each with 3 spoken variants

The lens style above is for cards, not for this list. Write every question and variant as a complete
sentence, exactly as a person would say it out loud in the room (for example "How fast does a card
show up after someone asks?"). Never add page citations or shorthand to them."""

CARD_TASK = """Write the cue card the presenter glances at just before answering this question out loud.
Question: {question}

- lead: what to say first, in plain spoken words, at most 12 words. Answer exactly what was asked and
  name the specific thing (a number, a name, a step). Don't restate the topic or use a slogan.
- points: up to 3, at most 10 words each, strongest first. Give concrete evidence from the material,
  then the answer to any other part of the question or the objection behind it.
- source: the one page that supports the card, as "<alias> p.<n>"
A bare fact is never enough. When the honest answer is weak (no users, no revenue), pair it with the
strongest real evidence in the material and the next step, as a confident founder would.
Every number on the card must appear on the cited page.
If the material can't answer the question, set answerable to false."""

REVIEW_TASK = """A sharp investor asked: "{question}"
The presenter's cue card says:
{card}
Would this card let the presenter give a strong, specific answer? List concrete weaknesses, each as a
fix: it restates the topic, skips part of the question, gives a bare fact with no evidence or next step,
or misses stronger evidence that the material has. Return an empty list if it's good."""

FEEDBACK = "\n\nYour last draft was rejected. Fix these problems:\n{problems}"

JUDGE_TASK = """Check this cue card against page {source} of the material, and only that page.
Card: {card}
List every statement on the card that page does not support. Return an empty list if everything is supported."""

LIVE_TASK = """An investor or judge just asked the presenter: "{question}"
Write the cue card to glance at before answering, in exactly this plain text, nothing else:
LEAD: <what to say first, spoken words, at most 12 words, naming the specific thing>
- <strongest evidence from the material, with a number or name, at most 10 words>
- <the other part of the question, or the answer to the objection, at most 10 words>
SOURCE: <alias> p.<n>
Reason from the material; label hypotheses. Never restate the topic or use a slogan.
If the material can't support an answer, leave out SOURCE and suggest how a sharp founder would reason
about it, with no invented facts or numbers."""

NOTES_TASK = """For every page of the main document ({alias}), write the notes the presenter glances at while showing it:
- page: the page number
- points: 2-4 key points the presenter must say on this page, at most 8 words each
- bridge: one short line that leads into the next page
- short: a one-sentence version of the page for when time runs out
- support: one extra fact from the evidence documents that backs up this page, at most 12 words,
  or "" if there is none. Never take it from the page itself.
- support_source: where that fact is, as "<alias> p.<n>", or "" """

KEYWORDS_TASK = """List up to 40 terms a speech recognizer might mishear in questions about this material:
product and company names, people, acronyms, jargon, unusual words. Most important first."""

CHART_TASK = """This is one page of a presentation. List every number shown in its charts, graphs, and tables
exactly as printed (for example "61%", "1.4", "$2.3M"). Ignore page numbers. Return an empty list if there are none."""

QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "types": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "qtype": {"type": "string"},
                    "audience": {"type": "string", "enum": ["investor", "technical", "general"]},
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
                "required": ["qtype", "audience", "question", "variants", "follow_ups"],
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

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"weaknesses": {"type": "array", "items": {"type": "string"}}},
    "required": ["weaknesses"],
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
                    "support": {"type": "string"},
                    "support_source": {"type": "string"},
                },
                "required": ["page", "points", "bridge", "short", "support", "support_source"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["pages"],
    "additionalProperties": False,
}

TERMS_SCHEMA = {
    "type": "object",
    "properties": {"terms": {"type": "array", "items": {"type": "string"}}},
    "required": ["terms"],
    "additionalProperties": False,
}

NUMBERS_SCHEMA = {
    "type": "object",
    "properties": {"numbers": {"type": "array", "items": {"type": "string"}}},
    "required": ["numbers"],
    "additionalProperties": False,
}


def parse_json(text: str | None) -> dict:
    """Parse a JSON object reply, tolerating a markdown fence or text around it."""
    text = (text or "").strip()
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


# ---------------------------------------------------------------------------------------------
# Muse Spark


class SparkModel:
    def __init__(
        self, api_key: str, base_url: str = config.BASE_URL, model: str = config.SPARK_MODEL, http_client=None
    ) -> None:
        from openai import AsyncOpenAI  # the SDK does not read MODEL_API_KEY itself

        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=60, max_retries=2, http_client=http_client)
        self.model = model
        self.cache_stats: list[dict] = []  # per call: prompt and cached tokens, for the console
        self._plain_json = False  # set if the server turns out not to support json_schema
        self._prefix_role = "developer"  # cookbook default; falls back to "system" if rejected

    backend = "spark"

    def _options(self, cache_key: str, effort: str) -> dict:
        """Model-specific request fields: Spark's prompt cache key and reasoning effort."""
        return {"prompt_cache_key": cache_key, "reasoning_effort": effort}

    def _messages(self, library: Library, task: str) -> tuple[list[dict], str]:
        prefix = INSTRUCTIONS + library.as_prompt()
        key = "cueon-" + hashlib.sha256(prefix.encode()).hexdigest()[:16]
        return [{"role": self._prefix_role, "content": prefix}, {"role": "user", "content": task}], key

    async def _create(self, **kwargs):
        """chat.completions.create, switching the prefix to the system role if 'developer' is rejected."""
        from openai import BadRequestError

        try:
            return await self.client.chat.completions.create(**kwargs)
        except BadRequestError as error:
            messages = kwargs.get("messages") or []
            if self._prefix_role != "developer" or "role" not in str(error).lower() or not messages:
                raise
            log.warning("developer role rejected; using system role from now on")
            self._prefix_role = "system"
            if messages[0].get("role") == "developer":
                kwargs["messages"] = [{**messages[0], "role": "system"}, *messages[1:]]
            return await self.client.chat.completions.create(**kwargs)

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
        """Structured output. If the server rejects json_schema, fall back to JSON mode with the
        schema in the prompt, so one unsupported parameter doesn't stop prep."""
        from openai import BadRequestError

        messages, key = self._messages(library, task)
        started = time.perf_counter()
        if not self._plain_json:
            try:
                response = await self._create(
                    model=self.model,
                    messages=messages,
                    **self._options(key, effort),
                    response_format={"type": "json_schema", "json_schema": {"name": task_name, "schema": schema}},
                )
                self._record(task_name, response.usage, started)
                return parse_json(response.choices[0].message.content)
            except BadRequestError as error:
                log.warning("json_schema rejected (%s); using JSON mode from now on", error)
                self._plain_json = True
        messages[-1] = {
            "role": "user",
            "content": f"{task}\n\nReply with only a JSON object matching this schema:\n{json.dumps(schema)}",
        }
        response = await self._create(
            model=self.model, messages=messages, **self._options(key, effort), response_format={"type": "json_object"}
        )
        self._record(task_name, response.usage, started)
        return parse_json(response.choices[0].message.content)

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

    async def review(self, library: Library, question: str, card: Card) -> list[str]:
        shown = cardtext.format(card).strip().replace("\n", " | ")
        data = await self._json(library, "review", REVIEW_TASK.format(question=question, card=shown), REVIEW_SCHEMA, "low")
        return [f"Weak answer: {w}" for w in data.get("weaknesses", [])]

    async def judge(self, library: Library, card: Card) -> list[str]:
        shown = cardtext.format(card).strip().replace("\n", " | ")
        data = await self._json(library, "judge", JUDGE_TASK.format(source=card.source, card=shown), JUDGE_SCHEMA, "low")
        return [f"Not supported by {card.source}: {s}" for s in data.get("unsupported", [])]

    async def answer_stream(self, library: Library, question: str) -> AsyncIterator[str]:
        messages, key = self._messages(library, LIVE_TASK.format(question=question))
        started = time.perf_counter()
        stream = await self._create(
            model=self.model,
            messages=messages,
            **self._options(key, "minimal"),
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

    async def keywords(self, library: Library) -> list[str]:
        data = await self._json(library, "keywords", KEYWORDS_TASK, TERMS_SCHEMA, "low")
        return [t.strip() for t in data.get("terms", []) if t.strip()][:50]

    async def chart_numbers(self, image_png: bytes) -> list[str]:
        """Read the numbers in a page's charts and tables (vision input, no material prefix)."""
        url = "data:image/png;base64," + base64.b64encode(image_png).decode()
        started = time.perf_counter()
        response = await self._create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [{"type": "text", "text": CHART_TASK}, {"type": "image_url", "image_url": {"url": url}}],
                }
            ],
            response_format={"type": "json_schema", "json_schema": {"name": "chart_numbers", "schema": NUMBERS_SCHEMA}},
            **self._options("cueon-vision", "low"),
        )
        self._record("vision", response.usage, started)
        data = json.loads(response.choices[0].message.content or "{}")
        return [str(n) for n in data.get("numbers", [])]

    async def warm(self, library: Library) -> None:
        """Send the prefix once so the first live question hits a warm cache."""
        messages, key = self._messages(library, "Reply with OK.")
        started = time.perf_counter()
        response = await self._create(
            model=self.model, messages=messages, **self._options(key, "minimal")
        )
        self._record("warm", response.usage, started)


class GlimmerModel(SparkModel):
    """Local mode: Muse Glimmer on the presenter's own machine, so the material never leaves it.

    Any OpenAI-compatible runtime works (llama.cpp `llama-server` on :8080 by default, Ollama,
    vLLM, SGLang). The runtime keeps the shared prefix in its KV cache on its own, so there is no
    cache key, and reasoning effort is left to the server's settings.
    """

    backend = "glimmer"

    def __init__(self, base_url: str = config.LOCAL_BASE_URL, model: str = config.LOCAL_MODEL, http_client=None) -> None:
        super().__init__("local-only", base_url=base_url, model=model, http_client=http_client)
        self.client.timeout = 300  # a 30B model on a laptop is slower than the API

    def _options(self, cache_key: str, effort: str) -> dict:
        return {}


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

    backend = "stand-in"

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

    async def review(self, library: Library, question: str, card: Card) -> list[str]:
        return []

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

    async def keywords(self, library: Library) -> list[str]:
        return [p.title for d in library.documents for p in d.pages][:50]

    async def chart_numbers(self, image_png: bytes) -> list[str]:
        return []

    async def warm(self, library: Library) -> None:
        return None


def make_model() -> Model:
    if config.BACKEND == "glimmer":
        log.info("Local mode: Muse Glimmer at %s (%s)", config.LOCAL_BASE_URL, config.LOCAL_MODEL)
        return GlimmerModel()
    key = config.api_key()
    if config.fake_mode() or key is None:
        log.info("Using the stand-in model (no MODEL_API_KEY or CUEON_FAKE=1)")
        return FakeModel()
    log.info("Using Muse Spark (%s)", config.SPARK_MODEL)
    return SparkModel(key)
