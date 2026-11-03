# Cueon

Live Q&A cue cards for presenters, shown on Meta Ray-Ban Display.

Cueon reads everything you bring to a talk (slides, business plan, papers, data) before you go on
stage, predicts the questions you'll get, and writes a short, checked answer card for each. During
Q&A it listens when you pinch, finds the right card, and puts it on the glasses lens. If nothing
fits, Muse Spark writes one on the spot from your material, marked as unchecked. While you present,
it follows along through your slides and tells you when you skipped a point.

Built for the Meta Global AI Developer Hackathon 2026 (Indie Developer track, Build for Your World).

## New work

All code in this repository was written during the hackathon (Oct 26 – Nov 4, 2026). No prior code
was reused. Third-party libraries are listed in `pyproject.toml` and `hud/package.json`.

## How it works

```
                 before the talk                                   during the talk
 ┌─────────────────────────────────────────────┐    ┌─────────────────────────────────────────────┐
 │ Material: PDF / CSV, each with alias + role │    │ mic → Muse Voice Transcribe (ENDPOINTING)    │
 │        │                                    │    │        │ speechComplete                      │
 │        ▼ all pages in one cached prefix     │    │        ▼                                     │
 │ Muse Spark: expected questions + phrasings  │    │ Q&A: match card bank locally (~0 ms)         │
 │        │    + follow-ups                    │    │   ├─ hit  → prepared card, unchanged         │
 │        ▼                                    │    │   └─ miss → Spark streams a card from the    │
 │ write card → save_card checks → LLM judge   │    │            cached prefix, lead line first,   │
 │   (retry ×3 with feedback, else a "gap")    │    │            marked "Live · unchecked"         │
 │        ▼                                    │    │ Present: sentence ↔ page notes similarity    │
 │ card bank + page notes  ─────────────────────────▶  → current page, ✓ points, "Skipped" cue    │
 └─────────────────────────────────────────────┘    └──────────────┬──────────────────────────────┘
                                                                   ▼ WebSocket /hud
                                                    Ray-Ban Display web app (600×600)
```

- **No retrieval step.** The whole library goes into one fixed developer message that every Spark
  call shares (`prompt_cache_key`), so Spark sees all of the material every time and the prefix
  is served from cache after the first call.
- **Checks the agent can't skip.** `save_card` rejects a card whose citation isn't a real page,
  whose numbers aren't on the cited page, or that is too long to read at a glance; then an LLM judge
  checks every claim against the cited page. Problems go back to the writer; after three tries the
  question becomes a gap the presenter resolves in the console.
- **Citations** read `ALIAS p.N` (for example `BP p.12`), across slides, documents and CSV data.
- **Two modes, one app.** Presentation mode only uses the model before the talk (key points, a
  bridge line and a short version per page). Q&A mode uses the prepared bank first and Spark only
  when the bank has nothing close.
- **Measured.** Every question is logged with its path (prepared / live), match score and timings
  from the end of the question to the first card text and to the glasses rendering it. The console
  shows p50/p95 per path, the prepared-card hit rate and prompt-cache hits (`data/questions.jsonl`).

More detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Layout

```
hub/            FastAPI hub
  sources.py      material library: PDF/CSV parsing, page index, citations
  models.py       Muse Spark client (and a stand-in that runs without a key), prompts
  stt.py          Muse Voice Transcribe realtime client
  prep.py         Prep Agent: questions → checked cards → card bank
  verify.py       save_card checks
  bank.py         card bank and local question matching
  present.py      presentation-mode tracker
  pipeline.py     live loop, latency records
  main.py         console API, /hud and /audio WebSockets
hud/            web apps (Vite + React)
  index.html      glasses view, built with the Meta Wearables UI Toolkit (MRBD)
  console.html    presenter console: material, prep, card editing, gaps, rehearsal, latency
tests/          pytest
```

