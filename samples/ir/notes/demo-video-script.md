# Demo video script (3:00)

Material: `samples/cueon-pitch.pdf` (DECK, main) + `samples/research-notes.pdf` (RESEARCH, evidence).
Glasses view: Meta Ray-Ban Display simulator (label it on screen). Console: laptop browser.
If a part is scripted with `samples/demo_run.py`, say so on screen.

| time | picture | voice-over |
|---|---|---|
| 0:00–0:15 | Presenter on stage, a judge asks a question, presenter freezes. Caption: “A pause of 0.6–1.2 s already reads as hesitation.” | “You can rehearse a talk. You can't rehearse the questions.” |
| 0:15–0:25 | Title: Cueon, on Meta Ray-Ban Display. | “Cueon puts the answer from your own material on your lens, while the question is still in the air.” |
| 0:25–0:55 | Console: drop DECK and RESEARCH, press Prepare. Cut to the bank: cards with sources, phrasings, follow-ups; the checks line (“passed on first draft / fixed after feedback / rejected”); one gap. | “Before the talk, Muse Spark reads everything: slides, plan, papers, data. It predicts the questions an investor, a technical judge and the audience would ask, and writes a card for each. Every card is checked: every number must be on the page it cites, and a judge model checks every claim. What your material can't support becomes a gap you fix before you go on.” |
| 0:55–1:20 | Glasses (simulator), presentation mode: page counter, points ticking off, time left; presenter skips a point → **Skipped**. | “While you present, Cueon follows along page by page from what you say. No model calls on stage. Skip a key point, and it tells you before you move on.” |
| 1:20–2:05 | Pinch → Listening → question → card on the lens in under a second, presenter answers. Second question: follow-up card. Third: not in the bank → *Live · unchecked* card streams in. Fourth: out of scope → “Not in your material”. | “In Q&A, pinch to listen. A question we prepared for: the checked card is on the lens almost instantly. A follow-up: Cueon expects it. Something new: Spark writes a card on the spot from your whole deck, marked as unchecked. And if your material doesn't cover it, it says so instead of making something up.” |
| 2:05–2:30 | Console latency table (p50/p95 per path, hit rate, cache hits). Architecture diagram. | “Prepared cards are matched locally. New questions stream from Spark with the whole deck in a cached prompt, started before the speaker even finishes. These are measured numbers, end of question to card on the lens.” *(read the real numbers from the benchmark)* |
| 2:30–2:45 | Local mode badge; privacy points. | “Confidential deck? Local mode runs Muse Glimmer on your laptop. The mic only listens when you pinch, and audio is never stored.” |
| 2:45–3:00 | Presenter answering confidently. Logo + repo URL. | “Cueon. Your cue, on when you need it.” |

Notes
- Only show numbers that came from `eval/bench.py` / the console with the real models.
- If the pilot experiment ran, add its chart at 2:05 (`docs/experiment/chart.svg`); otherwise leave it out.
- X cut (30 s): 1:20–2:05 trimmed to the first card and the live card, with captions.
