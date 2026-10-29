"""Slide index built from the presenter's PDF deck."""

import re
from pathlib import Path

import pymupdf
from pydantic import BaseModel

# Standalone numbers like 1.4, 30, 1,000, $0.18 — but not the 50 in "p50" or the 3 in "GPT3".
_NUMBER = re.compile(r"(?<![A-Za-z\d])\d+(?:[.,]\d+)*")


def numbers_in(text: str) -> set[str]:
    return {match.replace(",", "") for match in _NUMBER.findall(text)}


class Slide(BaseModel):
    number: int
    title: str
    text: str
    # Numbers the slide supports. Starts with the text's numbers; the Prep Agent adds
    # numbers it reads from charts and tables in the slide image.
    numbers: set[str]


class Deck(BaseModel):
    slides: list[Slide]

    def slide(self, number: int) -> Slide | None:
        return next((s for s in self.slides if s.number == number), None)


def parse_pdf(path: str | Path) -> Deck:
    slides = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            title = next((line for line in text.splitlines() if line.strip()), f"Slide {i}")
            slides.append(Slide(number=i, title=title.strip(), text=text, numbers=numbers_in(text)))
    return Deck(slides=slides)


def render_slides(path: str | Path, out_dir: str | Path, dpi: int = 100) -> list[Path]:
    """Save each slide as a PNG so a multimodal model can read charts and tables."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            image = out / f"slide-{i:02d}.png"
            page.get_pixmap(dpi=dpi).save(image)
            paths.append(image)
    return paths
