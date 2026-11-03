# Pilot experiment: no help vs Cueon

Question: with Cueon cards, do presenters start answering sooner and answer more accurately in
English Q&A under mild pressure than with no help?

- **Participants:** 4 or 8 (a multiple of 4 balances order and question set). A pilot: report
  direction of effects, not significance.
- **Design:** within-subject, two conditions (no help / Cueon). Two question sets (A, B; 5 each,
  in `questions.csv`). `schedule.py` assigns order × set so each of the four combinations is used
  equally.
- **Material:** `samples/cueon-pitch.pdf` and `samples/research-notes.pdf`. Five minutes to study.
- **Procedure per condition:** play each recorded question, participant answers aloud in English.
  In the Cueon condition the glasses view runs in a small window below eye line (the simulator),
  with the prepared bank loaded. Note this differs from real glasses.
- **Measures:** answer start time (s), accuracy (rubric 0–3), NASA-TLX raw after each condition,
  preference at the end.
- **Record:** one row per answer in `results.csv` (template below), then `uv run python -m
  eval.experiment.analyze eval/experiment/results.csv` writes the summary and chart.

`results.csv` columns: `participant,condition,set,question_id,start_s,accuracy,tlx`
(`tlx` once per participant × condition, on any one row of that block.)
