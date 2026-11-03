"""Counterbalanced schedule: condition order × question set, cycling through all four combinations.

    uv run python -m eval.experiment.schedule 8
"""

import sys

COMBOS = [
    (("none", "A"), ("cueon", "B")),
    (("none", "B"), ("cueon", "A")),
    (("cueon", "A"), ("none", "B")),
    (("cueon", "B"), ("none", "A")),
]


def schedule(n: int) -> list[tuple[str, tuple, tuple]]:
    return [(f"P{i + 1}", *COMBOS[i % 4]) for i in range(n)]


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    if n % 4:
        print(f"note: {n} is not a multiple of 4, so the combinations won't be balanced")
    print("participant,first_condition,first_set,second_condition,second_set")
    for p, first, second in schedule(n):
        print(f"{p},{first[0]},{first[1]},{second[0]},{second[1]}")
