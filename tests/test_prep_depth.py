import asyncio

import httpx
import pymupdf

from hub.cards import Card
from hub.models import PageNotes, SparkModel
from hub.prep import Gap, check_notes, prep_stats, read_charts
from hub.sources import Library, parse_csv, parse_file
from hub.verify import check_card
from tests.fake_openai import make_server


def chart_pdf(tmp_path):
    path = tmp_path / "deck.pdf"
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), "Cueon\nLive Q&A cue cards")
        page = doc.new_page()
        page.insert_text((72, 72), "Results")
        for i, height in enumerate([61, 88]):  # a bar chart whose values are only in the picture
            page.draw_rect(pymupdf.Rect(100 + i * 60, 300 - height, 140 + i * 60, 300), fill=(0.2, 0.4, 0.9))
        page.draw_line((90, 300), (240, 300))
        doc.save(path)
    return path


class ChartModel:
    def __init__(self):
        self.images = 0

    async def chart_numbers(self, image_png: bytes) -> list[str]:
        assert image_png.startswith(b"\x89PNG")
        self.images += 1
        return ["61%", "88%"]


def test_chart_numbers_become_citable(tmp_path):
    library = Library()
    library.add(parse_file(chart_pdf(tmp_path), alias="DECK"))
    card = Card(question="q", lead="Accuracy 61% → 88%", points=[], source="DECK p.2")
    assert check_card(card, library)  # not in the text layer

    model = ChartModel()
    assert asyncio.run(read_charts(model, library)) == 1 and model.images == 1  # only the page with a chart
    assert check_card(card, library) == []


def test_notes_keep_only_checked_support(tmp_path):
    library = Library()
    library.add(parse_file(chart_pdf(tmp_path), alias="DECK"))
    library.add(parse_csv("presenter,accuracy\nP1,90\n", alias="STUDY", name="s.csv"))
    notes = [
        PageNotes(page=1, points=["Live cue cards"], support="P1 reached 90 accuracy", support_source="STUDY p.1"),
        PageNotes(page=2, points=["Accuracy up 27 points"], support="P1 reached 95", support_source="STUDY p.1"),
    ]
    checked = check_notes(notes, library)
    assert checked[0].support_source == "STUDY p.1"
    assert checked[1].support == "" and checked[1].points == []  # 95 and 27 aren't in the material


def test_prep_stats():
    stats = prep_stats({"a": 1, "b": 2, "c": 3}, [Gap(question="c", problems=["x"])])
    assert stats == {"questions": 3, "cards": 2, "first_try": 1, "retried": 1, "gaps": 1, "drafts": 6}


def test_spark_vision_request_shape():
    server = make_server({"chart_numbers": {"numbers": ["61%"]}}, "")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://spark")
    model = SparkModel("LLM|1|test", base_url="http://spark/v1", http_client=client)
    assert asyncio.run(model.chart_numbers(b"\x89PNGfake")) == ["61%"]
    content = server.state.requests[0]["messages"][0]["content"]
    assert content[1]["type"] == "image_url" and content[1]["image_url"]["url"].startswith("data:image/png;base64,")
