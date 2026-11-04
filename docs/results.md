# Measured results

Everything here ran on the real Muse Spark and Muse Voice Transcribe on a laptop, on Nov 5, 2026. These are
small runs from one machine, so read them as a first measurement, not a benchmark. Nothing has been measured on
real glasses yet.

## Latency on investor questions

20 typed questions (`eval/data/ir-questions.csv`) on our own pitch material, which isn't in this repo. Speech
recognition isn't included. Time starts when the question is complete.

| Path | Questions | First text p50 | p95 |
|---|---|---|---|
| Prepared card | 6 of 20 | 7 ms | 10 ms |
| New card from Muse Spark | 14 of 20 | 4.3 s | 6.3 s |

New questions show the closest prepared card at about 1.2 s until Spark's card arrives. Our target for a card on the
lens is 1.5 s p50 and 2.5 s p95. Prepared cards meet it. New questions don't yet.

The same questions can be run with `uv run python -m eval.bench --questions eval/data/ir-questions.csv`.

## Spoken questions

Scripted speech fed through the browser microphone path, one take of four questions. Time runs from the end of the
speech to the final card on the view.

| Path | Time |
|---|---|
| Prepared card | 0.7 s |
| New card from Muse Spark | 4.7 to 9.3 s |

## Matching

40 labelled questions about the sample deck (`eval/data/questions.csv`), 34 answerable and 6 out of scope. At the
threshold we use, 0.62, nothing wrong was shown, but most questions went to the slower live path. See
[matching.md](matching.md) for every threshold. We raised it from 0.42 because a wrong card shown instantly is
worse than a slower right one.

## What we haven't measured

Real Ray-Ban Display render time, noisy rooms, accented speech, and whether Cueon helps people answer better. The
protocol for that pilot is in `eval/experiment/`, and it hasn't been run.
