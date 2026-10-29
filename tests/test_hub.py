from fastapi.testclient import TestClient

from hub.main import app


def receive_until(ws, state: str) -> list[dict]:
    seen = []
    while True:
        message = ws.receive_json()
        seen.append(message)
        if message["state"] == state:
            return seen


def test_question_becomes_card_on_hud():
    client = TestClient(app)
    with client.websocket_connect("/hud") as ws:
        assert ws.receive_json()["type"] == "hud"

        reply = client.post("/ask", json={"text": "How fast is the latency?"}).json()
        seen = receive_until(ws, "card")

        states = [m["state"] for m in seen]
        assert "listening" in states and "thinking" in states
        card = seen[-1]
        assert card["id"] == reply["id"]
        assert card["question"] == "How fast is the latency?"
        assert card["source"] == "Slide 7"

        ws.send_json({"type": "rendered", "id": card["id"]})
        ws.send_json({"type": "toggle_listen"})  # round-trip so the ack is processed
        receive_until(ws, "listening")
        assert "rendered" in client.get("/timings").json()[card["id"]]


def test_unknown_question_asks_to_repeat():
    client = TestClient(app)
    with client.websocket_connect("/hud") as ws:
        ws.receive_json()
        client.post("/ask", json={"text": "Where did you buy that shirt?"})
        assert receive_until(ws, "repeat")[-1]["partial"] == "Where did you buy that shirt?"
