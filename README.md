# Cueon

Live Q&A cue cards for presenters, shown on Meta Ray-Ban Display.

Cueon listens to audience questions during Q&A, builds a short answer cue from the presenter's own deck, and shows it on the glasses lens.

Built for the Meta Global AI Developer Hackathon 2026 (Indie Developer track, Build for Your World).

## New work

All code in this repository was written during the hackathon (Oct 26 – Nov 4, 2026). No prior code was reused.

## Layout

```
hub/   FastAPI hub: speech-to-text, question detection, answer agent, HUD bus
hud/   Ray-Ban Display web app (600×600)
```

## Run

```bash
cp .env.example .env
uv sync
uv run uvicorn hub.main:app --port 8000
```
