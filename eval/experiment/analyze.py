"""Summarise pilot results and draw one chart (SVG, no plotting library needed).

    uv run python -m eval.experiment.analyze eval/experiment/results.csv --out docs/experiment
"""

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

LABELS = {"none": "No help", "cueon": "Cueon"}


def summarise(rows: list[dict]) -> dict:
    by = defaultdict(lambda: {"start": [], "acc": [], "tlx": []})
    per_participant = defaultdict(dict)
    for r in rows:
        c = r["condition"]
        by[c]["start"].append(float(r["start_s"]))
        by[c]["acc"].append(float(r["accuracy"]))
        if r.get("tlx"):
            by[c]["tlx"].append(float(r["tlx"]))
        per_participant[r["participant"]].setdefault(c, []).append(float(r["start_s"]))
    out = {}
    for c, v in by.items():
        out[c] = {
            "answers": len(v["start"]),
            "start_median": statistics.median(v["start"]),
            "accuracy_mean": statistics.mean(v["acc"]),
            "tlx_mean": statistics.mean(v["tlx"]) if v["tlx"] else None,
        }
    faster = sum(
        1 for p in per_participant.values() if "none" in p and "cueon" in p and statistics.median(p["cueon"]) < statistics.median(p["none"])
    )
    out["participants"] = len(per_participant)
    out["faster_with_cueon"] = faster
    return out


def bar_chart(summary: dict) -> str:
    """Two panels: median answer start (s) and mean accuracy (0–3)."""
    conds = [c for c in ("none", "cueon") if c in summary]
    w, h, pad = 640, 300, 50
    panels = [("Answer start, median (s)", "start_median", None), ("Accuracy, mean (0–3)", "accuracy_mean", 3.0)]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="system-ui, sans-serif" font-size="13">',
             f'<rect width="{w}" height="{h}" fill="white"/>']
    colors = {"none": "#9aa3b2", "cueon": "#2f6fed"}
    for i, (title, key, top) in enumerate(panels):
        x0 = pad + i * (w / 2)
        top = top or max(summary[c][key] for c in conds) * 1.2 or 1
        base = h - pad
        parts.append(f'<text x="{x0}" y="28" font-weight="600">{title}</text>')
        for j, c in enumerate(conds):
            value = summary[c][key]
            bh = (base - 50) * value / top
            bx = x0 + j * 110
            parts.append(f'<rect x="{bx}" y="{base - bh}" width="80" height="{bh}" rx="4" fill="{colors[c]}"/>')
            parts.append(f'<text x="{bx + 40}" y="{base - bh - 6}" text-anchor="middle">{value:.2f}</text>')
            parts.append(f'<text x="{bx + 40}" y="{base + 18}" text-anchor="middle">{LABELS[c]}</text>')
        parts.append(f'<line x1="{x0 - 10}" y1="{base}" x2="{x0 + 220}" y2="{base}" stroke="#ccc"/>')
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results")
    parser.add_argument("--out", default="docs/experiment")
    args = parser.parse_args()
    rows = list(csv.DictReader(open(args.results, encoding="utf-8")))
    summary = summarise(rows)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "chart.svg").write_text(bar_chart(summary), encoding="utf-8")
    lines = [f"Pilot, {summary['participants']} participants. Direction of effects only.", "",
             "| condition | answers | answer start (median s) | accuracy (mean 0–3) | NASA-TLX (mean) |", "|---|---|---|---|---|"]
    for c in ("none", "cueon"):
        if c in summary:
            s = summary[c]
            tlx = f"{s['tlx_mean']:.1f}" if s["tlx_mean"] is not None else "–"
            lines.append(f"| {LABELS[c]} | {s['answers']} | {s['start_median']:.2f} | {s['accuracy_mean']:.2f} | {tlx} |")
    lines += ["", f"{summary['faster_with_cueon']} of {summary['participants']} participants started answering sooner with Cueon."]
    (out / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
