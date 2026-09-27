"""The ideation artifact: gaps and ideas as Markdown, for a reader and for the F16 report.

Deterministic order, and all of it model-produced, so every value is collapsed to one line and
stripped of the markup that could break the document.
"""

from research_agent.domain.analysis import ResearchGap, ResearchIdea


def render_ideation(gaps: list[ResearchGap], ideas: list[ResearchIdea]) -> str:
    """Render one run's gaps and ideas, each with the papers that support it."""
    lines = ["# Research gaps and ideas", ""]
    lines.extend(_gaps(gaps))
    lines.extend(_ideas(ideas))
    return "\n".join(lines).rstrip() + "\n"


def _gaps(gaps: list[ResearchGap]) -> list[str]:
    lines = ["## Gaps", ""]
    if not gaps:
        lines.append("No gap was supported by a paper in this run.")
        return lines
    for gap in gaps:
        confidence = "unstated" if gap.confidence is None else f"{gap.confidence:.2f}"
        lines.extend(
            [
                f"### {_inline(gap.title)}",
                "",
                f"- **Confidence:** {confidence}",
                f"- **Supported by:** {', '.join(gap.supporting_paper_ids)}",
                f"- **Model:** {gap.model_provider}/{gap.model_name} ({gap.prompt_version})",
                "",
                _inline(gap.description),
                "",
            ]
        )
    return lines


def _ideas(ideas: list[ResearchIdea]) -> list[str]:
    lines = ["## Ideas", ""]
    if not ideas:
        lines.append("No idea survived reference validation.")
        return lines
    for idea in ideas:
        lines.extend(
            [
                f"### {_inline(idea.title)}",
                "",
                f"- **Addresses gap:** {_inline(idea.identified_gap)}",
                f"- **Supported by:** {', '.join(idea.supporting_paper_ids)}",
                f"- **Model:** {idea.model_provider}/{idea.model_name} ({idea.prompt_version})",
                "",
                f"**Hypothesis.** {_inline(idea.hypothesis)}",
                "",
                f"**Motivation.** {_inline(idea.motivation)}",
                "",
                f"**Proposed direction.** {_inline(idea.proposed_direction)}",
                "",
                f"**Evaluation plan.** {_inline(idea.evaluation_plan)}",
                "",
            ]
        )
        if idea.risks:
            lines.extend(["**Risks.**", "", *(f"- {_inline(risk)}" for risk in idea.risks), ""])
    return lines


def _inline(value: str) -> str:
    return " ".join(value.replace("`", "'").split())
