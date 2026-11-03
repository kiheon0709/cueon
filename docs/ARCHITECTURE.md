# Cueon architecture

Cueon has two moments: **before the talk**, an agent prepares and checks everything it can; **during
the talk**, a latency-first loop shows the right thing on the lens. The model does its expensive
work in the first part so the second part rarely has to wait for it.

```
 laptop / phone mic ──PCM16 24 kHz──▶ hub (FastAPI, on the presenter's laptop)
                                       │
       ┌── Muse Voice Transcribe  (wss, ENDPOINTING, keywords from prep)
       │        │ partial transcripts / speechComplete
       │        ▼
       ├── Presentation mode: sentence ↔ page notes  → page, ✓ points, skipped, time left
       ├── Q&A mode: card bank match (local, ~1 ms)
       │        ├─ hit  → prepared card, unchanged
       │        └─ miss → Muse Spark stream (cached material prefix, minimal effort)
       │                   ├─ speculative start from the partial transcript
       │                   └─ fallback: closest prepared card at 1.2 s, replaced when Spark answers
       └── HUD bus (WebSocket /hud) ──▶ Ray-Ban Display web app (600×600, UI Toolkit)
                                          └─ render ack → latency log

 presenter console (web) ── upload · prepare · edit cards · gaps · rehearse · latency
```

## Material

`hub/sources.py` turns each upload into a `Document` with an alias (`DECK`, `BP`, `STUDY`) and a
role: **main** is what the talk follows, **evidence** backs it up. PDFs become pages of text;
CSVs become pages of 40 rows. Each page keeps the numbers it supports. Citations everywhere are
`ALIAS p.N`.

The whole library is rendered once into a fixed developer message (`Library.as_prompt`). Every
Spark call sends that same prefix with the same `prompt_cache_key`, and only the task in the user
message changes, so after the first call the material is served from Spark's prompt cache. There
is no vector search: the model sees all of the material on every call.

## Prep Agent (`hub/prep.py`)

1. **Charts:** pages with images or drawings are rendered, and Spark reads the numbers in their
   charts and tables. Those numbers join the page's citable numbers.
2. **Expected questions:** Spark predicts question types from three seats (investor, technical
   judge, general audience), each with spoken-style phrasings and follow-ups.
3. **Cards, checked:** each question gets a card written by Spark and saved only through
   `save_card` (`hub/verify.py`), which the agent can't skip:
   - deterministic checks: lead ≤ 12 words, ≤ 3 points, the citation is a real page, every
     number on the card is on that page;
   - then an LLM judge checks each claim against the cited page.
   A rejected card goes back to the writer with the problems, up to 3 times. What still fails
   becomes a **gap** the presenter resolves in the console.
4. **Presentation notes:** key points, a bridge line, a short version, and one supporting fact
   from the evidence documents per page; supporting facts and points pass the same number check.
5. **Recognition terms:** Spark picks up to 40 names and terms for speech-recognition biasing.

The result is the **card bank** (`hub/bank.py`): one checked card per question type, the
phrasings it should match, and its follow-ups linked to it.

## Live loop (`hub/pipeline.py`)

**Q&A.** The presenter pinches to listen (push-to-listen). When Voice Transcribe reports the turn
complete, the question is matched against every phrasing in the bank with a local
character-trigram/word cosine similarity (`hub/similarity.py`), with a bonus for follow-ups of
the card just shown. Above the threshold the prepared card is shown exactly as it was checked.
Below it, Spark streams a card in a plain-text line format; the lead line goes to the lens as soon
as it is complete, and the card is marked *Live · unchecked*. Two latency tricks:

- **Speculative start:** a partial transcript that already reads like a whole question (≥ 5
  words, question form, not in the bank) starts the Spark request early. If the final question
  is the same, its answer is reused; otherwise it's cancelled.
- **Fallback:** if Spark has no lead after 1.2 s, the closest prepared card is shown as
  *Closest prepared* and replaced when Spark's card arrives.

Left/right swipe flips to the runner-up card. A card dims after 10 s so the presenter looks back
at the audience.

**Presentation.** No model call during the talk. Each sentence is compared with the page notes in
a window around the current page; a page change needs a strong match or two sentences in a row.
Points are ticked off as they're said; moving on with points open shows **Skipped**. With a talk
length set, the glasses count down, say *speed up* when fewer pages are done than the clock says,
and show the page's short version in the last minute.

## Measurement

Every question is logged (`data/questions.jsonl`) with its path, match score, whether it started
early or showed a fallback, and timings from the end of the question to the first card text and
to the glasses rendering it (the glasses acknowledge each render). The console shows p50/p95 per
path and the prepared-card hit rate; `eval/` has the benchmarks.

## Local mode

`MODEL_BACKEND=glimmer` points the same prompts at Muse Glimmer on any OpenAI-compatible local
runtime, so the material never leaves the laptop. Only question audio goes to Voice Transcribe.

## Privacy

Push-to-listen in Q&A; audio is streamed, never stored; no speaker identification; no camera.
