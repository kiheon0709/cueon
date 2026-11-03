import pymupdf
from fastapi.testclient import TestClient

from hub.main import app

SLIDES = [
    "Cueon\nLive Q&A cue cards for presenters",
    "Latency\nCard appears 1.4s after the question\nPrepared cards show in 0.3s",
    "Privacy\nAudio is never stored\nPush to listen only",
]


def receive_until(ws, state: str) -> list[dict]:
    seen = []
    while True:
        message = ws.receive_json()
        seen.append(message)
        if message["state"] == state:
            return seen


def make_pdf(tmp_path):
    path = tmp_path / "deck.pdf"
    with pymupdf.open() as doc:
        for text in SLIDES:
            doc.new_page().insert_text((72, 72), text)
        doc.save(path)
    return path


def wait_for_prep(client):
    import time

    for _ in range(200):
        status = client.get("/api/status").json()["prep"]
        if not status["running"]:
            return status
        time.sleep(0.05)
    raise AssertionError("prep did not finish")


def test_upload_prep_answer_and_present(tmp_path):
    with TestClient(app) as client:  # keeps one event loop so prep runs in the background
        run_flow(client, tmp_path)


def run_flow(client, tmp_path):
    with make_pdf(tmp_path).open("rb") as f:
        reply = client.post("/api/docs", files={"file": ("deck.pdf", f, "application/pdf")}, data={"alias": "DECK"}).json()
    assert reply == {"alias": "DECK", "pages": 3, "role": "main"}

    client.post("/api/prep", json={"limit": 5})
    status = wait_for_prep(client)
    assert status["error"] is None
    bank = client.get("/api/bank").json()
    assert {e["qtype"] for e in bank["entries"] if not e["parent"]} == {"latency", "privacy"}
    assert len(client.get("/api/notes").json()) == 3

    with client.websocket_connect("/hud") as ws:
        ws.receive_json()

        # Fast path: a prepared card, shown as is.
        reply = client.post("/api/ask", json={"text": "How does latency work?"}).json()
        card = receive_until(ws, "card")[-1]
        assert card["path"] == "bank" and card["source"] == "DECK p.2" and not card["live"]
        assert card["id"] == reply["id"]
        ws.send_json({"type": "rendered", "id": card["id"]})

        # Live path: nothing in the bank is close, so a card is written on the spot.
        client.post("/api/ask", json={"text": "Is audio stored anywhere?"})
        seen = receive_until(ws, "card")
        assert "thinking" in [m["state"] for m in seen]
        assert seen[-1]["path"] == "live" and seen[-1]["live"]

    stats = client.get("/api/stats").json()
    assert stats["questions"] == 2 and stats["hit_rate"] == 0.5
    assert stats["paths"]["bank"]["first_p50"] is not None

    # Presentation mode follows the page notes written during prep.
    with client.websocket_connect("/hud") as ws:
        ws.receive_json()
        client.post("/api/mode", json={"mode": "present"})
        assert receive_until(ws, "present")[-1]["page"] == 1
        ws.send_json({"type": "page", "delta": 1})
        message = ws.receive_json()
        assert message["page"] == 2
        client.post("/api/mode", json={"mode": "qa"})
