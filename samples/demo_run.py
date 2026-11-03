"""Play a scripted talk and Q&A through a running hub, paced like speech, for recording the demo.

The script goes through the same path as the microphone (partial transcripts, then the finished
turn). Use it to record the glasses view in the simulator when a live mic isn't practical; say in
the video which parts are scripted.

    uv run python samples/demo_run.py --hub http://127.0.0.1:8000
"""

import argparse
import time

import httpx

TALK = [
    "Hi, I'm presenting Cueon, live Q and A cue cards for presenters on Meta Ray-Ban Display.",
    "The problem is that Q and A is the part of a talk you can't rehearse.",
    "Presenters miss the question or blank on the number.",
    "It's for non-native speakers presenting in English, like hackathon finalists and founders.",
    "Before the talk you upload your slides, plan, papers and data.",
    "Cueon predicts the questions and writes a checked card for each one.",
]

QA = [
    "How fast does the card actually show up?",
    "And how do you stop the model from making up numbers?",
    "Who are your competitors?",
    "What's your business model?",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hub", default="http://127.0.0.1:8000")
    parser.add_argument("--minutes", type=float, default=3)
    parser.add_argument("--gap", type=float, default=2.5, help="seconds between sentences")
    parser.add_argument("--qa-gap", type=float, default=7, help="seconds to 'answer' each question")
    args = parser.parse_args()

    with httpx.Client(base_url=args.hub, timeout=60) as hub:
        hub.post("/api/talk", json={"minutes": args.minutes})
        hub.post("/api/mode", json={"mode": "present"})
        input("Presentation mode is on the glasses. Start recording, then press Enter… ")
        for sentence in TALK:
            print("say:", sentence)
            hub.post("/api/ask", json={"text": sentence})
            time.sleep(args.gap)

        hub.post("/api/mode", json={"mode": "qa"})
        time.sleep(2)
        for question in QA:
            print("Q:", question)
            reply = hub.post("/api/ask", json={"text": question}).json()
            record = reply.get("record") or {}
            print(f"   → {record.get('path')} card, first text {record.get('first')} ms")
            time.sleep(args.qa_gap)
    print("done")


if __name__ == "__main__":
    main()
