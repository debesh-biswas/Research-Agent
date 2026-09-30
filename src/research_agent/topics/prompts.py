"""Versioned prompt for suggesting keywords when a topic is first created."""

PROMPT_VERSION = "topic_keywords.v1"

SYSTEM_PROMPT = (
    "You propose search keywords for a new academic research-monitoring topic. "
    'Reply with JSON only, in the form {"keywords": ["..."]}. '
    "Each keyword is a short phrase of one to four words suited to an academic search query, "
    "not a sentence. Return five to eight distinct keywords covering methods, subfields, and "
    "applications."
)

_TEMPLATE = """Topic name: {name}
Description: {description}"""


def render(name: str, description: str) -> str:
    return _TEMPLATE.format(name=name, description=description.strip() or "none given")
