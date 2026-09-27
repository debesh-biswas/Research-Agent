"""Versioned prompts for gap detection and ideation.

Both prompts are given the run's paper ids explicitly, because a gap or an idea that cannot be
traced back to a real paper in the corpus is discarded rather than stored.
"""

from research_agent.config import TopicSettings
from research_agent.domain.analysis import ResearchGap, WeeklySynthesis

GAP_PROMPT_VERSION = "research_gaps.v1"
IDEA_PROMPT_VERSION = "research_ideas.v1"

GAP_SYSTEM_PROMPT = (
    "You identify unaddressed research questions from a week's synthesis of one topic. Reply with "
    'JSON only, in the form {"gaps": [{"title": "...", "description": "...", '
    '"supporting_paper_ids": ["..."], "confidence": 0.0}]}. '
    "Every gap must cite at least one supporting paper id, copied exactly from the ids "
    "given; a gap you cannot attribute must be left out. Confidence is between 0 and 1 "
    "and should be low when "
    "the evidence is thin or comes from an abstract alone. State at most {max_gaps} gaps, most "
    "clearly supported first. Add no fields beyond the ones listed."
)

IDEA_SYSTEM_PROMPT = (
    "You turn identified research gaps into concrete, testable proposals. Reply with JSON only, in "
    'the form {"ideas": [{"title": "...", "hypothesis": "...", "motivation": "...", '
    '"supporting_paper_ids": ["..."], "identified_gap": "...", "proposed_direction": "...", '
    '"evaluation_plan": "...", "risks": ["..."]}]}. '
    "`identified_gap` must repeat the title of one of the gaps given. Every idea must cite "
    "at least one supporting paper id, copied exactly from the ids given. Propose at most "
    "{max_ideas} "
    "distinct ideas; do not restate one idea twice. The evaluation plan must name what would "
    "falsify the hypothesis. Add no fields beyond the ones listed."
)

_GAP_TEMPLATE = """Topic: {name}
Topic keywords: {keywords}

Paper ids in this run: {paper_ids}

This week's synthesis:
{synthesis}"""

_IDEA_TEMPLATE = """Topic: {name}
Topic keywords: {keywords}

Paper ids in this run: {paper_ids}

Identified gaps:
{gaps}"""

_TRUNCATED = "\n\n[input truncated]"


def gap_system_prompt(max_gaps: int) -> str:
    """The gap prompt with its ceiling filled in; `str.replace`, because the prompt is full of
    JSON braces that `str.format` would try to read as fields."""
    return GAP_SYSTEM_PROMPT.replace("{max_gaps}", str(max_gaps))


def idea_system_prompt(max_ideas: int) -> str:
    return IDEA_SYSTEM_PROMPT.replace("{max_ideas}", str(max_ideas))


def render_gaps(topic: TopicSettings, synthesis: WeeklySynthesis, max_input_chars: int) -> str:
    """Render the gap prompt from a stored synthesis, which already carries its own references."""
    return _bounded(
        _GAP_TEMPLATE.format(
            name=topic.name,
            keywords=", ".join(topic.keywords) if topic.keywords else "none",
            paper_ids=", ".join(synthesis.paper_ids) or "none",
            synthesis=_synthesis(synthesis),
        ),
        max_input_chars,
    )


def render_ideas(
    topic: TopicSettings,
    gaps: list[ResearchGap],
    paper_ids: list[str],
    max_input_chars: int,
) -> str:
    return _bounded(
        _IDEA_TEMPLATE.format(
            name=topic.name,
            keywords=", ".join(topic.keywords) if topic.keywords else "none",
            paper_ids=", ".join(paper_ids) or "none",
            gaps="\n".join(
                f"- title: {gap.title}\n  description: {gap.description}\n"
                f"  supported by: {', '.join(gap.supporting_paper_ids)}"
                for gap in gaps
            ),
        ),
        max_input_chars,
    )


def _synthesis(synthesis: WeeklySynthesis) -> str:
    sections = [
        ("developments", synthesis.major_developments),
        ("emerging directions", synthesis.emerging_directions),
        ("methods gaining attention", synthesis.methods_gaining_attention),
        ("contradictions", synthesis.contradictions),
        ("common limitations", synthesis.common_limitations),
    ]
    lines: list[str] = []
    for label, findings in sections:
        if not findings:
            continue
        lines.append(f"{label}:")
        lines.extend(
            f"  - {finding.text} [{', '.join(finding.supporting_paper_ids)}]"
            for finding in findings
        )
    for label, values in (
        ("new datasets", synthesis.new_datasets),
        ("new benchmarks", synthesis.new_benchmarks),
        ("changes from history", synthesis.changes_from_history),
    ):
        if values:
            lines.append(f"{label}: {', '.join(values)}")
    return "\n".join(lines) or "the synthesis recorded no findings"


def _bounded(prompt: str, max_input_chars: int) -> str:
    if len(prompt) <= max_input_chars:
        return prompt
    return prompt[:max_input_chars] + _TRUNCATED