## Run

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
cp .env.example .env          # put your Model API key in MODEL_API_KEY
uv sync
(cd hud && npm ci && npm run build)
uv run uvicorn hub.main:app --port 8000
```

- Console: http://127.0.0.1:8000/console
- Glasses view: http://127.0.0.1:8000/glasses (or the 600×600 preview inside the console)

Without `MODEL_API_KEY` (or with `CUEON_FAKE=1`) the hub runs on stand-ins: cards come from your
material by text matching and you type questions instead of speaking them. Everything else works
the same.

For front-end work, `cd hud && npm run dev` serves both pages with hot reload and proxies the API
to the hub on port 8000 (`/console.html`, and `/` for the glasses view).

### Local mode (Muse Glimmer)

For material that shouldn't leave your laptop (an unreleased IR deck, a paper draft), run the
open-weights Muse Glimmer locally and point Cueon at it. Prep and live cards are then written on
your machine; only the question audio goes to Muse Voice Transcribe.

```bash
# Serve Glimmer with any OpenAI-compatible runtime, e.g. llama.cpp (weights: huggingface.co/meta-models)
llama-server -m Muse-Glimmer-30B-Q4_K_M.gguf --port 8080 -c 65536 --jinja

# .env
MODEL_BACKEND=glimmer
LOCAL_BASE_URL=http://localhost:8080/v1   # Ollama: :11434/v1, vLLM: :8000/v1
LOCAL_MODEL=muse-glimmer-30b              # what GET /v1/models reports
```

The prompts and checks are the same as with Spark. The runtime reuses the shared material prefix
from its KV cache, and Cueon leans more on prepared cards because a local 30B model is slower.

### On the glasses

Serve the glasses view where the Ray-Ban Display can reach it and point it at the hub with the
`hub` query parameter, for example `https://<host>/?hub=wss://<hub-host>/hud`. Neural Band input
arrives as keys: swipe up toggles listening, swipe
left/right flips to the runner-up card (Q&A) or corrects the page (presentation), swipe down shows
all points, and pinch presses the on-lens button (Listen / Stop, or Start Q&A while presenting).

Without Ray-Ban Display, `?device=xreal` draws the same view as a small panel low and to the right
of a full-screen display glasses (black is transparent there too).

The glasses view passes Meta's webapp checker (`meta-wearables-webapp` `check-webapp.mjs`):
UI Toolkit structure, focus, overflow and console checks in a real browser.

### Use

1. Upload your material in the console. Give each file a short alias (`DECK`, `BP`, `STUDY`) and a
   role: **main** is what you present, **evidence** is what backs it up.
2. Press **Prepare cards**. Review the bank, edit anything, and resolve the gaps.
3. Rehearse: type or speak questions and watch the glasses preview and the latency table.
4. On stage: **Presenting** while you talk, **Q&A** afterwards; pinch-up to listen to a question.

## Evaluation

```bash
uv run python -m eval.bench --out docs/latency.md          # latency p50/p95 per path, against a running hub
uv run python -m eval.bench_stt recordings/*.wav           # end of speech → speechComplete (needs the key)
uv run python -m eval.matching --data data                 # right / wrong / live-path rate per threshold
uv run python -m eval.experiment.schedule 8                # counterbalanced pilot schedule
uv run python -m eval.experiment.analyze results.csv       # pilot summary + chart
```

`eval/data/questions.csv` holds 40 spoken-style questions about the sample deck, labelled with the
page that answers them (or `none`). The pilot protocol and rubric are in `eval/experiment/`.

## Demo material

`samples/cueon-pitch.pdf` (Cueon's own pitch) and `samples/research-notes.pdf` (the sources
behind it) are generated by `samples/make_samples.py`. Upload them as `DECK` (main) and
`RESEARCH` (evidence). `samples/demo_run.py` plays a scripted talk and Q&A through a running hub,
paced like speech, for recording the glasses view.

## Tests

```bash
uv run pytest
cd hud && npm run typecheck
node hud/e2e/smoke.mjs http://127.0.0.1:8000   # against a running hub (CUEON_FAKE=1 is fine)
```
