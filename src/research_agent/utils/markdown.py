"""Rendering helpers for untrusted text.

Every value in a card or a report comes from a model reply or a provider payload, so all of it is
neutralized before it reaches a Markdown document.
"""


def inline(value: str) -> str:
    """Collapse untrusted text to one line and remove the markup that could break a document."""
    return " ".join(value.replace("`", "'").split())


def block(value: str) -> str:
    """Keep paragraph breaks, but never let untrusted text open a heading or a code fence."""
    paragraphs = [inline(part) for part in value.split("\n\n")]
    return "\n\n".join(part for part in paragraphs if part)
