# Measured results

Everything here ran on the real Muse Spark and Muse Voice Transcribe on a laptop, on Nov 5, 2026, early morning
Korea time. These are small runs from one machine, so read them as a first measurement, not a benchmark. Nothing
has been measured on real glasses yet.

## Typed investor questions

20 typed questions (`eval/data/ir-questions.csv`) on our own pitch material, which isn't in this repo. Speech
recognition isn't included. Time starts when the question is complete.

| Path | Questions | First text p50 | p95 |
|---|---|---|---|
| Prepared card | 7 of 20 | 4 ms | 4 ms |
| New card from Muse Spark | 13 of 20 | 5.1 s | 7.0 s |

An earlier run the same morning, on the same code path, had 6.4 s and 7.9 s for new cards, so read this as 5 to 6 s.
Our target for a card on the lens is 1.5 s p50 and 2.5 s p95. Prepared cards meet it. New questions don't.
About 95% of input tokens on live calls came from the prompt cache.

The same questions can be run with `uv run python -m eval.bench --questions eval/data/ir-questions.csv`, and the
raw numbers from the last run are in [latency.md](latency.md) and `latency.json`.

## Spoken questions, stage by stage

Scripted speech played through the browser microphone path: three takes of five long questions, so 15 questions.
One was a prepared card in all three takes, and four were new. Times run from the end of the speech, read from
the lens view, which is polled every 120 ms.

| Stage | Time after the speech ends |
|---|---|
| End of turn from Muse Voice Transcribe | 0.6 to 1.1 s, median 0.9 s |
| Prepared card on the lens | 0.6 to 0.7 s |
| Stalling line on the lens, new question | 0.5 to 0.8 s |
| Closest prepared card, if one is close enough | about 2 s |
| Final card from Muse Spark, new question | 4.8 to 9.4 s, median 5.8 s |

Local matching takes under 10 ms of this. For new questions, most of the wait is Spark's time to the first text.

Spark's response time varies a lot from call to call: up to 23 s in one test of 10 questions. Asking twice and keeping
whichever call starts first cut the slowest case from 23 s to 9 s in that test, but barely moved the median. It costs up to
twice the input per new question.

## Matching

40 labelled questions about the sample deck (`eval/data/questions.csv`), 34 answerable and 6 out of scope, against 22
prepared cards. At the threshold we use, 0.62, nothing wrong was shown and all 6 out-of-scope questions stayed out,
but only 3 of the 34 got a prepared card and 31 went to the slower live path. See [matching.md](matching.md) for
every threshold. We raised it from 0.42 because a wrong card shown instantly is worse than a slower right one. On our
pitch material, with 58 cards, 7 of 20 questions got a prepared card, so more preparation helps.

## What we haven't measured

Real Ray-Ban Display render time, noisy rooms, accented speech, and whether Cueon helps people answer better. The
protocol for that pilot is in `eval/experiment/`, and it hasn't been run.
