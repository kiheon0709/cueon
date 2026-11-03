# Submission text (draft)

Fill the bracketed numbers from the benchmark before submitting. Don't claim anything that wasn't run.

## Name
Cueon — live Q&A cue cards on Meta Ray-Ban Display

## One line
Cueon listens to audience questions and puts a checked answer from your own slides, plans and
data on your Ray-Ban Display lens, in about a second.

## What it does
Q&A is the part of a talk you can't rehearse: you mishear the question, the number won't come,
the pause gets long. Cueon prepares before the talk and helps during it.

- **Before:** upload slides, business plan, papers and data. A Prep Agent on Muse Spark predicts
  the questions an investor, a technical judge and the audience would ask, writes a short cue card
  for each, and checks it: every number must be on the page it cites (`BP p.12`), and a judge model
  checks every claim. Rejected cards are rewritten up to three times; what your material can't
  support is shown as a gap to fix.
- **While presenting:** Cueon follows along page by page from what you say, ticks off key points,
  warns when you skip one, and counts down your time. No model calls on stage.
- **In Q&A:** pinch to listen. A prepared card appears as soon as Muse Voice Transcribe hears the
  question end. New questions are answered on the spot by Muse Spark from the whole deck, marked
  as unchecked; out-of-scope questions get “Not in your material” instead of a made-up answer.

## How we built it
- Muse Voice Transcribe realtime (ENDPOINTING, keyword biasing from prep) for turn detection.
- Muse Spark 1.3 for prep (structured output, vision for chart numbers, LLM-as-judge) and the live
  path (streaming, `reasoning_effort=minimal`), with the entire material in one cached prefix
  (`prompt_cache_key`). No vector retrieval.
- Latency engineering: local matching against the prepared bank; speculative Spark requests from
  partial transcripts; a fallback card at 1.2 s; stage timings logged for every question.
- Local mode on Muse Glimmer through any OpenAI-compatible runtime, for confidential decks.
- Ray-Ban Display web app built with the Meta Wearables UI Toolkit; passes Meta's webapp checker.
- FastAPI hub, React console.

## Results
- Latency, end of question → card on the lens: prepared cards p50 [ ] ms / p95 [ ] ms; live Spark
  cards p50 [ ] ms / p95 [ ] ms ([n] questions, `eval/bench.py`).
- Prepared-card hit rate on 34 answerable test questions: [ ]%; wrong card shown: [ ].
- Prep checks: [ ] of [ ] cards passed on the first draft, [ ] fixed after feedback, [ ] rejected.
- Pilot (if run): [n] participants, no help vs Cueon, answer start and accuracy.

## Challenges
Keeping the live path fast without giving up correctness: we moved checking to before the talk,
show checked cards unchanged, and label anything written live.

## Bonus categories
Best Agentic (Prep Agent with mandatory checks and retry loop), Open Weights (Glimmer local mode),
Most Viral, Community Vote.

## Built during the hackathon
All code was written Oct 26 – Nov 4, 2026.
