# Overnight plan (11/4 01:00 → 10:00 KST)

Branch: `overnight`. Commit per feature, push, update the Notion page "야간 작업 로그".
Notion 기획서 본문과 11장 일정표는 건드리지 않는다. 키 없이 할 수 있는 것만 (api.meta.ai는 클라우드에서 막힘).

Status: [ ] todo · [~] doing · [x] done

## 1. Verify the real-model code path without a key
- [x] Fake OpenAI-compatible server in tests: Spark client sends prompt_cache_key, reasoning_effort,
      json_schema, streams; parses usage/cached tokens. Catch spec mistakes before the morning.
- [x] Fake ASR WebSocket server in tests: handshake, binary audio, endStream, events → pipeline.

## 2. Live agent (기획서 6장)
- [x] Fallback: if no live lead within 1.2 s, show the nearest bank card (marked tentative), replace when Spark answers
- [x] Speculative start: partial transcript that looks like a complete question starts the live request early; cancel if final differs
- [x] Second candidate: swipe left/right shows the runner-up card
- [x] Repeat card for unusable transcripts (too short / not a question)
- [x] Cache warm-up every few minutes while idle

## 3. Glimmer local mode (P1, Open Weights bonus)
- [x] OpenAI-compatible local backend (ollama / llama.cpp server), MODEL_BACKEND=glimmer
- [x] Console badge + README section

## 4. Prep Agent depth
- [ ] Audience perspectives (investor / technical judge / general) in question generation
- [ ] Chart and table numbers from page images (Spark vision) added to page numbers
- [ ] STT keyword list from the model (proper nouns, acronyms)
- [ ] Presentation notes: supporting line from evidence docs, number-checked like cards
- [ ] Rejection rate and retries shown in the console

## 5. Presentation mode P2
- [ ] Talk timer: target length, remaining time, "N min left, M pages to go"

## 6. HUD / console UI-UX
- [ ] HUD: confidence dot, tentative/live states, layout polish to spec (25px+ type, 5 lines max)
- [ ] HUD: `?device=xreal` placement option
- [ ] HUD: run Meta's webapp checker (meta-wearables-webapp check-webapp.mjs)
- [ ] Console: drag-and-drop upload, glasses-size preview per card, live transcript, prep stats

## 7. Evaluation
- [ ] eval/bench.py: N questions through the hub, p50/p95 per stage, markdown table
- [ ] eval/matching: paraphrase set → hit rate / wrong-card rate vs threshold
- [ ] eval/experiment kit: question sets A/B, counterbalancing, rubric, analysis → chart

## 8. Demo + submission
- [ ] samples/: Cueon pitch deck PDF + evidence CSV for the demo
- [ ] docs/ARCHITECTURE.md, demo video script, submission text, X post draft
- [ ] End-to-end Playwright check + screenshots
