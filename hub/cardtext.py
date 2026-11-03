"""Plain-text card format for the streamed live path.

Spark writes the card line by line so the lead can reach the lens before the rest is done:

    LEAD: Card in ~1.5s after the question
    - Prepared cards show in ~0.3s
    - Cached material, no retrieval step
    SOURCE: DECK p.7
"""

from hub.cards import Card


def parse(text: str, question: str) -> Card | None:
    """Parse whatever has streamed so far. Returns None until the lead line is complete."""
    lead, points, source = None, [], None
    lines = text.split("\n")
    complete = lines if text.endswith("\n") else lines[:-1]
    for line in complete:
        line = line.strip()
        upper = line.upper()
        if upper.startswith("LEAD:"):
            lead = line[5:].strip()
        elif upper.startswith("SOURCE:"):
            source = line[7:].strip() or None
        elif line.startswith(("-", "•", "*")) and lead is not None:
            points.append(line.lstrip("-•* ").strip())
    if not lead:
        return None
    return Card(question=question, lead=lead, points=points[:3], source=source, live=True)


def format(card: Card) -> str:
    lines = [f"LEAD: {card.lead}", *(f"- {p}" for p in card.points)]
    if card.source:
        lines.append(f"SOURCE: {card.source}")
    return "\n".join(lines) + "\n"
