"""Sentence similarity without a model call: cosine over character trigrams and words.

Used for the fast paths that can't wait on the network: matching a spoken question to a prepared
card, and tracking where the presenter is in the slides. Works for English and Korean alike.
"""

import math
import re
from collections import Counter

_WORD = re.compile(r"[a-z0-9]+|[가-힣]+")
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "to", "of", "and", "or", "in", "on", "for",
    "it", "this", "that", "you", "your", "we", "our", "i", "do", "does", "did", "can", "could",
    "how", "what", "why", "with", "about", "so", "me", "us", "they", "there", "have", "has",
}


def features(text: str) -> Counter:
    words = [w for w in _WORD.findall(text.lower()) if w not in _STOP]
    grams: Counter = Counter()
    for word in words:
        grams[f"w:{word}"] += 2
        padded = f" {word} "
        for i in range(len(padded) - 2):
            grams[padded[i : i + 3]] += 1
    return grams


def cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(count * b[key] for key, count in a.items() if key in b)
    norm = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return dot / norm


def similarity(a: str, b: str) -> float:
    return cosine(features(a), features(b))
