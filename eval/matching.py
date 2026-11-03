"""How well local matching picks the right prepared card, across thresholds.

A question counts as a hit when the matched card cites the expected page, wrong when it shows a
card from another page, and a miss when nothing clears the threshold (the live path takes over).
For out-of-scope questions (expected = none) the right outcome is a miss: showing any prepared
card is wrong.

    uv run python -m eval.matching --data data            # the hub's prepared workspace
    uv run python -m eval.matching --questions eval/data/questions.csv --out docs/matching.md
"""

import argparse
import csv
from pathlib import Path

from hub.bank import Bank
from hub.workspace import Workspace

THRESHOLDS = [0.25, 0.3, 0.35, 0.4, 0.42, 0.45, 0.5, 0.55, 0.6]


def page_of(source: str | None) -> str:
    return (source or "").strip()


def evaluate(bank: Bank, rows: list[dict], threshold: float) -> dict:
    hit = wrong = miss = correct_miss = 0
    for row in rows:
        ranked = bank.rank(row["question"], limit=1)
        best = ranked[0] if ranked and ranked[0].score >= threshold else None
        if row["expected"] == "none":
            if best is None:
                correct_miss += 1
            else:
                wrong += 1
        elif best is None:
            miss += 1
        elif page_of(best.entry.card.source) == row["expected"]:
            hit += 1
        else:
            wrong += 1
    n = len(rows)
    return {"threshold": threshold, "hit": hit, "wrong": wrong, "miss": miss, "correct_miss": correct_miss, "n": n}


def table(results: list[dict]) -> str:
    lines = [
        "| threshold | right card | wrong card shown | sent to live path | out-of-scope kept out |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['threshold']:.2f} | {r['hit']} | {r['wrong']} | {r['miss']} | {r['correct_miss']} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default="data", help="hub data folder with workspace.json")
    parser.add_argument("--questions", default="eval/data/questions.csv")
    parser.add_argument("--out", help="write the markdown table here too")
    args = parser.parse_args()

    workspace = Workspace.load(Path(args.data))
    if not workspace.bank.entries:
        raise SystemExit(f"No cards in {args.data}/workspace.json. Upload material and run Prepare first.")
    rows = list(csv.DictReader(open(args.questions, encoding="utf-8")))
    results = [evaluate(workspace.bank, rows, t) for t in THRESHOLDS]
    in_scope = sum(1 for r in rows if r["expected"] != "none")
    report = (
        f"Matching on {len(rows)} questions ({in_scope} answerable from the material, "
        f"{len(rows) - in_scope} out of scope), {len(workspace.bank.entries)} prepared cards.\n\n" + table(results)
    )
    print(report)
    if args.out:
        Path(args.out).write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
