"""The presenter's material: slides, plans, papers, data. Each document has an alias and a role.

Cards cite a page as "<alias> p.<n>" (for example "BP p.12"). CSV files are split into pages of
rows so data can be cited the same way.
"""

import csv
import io
import re
from pathlib import Path
from typing import Literal

import pymupdf
from pydantic import BaseModel

# Standalone numbers like 1.4, 30, 1,000, $0.18 — but not the 50 in "p50" or the 3 in "GPT3".
_NUMBER = re.compile(r"(?<![A-Za-z\d])\d+(?:[.,]\d+)*")
_SOURCE = re.compile(r"\s*([\w\-]+)\s+p\.?\s*(\d+)\s*")
CSV_ROWS_PER_PAGE = 40

Role = Literal["main", "evidence"]


def numbers_in(text: str) -> set[str]:
    return {match.replace(",", "") for match in _NUMBER.findall(text)}


class Page(BaseModel):
    number: int
    title: str
    text: str
    # Numbers the page supports. Starts with the text's numbers; the Prep Agent adds numbers it
    # reads from charts and tables in the page image.
    numbers: set[str]


class Document(BaseModel):
    alias: str
    name: str
    role: Role = "main"
    pages: list[Page]
    path: str | None = None  # the uploaded file, for rendering pages

    def page(self, number: int) -> Page | None:
        return next((p for p in self.pages if p.number == number), None)


class Library(BaseModel):
    documents: list[Document] = []

    def add(self, doc: Document) -> None:
        self.documents = [d for d in self.documents if d.alias != doc.alias] + [doc]

    def doc(self, alias: str) -> Document | None:
        return next((d for d in self.documents if d.alias.lower() == alias.lower()), None)

    def main(self) -> Document | None:
        """The document the talk follows (the slides)."""
        return next((d for d in self.documents if d.role == "main"), None)

    def resolve(self, source: str | None) -> tuple[Document, Page] | None:
        """Look up a citation like 'BP p.12'."""
        match = _SOURCE.fullmatch(source or "")
        if not match:
            return None
        doc = self.doc(match.group(1))
        page = doc.page(int(match.group(2))) if doc else None
        return (doc, page) if doc and page else None

    def as_prompt(self) -> str:
        """Every page of every document, in a stable order, for the cached prompt prefix."""
        parts = []
        for doc in self.documents:
            parts.append(f"# Document {doc.alias} ({doc.role}): {doc.name}")
            for page in doc.pages:
                parts.append(f"## {doc.alias} p.{page.number}\n{page.text}")
        return "\n\n".join(parts)


def default_alias(filename: str, taken: list[str] = ()) -> str:
    """Short alias from the file name (any script), unique among the other documents."""
    stem = re.sub(r"[^\w]+", "", Path(filename).stem).replace("_", "")
    base = (stem[:6] or "DOC").upper()
    alias, n = base, 2
    while alias.lower() in {t.lower() for t in taken}:
        alias, n = f"{base}{n}", n + 1
    return alias


def parse_pdf(path: str | Path, alias: str, role: Role = "main", name: str | None = None) -> Document:
    pages = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            title = next((line.strip() for line in text.splitlines() if line.strip()), f"Page {i}")
            pages.append(Page(number=i, title=title, text=text, numbers=numbers_in(text)))
    return Document(alias=alias, name=name or Path(path).name, role=role, pages=pages, path=str(path))


def parse_csv(data: str, alias: str, name: str, role: Role = "evidence") -> Document:
    rows = list(csv.reader(io.StringIO(data)))
    if not rows:
        return Document(alias=alias, name=name, role=role, pages=[])
    header, body = rows[0], rows[1:]
    pages = []
    for start in range(0, max(len(body), 1), CSV_ROWS_PER_PAGE):
        chunk = body[start : start + CSV_ROWS_PER_PAGE]
        out = io.StringIO()
        csv.writer(out).writerows([header, *chunk])
        text = out.getvalue().strip()
        title = f"{name} rows {start + 1}-{start + len(chunk)}"
        pages.append(Page(number=len(pages) + 1, title=title, text=text, numbers=numbers_in(text)))
    return Document(alias=alias, name=name, role=role, pages=pages)


def parse_file(path: str | Path, alias: str | None = None, role: Role | None = None) -> Document:
    path = Path(path)
    alias = alias or default_alias(path.name)
    if path.suffix.lower() == ".csv":
        return parse_csv(path.read_text(encoding="utf-8-sig"), alias, path.name, role or "evidence")
    return parse_pdf(path, alias, role or "main", path.name)


def pages_with_visuals(path: str | Path) -> list[int]:
    """Pages that have images or vector drawings: where charts and tables hide numbers."""
    found = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            if page.get_images() or len(page.get_drawings()) >= 3:
                found.append(i)
    return found


def page_png(path: str | Path, number: int, dpi: int = 110) -> bytes:
    with pymupdf.open(path) as doc:
        return doc[number - 1].get_pixmap(dpi=dpi).tobytes("png")


def render_pages(path: str | Path, out_dir: str | Path, dpi: int = 100) -> list[Path]:
    """Save each PDF page as a PNG so a multimodal model can read charts and tables."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            image = out / f"page-{i:02d}.png"
            page.get_pixmap(dpi=dpi).save(image)
            paths.append(image)
    return paths
