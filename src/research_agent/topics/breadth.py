"""What each topic breadth tells the model, for searching and for screening.

Breadth replaces hand-typed keywords: the model reads the topic's name and description and
decides the terms itself, as narrowly or widely as the breadth says. Wording changes here change
the query and screening prompts, so both prompt versions move with them.
"""

from research_agent.config import Breadth

QUERY_GUIDANCE: dict[Breadth, str] = {
    "focused": (
        "Breadth: focused. Stay on the topic's core: its exact name, standard synonyms and the "
        "few methods that define it. Do not branch into neighbouring fields."
    ),
    "balanced": (
        "Breadth: balanced. Cover the core and its close sub-areas, methods, datasets and "
        "applications."
    ),
    "exploratory": (
        "Breadth: exploratory. Cover the core, then reach into adjacent fields whose methods, "
        "data or findings could carry over to this topic, including ones that use other words "
        "for the same problem."
    ),
}

SCREENING_GUIDANCE: dict[Breadth, str] = {
    "focused": (
        "Breadth: focused. Mark a paper relevant only when its central contribution is squarely "
        "the topic itself; work on neighbouring problems is low."
    ),
    "balanced": (
        "Breadth: balanced. Mark a paper relevant when its central contribution belongs to the "
        "topic or one of its close sub-areas."
    ),
    "exploratory": (
        "Breadth: exploratory. Also accept papers from adjacent fields whose methods or findings "
        "would plausibly transfer to the topic; score such papers medium rather than high."
    ),
}
