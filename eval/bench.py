"""End-to-end latency benchmark against a running hub, acting as the glasses.

Connects to /hud like the glasses do (acknowledging each rendered card), asks every question in
the CSV through the same path as speech, and reports p50/p95 per path from the hub's own records:
first card text (lead line) and card rendered, both measured from the end of the question.

    uv run python -m eval.bench --hub http://127.0.0.1:8000 --questions eval/data/questions.csv --out docs/latency.md
"""

import argparse
import asyncio
import csv
import json
import statistics
from pathlib import Path

import httpx
import websockets


def pct(values: list[float], q: int) -> str:
    if not values:
        return "–"
    if len(values) == 1:
        return f"{values[0]:.0f}"
    return f"{statistics.quantiles(values, n=100, method='inclusive')[q - 1]:.0f}"


async def glasses(url: str, stop: asyncio.Event) -> None:
    """Ack every new card the way the glasses view does."""
    async with websockets.connect(url) as ws:
        while not stop.is_set():
            try:
                message = json.loads(await asyncio.wait_for(ws.recv(), 0.5))
            except asyncio.TimeoutError:
                continue
            if message.get("state") == "card" and not message.get("replay") and not message.get("dimmed"):
                await ws.send(json.dumps({"type": "rendered", "id": message.get("id")}))


async def run(hub: str, questions: list[str], pause: float) -> list[dict]:
    stop = asyncio.Event()
    ws_url = hub.replace("http", "ws", 1) + "/hud"
    listener = asyncio.create_task(glasses(ws_url, stop))
    records = []
    async with httpx.AsyncClient(base_url=hub, timeout=60) as client:
        await client.post("/api/mode", json={"mode": "qa"})
        for question in questions:
            reply = (await client.post("/api/ask", json={"text": question})).json()
            await asyncio.sleep(pause)  # let the render ack arrive and the cache settle
            stats = (await client.get("/api/stats")).json()
            record = next((r for r in stats["recent"] if r["id"] == reply.get("id")), reply.get("record") or {})
            records.append(record)
            print(f"{record.get('path', '?'):5} {record.get('first', '–'):>7} ms  {question}")
    stop.set()
    await listener
    return records


def report(records: list[dict]) -> str:
    lines = ["| path | n | first text p50 | p95 | on lens p50 | p95 |", "|---|---|---|---|---|---|"]
    for path, label in (("bank", "Prepared card"), ("live", "Live (Spark)")):
        rows = [r for r in records if r.get("path") == path]
        first = [r["first"] for r in rows if "first" in r]
        rendered = [r["rendered"] for r in rows if "rendered" in r]
        lines.append(f"| {label} | {len(rows)} | {pct(first, 50)} ms | {pct(first, 95)} ms | {pct(rendered, 50)} ms | {pct(rendered, 95)} ms |")
    hits = sum(1 for r in records if r.get("path") == "bank")
    early = sum(1 for r in records if r.get("speculative"))
    fallback = sum(1 for r in records if r.get("tentative"))
    lines.append("")
    lines.append(f"{len(records)} questions · prepared-card hit rate {hits / max(len(records), 1):.0%} · "
                 f"live answers started early {early} · fallback card shown {fallback}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hub", default="http://127.0.0.1:8000")
    parser.add_argument("--questions", default="eval/data/questions.csv")
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--out")
    args = parser.parse_args()
    questions = [row["question"] for row in csv.DictReader(open(args.questions, encoding="utf-8"))]
    records = asyncio.run(run(args.hub, questions, args.pause))
    text = report(records)
    print("\n" + text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        Path(args.out).with_suffix(".json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
