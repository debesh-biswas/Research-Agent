from research_agent.domain.analysis import ResearchGap, ResearchIdea
from research_agent.ideation.cards import render_ideation


def gap(**overrides: object) -> ResearchGap:
    payload: dict[str, object] = {
        "title": "No long-horizon benchmark",
        "description": "Existing benchmarks stop at 50 steps.",
        "supporting_paper_ids": ["p1", "p2"],
        "confidence": 0.6,
        "model_provider": "nvidia_nim",
        "model_name": "some-model",
        "prompt_version": "research_gaps.v1",
    }
    payload.update(overrides)
    return ResearchGap.model_validate(payload)


def idea(**overrides: object) -> ResearchIdea:
    payload: dict[str, object] = {
        "title": "Persistent map benchmark",
        "hypothesis": "Longer horizons expose memory failures.",
        "motivation": "Current scores saturate.",
        "supporting_paper_ids": ["p1"],
        "identified_gap": "No long-horizon benchmark",
        "proposed_direction": "Extend ObjectNav episodes.",
        "evaluation_plan": "Compare SPL across horizons.",
        "risks": ["Compute cost"],
        "model_provider": "nvidia_nim",
        "model_name": "some-model",
        "prompt_version": "research_ideas.v1",
    }
    payload.update(overrides)
    return ResearchIdea.model_validate(payload)


def test_the_artifact_is_deterministic_and_traceable() -> None:
    first = render_ideation([gap()], [idea()])
    second = render_ideation([gap()], [idea()])

    assert first == second
    assert "### No long-horizon benchmark" in first
    assert "- **Supported by:** p1, p2" in first
    assert "- **Confidence:** 0.60" in first
    assert "- **Addresses gap:** No long-horizon benchmark" in first
    assert "**Evaluation plan.** Compare SPL across horizons." in first
    assert first.index("## Gaps") < first.index("## Ideas")


def test_unstated_confidence_is_labelled() -> None:
    assert "- **Confidence:** unstated" in render_ideation([gap(confidence=None)], [])


def test_nothing_supported_says_so_rather_than_rendering_empty_sections() -> None:
    card = render_ideation([], [])

    assert "No gap was supported" in card
    assert "No idea survived" in card


def test_an_idea_without_risks_omits_the_section() -> None:
    assert "**Risks.**" not in render_ideation([gap()], [idea(risks=[])])


def test_untrusted_text_cannot_inject_markup() -> None:
    card = render_ideation([gap(title="```sh\nrm -rf /\n```")], [])

    assert "```" not in card
    assert "\nrm -rf /" not in card
