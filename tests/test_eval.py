from eval.experiment.analyze import bar_chart, summarise
from eval.experiment.schedule import schedule
from eval.matching import evaluate
from hub.bank import Bank
from hub.cards import Card


def test_schedule_balances_every_four():
    rows = schedule(8)
    assert len({(first, second) for _, first, second in rows}) == 4


def test_analyze_summary_and_chart():
    rows = []
    for p, (none_s, cueon_s) in {"P1": (3.0, 1.5), "P2": (2.0, 2.5)}.items():
        rows += [
            {"participant": p, "condition": "none", "start_s": none_s, "accuracy": 1, "tlx": 60},
            {"participant": p, "condition": "cueon", "start_s": cueon_s, "accuracy": 3, "tlx": 50},
        ]
    summary = summarise(rows)
    assert summary["faster_with_cueon"] == 1 and summary["cueon"]["accuracy_mean"] == 3
    assert bar_chart(summary).startswith("<svg") and "Cueon" in bar_chart(summary)


def test_matching_outcomes():
    bank = Bank()
    bank.add("latency", Card(question="How fast is it?", lead="1.5s", points=[], source="DECK p.6"), ["What's the latency?"])
    rows = [
        {"question": "what's the latency", "expected": "DECK p.6"},
        {"question": "where did you buy that shirt", "expected": "none"},
        {"question": "how fast is it", "expected": "DECK p.2"},
    ]
    r = evaluate(bank, rows, 0.4)
    assert (r["hit"], r["correct_miss"], r["wrong"]) == (1, 1, 1)
