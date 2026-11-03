"""Cueon hub: the presenter console API, the HUD WebSocket, and the audio input.

Without MODEL_API_KEY (or with CUEON_FAKE=1) it runs on stand-ins: type questions into the
console or POST /ask, and cards come from the material by text matching.
"""

import asyncio
import json
import logging
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from hub import config  # noqa: E402
from hub.bus import HudBus  # noqa: E402
from hub.cards import Card  # noqa: E402
from hub.fakes import fake_transcribe  # noqa: E402
from hub.models import make_model  # noqa: E402
from hub.pipeline import Mode, Pipeline  # noqa: E402
from hub.prep import build_bank  # noqa: E402
from hub.sources import default_alias, parse_file  # noqa: E402
from hub.workspace import Workspace  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("cueon")

DATA = config.DATA_DIR
WARM_EVERY_S = 240  # keep Spark's prompt cache warm between questions


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async def keep_warm() -> None:
        while True:
            await asyncio.sleep(WARM_EVERY_S)
            if workspace.library.documents and not config.fake_mode():
                await warm()

    task = asyncio.create_task(keep_warm())
    yield
    task.cancel()


app = FastAPI(title="Cueon hub", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

bus = HudBus()
model = make_model()
workspace = Workspace.load(DATA)
pipeline = Pipeline(bus, model, workspace, log_path=DATA / "questions.jsonl")
prep_status: dict = {"running": False, "message": "", "error": None}


def save() -> None:
    workspace.save(DATA)


# --- material ---------------------------------------------------------------------------


@app.get("/api/status")
def status() -> dict:
    return {
        "fake": config.fake_mode(),
        "model": config.SPARK_MODEL,
        "mode": pipeline.mode,
        "listening": pipeline.listening,
        "hud_clients": len(bus.clients),
        "prep": prep_status,
    }


@app.get("/api/docs")
def list_docs() -> list[dict]:
    return [
        {"alias": d.alias, "name": d.name, "role": d.role, "pages": len(d.pages), "titles": [p.title for p in d.pages]}
        for d in workspace.library.documents
    ]


@app.post("/api/docs")
async def upload_doc(file: UploadFile = File(...), alias: str = Form(""), role: str = Form("")) -> dict:
    name = Path(file.filename or "upload.pdf").name
    if Path(name).suffix.lower() not in {".pdf", ".csv"}:
        raise HTTPException(400, "Upload a PDF or CSV file.")
    folder = DATA / "uploads"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    with path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    alias = (alias.strip() or default_alias(name)).replace(" ", "")
    chosen_role = role if role in ("main", "evidence") else None
    if chosen_role is None and Path(name).suffix.lower() == ".pdf":
        chosen_role = "evidence" if workspace.library.main() else "main"
    try:
        doc = parse_file(path, alias=alias, role=chosen_role)
    except Exception as error:
        raise HTTPException(400, f"Couldn't read {name}: {error}") from error
    workspace.library.add(doc)
    save()
    asyncio.create_task(warm())
    return {"alias": doc.alias, "pages": len(doc.pages), "role": doc.role}


class DocUpdate(BaseModel):
    role: str | None = None


@app.patch("/api/docs/{alias}")
def update_doc(alias: str, body: DocUpdate) -> dict:
    doc = workspace.library.doc(alias)
    if doc is None:
        raise HTTPException(404, "No such document")
    if body.role in ("main", "evidence"):
        doc.role = body.role  # type: ignore[assignment]
    save()
    return {"ok": True}


@app.delete("/api/docs/{alias}")
def delete_doc(alias: str) -> dict:
    workspace.library.documents = [d for d in workspace.library.documents if d.alias != alias]
    save()
    return {"ok": True}


async def warm() -> None:
    try:
        await model.warm(workspace.library)
    except Exception:
        log.warning("cache warm-up failed", exc_info=True)


# --- prep -------------------------------------------------------------------------------


class PrepRequest(BaseModel):
    limit: int = 12


async def run_prep(limit: int) -> None:
    async def progress(message: str) -> None:
        prep_status["message"] = message

    try:
        result = await build_bank(model, workspace.library, limit=limit, progress=progress)
        # Keep the presenter's own edits; replace the rest.
        kept = [e for e in workspace.bank.entries if e.edited]
        result.bank.entries = kept + result.bank.entries
        workspace.bank = result.bank
        workspace.gaps = result.gaps
        workspace.attempts = result.attempts
        prep_status["message"] = "Writing presentation notes"
        workspace.notes = await model.page_notes(workspace.library)
        save()
        prep_status["message"] = f"Ready: {len(workspace.bank.entries)} cards, {len(workspace.gaps)} gaps"
    except Exception as error:
        log.exception("prep failed")
        prep_status["error"] = str(error)
    finally:
        prep_status["running"] = False


@app.post("/api/prep")
async def start_prep(body: PrepRequest) -> dict:
    if not workspace.library.documents:
        raise HTTPException(400, "Upload material first.")
    if prep_status["running"]:
        return prep_status
    prep_status.update(running=True, message="Starting", error=None)
    asyncio.create_task(run_prep(body.limit))
    return prep_status


@app.get("/api/bank")
def get_bank() -> dict:
    return {"entries": [e.model_dump() for e in workspace.bank.entries], "gaps": [g.model_dump() for g in workspace.gaps]}


class EntryUpdate(BaseModel):
    question: str | None = None
    variants: list[str] | None = None
    lead: str | None = None
    points: list[str] | None = None
    source: str | None = None


@app.put("/api/bank/{entry_id}")
def update_entry(entry_id: str, body: EntryUpdate) -> dict:
    entry = workspace.bank.get(entry_id)
    if entry is None:
        raise HTTPException(404, "No such card")
    if body.question is not None:
        entry.question = entry.card.question = body.question
    if body.variants is not None:
        entry.variants = [v for v in body.variants if v.strip()]
    card = entry.card.model_copy(
        update={k: v for k, v in {"lead": body.lead, "points": body.points, "source": body.source}.items() if v is not None}
    )
    entry.card = card
    entry.edited = True
    save()
    from hub.verify import check_card

    return {"ok": True, "problems": check_card(card, workspace.library)}


class NewEntry(BaseModel):
    question: str
    lead: str
    points: list[str] = []
    source: str | None = None
    variants: list[str] = []
    parent: str | None = None


@app.post("/api/bank")
def add_entry(body: NewEntry) -> dict:
    card = Card(question=body.question, lead=body.lead, points=body.points, source=body.source)
    entry = workspace.bank.add("manual", card, body.variants, parent=body.parent)
    entry.edited = True
    workspace.gaps = [g for g in workspace.gaps if g.question != body.question]
    save()
    return entry.model_dump()


@app.delete("/api/bank/{entry_id}")
def delete_entry(entry_id: str) -> dict:
    workspace.bank.remove(entry_id)
    save()
    return {"ok": True}


@app.get("/api/notes")
def get_notes() -> list[dict]:
    return [n.model_dump() for n in workspace.notes]


# --- live -------------------------------------------------------------------------------


class Ask(BaseModel):
    text: str


@app.post("/ask")
@app.post("/api/ask")
async def ask(body: Ask) -> dict:
    """Run typed text through the same path as speech (fake STT partials, then the turn)."""
    if pipeline.mode == "qa":
        pipeline.listening = True
    before = set(pipeline.records)
    await pipeline.run_stream(fake_transcribe(body.text, word_ms=40))
    new = [qid for qid in pipeline.records if qid not in before]
    qid = new[-1] if new else None
    return {"id": qid, "record": pipeline.records.get(qid) if qid else None}


class ModeRequest(BaseModel):
    mode: Mode


@app.post("/api/mode")
async def set_mode(body: ModeRequest) -> dict:
    await pipeline.set_mode(body.mode)
    return {"mode": pipeline.mode}


@app.post("/api/listen")
async def listen() -> dict:
    await pipeline.toggle_listen()
    return {"listening": pipeline.listening}


@app.post("/api/page/{delta}")
async def page(delta: int) -> dict:
    await pipeline.goto_page(delta)
    return {"page": pipeline.tracker.current.page if pipeline.tracker and pipeline.tracker.current else None}


@app.get("/api/stats")
@app.get("/timings")
def stats() -> dict:
    return pipeline.stats()


@app.websocket("/hud")
async def hud(ws: WebSocket) -> None:
    await bus.connect(ws)
    try:
        while True:
            message = json.loads(await ws.receive_text())
            kind = message.get("type")
            if kind == "rendered":
                pipeline.mark_rendered(message.get("id", ""))
            elif kind == "toggle_listen":
                await pipeline.toggle_listen()
            elif kind == "page":
                await pipeline.swipe(int(message.get("delta", 1)))
    except WebSocketDisconnect:
        bus.disconnect(ws)


@app.websocket("/audio")
async def audio(ws: WebSocket) -> None:
    """Raw PCM16 mono 24 kHz from the console microphone (or any client), relayed to Voice Transcribe."""
    await ws.accept()
    key = config.api_key()
    if config.fake_mode() or key is None:
        await ws.send_text(json.dumps({"type": "error", "message": "No MODEL_API_KEY: type questions instead."}))
        await ws.close()
        return

    from hub.stt import transcribe

    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=8)

    async def chunks():
        while (chunk := await queue.get()) is not None:
            yield chunk

    async def relay() -> None:
        try:
            async for event in transcribe(chunks(), key, keywords=workspace.keywords()):
                if event.get("type") in ("transcript", "speechComplete"):
                    await ws.send_text(json.dumps(event))
                await pipeline.on_event(event)
        except Exception as error:
            log.exception("transcription stopped")
            try:
                await ws.send_text(json.dumps({"type": "error", "message": str(error)}))
            except Exception:
                pass

    task = asyncio.create_task(relay())
    try:
        while True:
            chunk = await ws.receive_bytes()
            if queue.full():
                queue.get_nowait()  # stay real time: drop the oldest frame rather than lag
            queue.put_nowait(chunk)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await queue.put(None)
        await asyncio.wait({task}, timeout=5)


# --- console static files ----------------------------------------------------------------

_DIST = Path(__file__).resolve().parent.parent / "hud" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/")
    @app.get("/console")
    def console_page() -> FileResponse:
        return FileResponse(_DIST / "console.html")

    @app.get("/glasses")
    def glasses_page() -> FileResponse:
        return FileResponse(_DIST / "index.html")
