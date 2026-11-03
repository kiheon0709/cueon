"""Build the demo material: Cueon's own pitch deck and a research-notes evidence document.

Only facts from the project plan and its cited sources go in here. Latency figures are targets,
labelled as such, until the benchmark has been run with the real models.

    uv run python samples/make_samples.py
"""

from pathlib import Path

import pymupdf

OUT = Path(__file__).parent
W, H = 960, 540

DECK = [
    ("Cueon", ["Live Q&A cue cards for presenters", "On Meta Ray-Ban Display", "Built with Muse Spark and Muse Voice Transcribe"]),
    ("The problem", [
        "Q&A is the part of a talk you can't rehearse",
        "Presenters miss the question, blank on the number, or ramble",
        "A pause of 0.6 to 1.2 seconds already reads as hesitation",
    ]),
    ("Who it's for", [
        "Non-native speakers presenting in English",
        "Hackathon finalists, founders pitching investors, researchers at conferences",
        "About 30% of early-career non-English researchers skip English conferences",
    ]),
    ("How it works", [
        "Before the talk: upload slides, plan, papers and data",
        "Cueon predicts questions and writes a checked card for each",
        "During Q&A: pinch to listen, the card appears on the lens",
    ]),
    ("Checked cards, not guesses", [
        "Every number on a card must appear on the cited page",
        "A judge model checks each claim against that page",
        "Rejected cards are rewritten up to 3 times, then flagged as gaps",
    ]),
    ("Latency", [
        "Prepared cards: matched locally, no model call",
        "New questions: Muse Spark streams a card from the cached material",
        "Target: card on the lens within 1.5 s (p50) and 2.5 s (p95)",
    ]),
    ("While you present", [
        "Follows your talk page by page from what you say",
        "Flags key points you skipped before you move on",
        "Shows time left and a short version when time runs out",
    ]),
    ("Privacy", [
        "Push to listen: the mic is off until you pinch",
        "Audio is never stored and speakers are never identified",
        "Local mode runs Muse Glimmer on your laptop for confidential decks",
    ]),
    ("Competition", [
        "Teleprompters show a fixed script and can't react to questions",
        "Live captions show words, not answers",
        "Cueon answers from your own material, built only for live Q&A",
    ]),
]

RESEARCH = [
    ("Research notes", ["Sources behind the Cueon pitch"]),
    ("Listening in a second language", [
        "Sentence recognition in quiet: native listeners 99.6%",
        "Chinese listeners living in the US: 70.7%",
        "Chinese listeners living in China: 41.0%",
    ]),
    ("Stress and recall", [
        "Social stress (Trier Social Stress Test) impairs free recall of learned material",
        "Numbers and exact figures are the hardest to retrieve under pressure",
    ]),
    ("Turn-taking", [
        "Gaps between conversational turns are short across languages",
        "Silences of 0.6 to 1.2 seconds are judged negatively by listeners",
    ]),
    ("Q&A and funding", [
        "Kanze et al., Academy of Management Journal, 2018",
        "The kind of questions founders get in investor Q&A, and how they answer, relates to funding raised",
    ]),
    ("Language barriers in science", [
        "Amano et al., PLOS Biology, 2023",
        "About 30% of early-career researchers from non-English-speaking countries avoid English-language conferences",
    ]),
    ("Reading on the glasses", [
        "Ray-Ban Display: 600 x 600 pixels, right eye, about 20 degrees field of view",
        "A glance of 2 seconds fits about 4 to 5 words, so card leads stay at 12 words or fewer",
    ]),
]


def write(pages: list[tuple[str, list[str]]], path: Path) -> None:
    doc = pymupdf.open()
    for title, lines in pages:
        page = doc.new_page(width=W, height=H)
        page.draw_rect(pymupdf.Rect(0, 0, W, 8), color=None, fill=(0.18, 0.43, 0.93))
        page.insert_textbox(pymupdf.Rect(60, 50, W - 60, 120), title, fontsize=34, fontname="helv")
        y = 160
        for line in lines:
            page.insert_textbox(pymupdf.Rect(80, y, W - 60, y + 60), f"• {line}", fontsize=21, fontname="helv")
            y += 70
    doc.save(path)


if __name__ == "__main__":
    write(DECK, OUT / "cueon-pitch.pdf")
    write(RESEARCH, OUT / "research-notes.pdf")
    print("wrote", OUT / "cueon-pitch.pdf", OUT / "research-notes.pdf")
