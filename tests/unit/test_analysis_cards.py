from datetime import date

from research_agent.analysis.cards import render_card
from research_agent.domain.analysis import Claim, PaperAnalysis
from tests.unit.conftest import candidate


def analysis(**overrides: object) -> PaperAnalysis:
    payload: dict[str, object] = {
        "paper_id": "doi_10_1234_abcd",
        "research_problem": "Agents cannot reason about unseen rooms.",
        "main_contribution": "A persistent spatial memory module.",
        "method": "A transformer over a metric map.",
        "datasets": ["HM3D"],
        "benchmarks": ["ObjectNav"],
        "experimental_setup": "Ten episodes per scene.",
        "main_results": ["+7 SPL over the baseline"],
        "strengths": ["Thorough ablations"],
        "limitations": ["Simulation only"],
        "key_claims": [Claim(text="Memory improves navigation", source_section="Results", page=7)],
        "related_work": ["Neural SLAM"],
        "topic_relevance": "Directly on topic.",
        "model_provider": "nvidia_nim",
        "model_name": "some-model",
        "prompt_version": "paper_analysis.v1",
    }
    payload.update(overrides)
    return PaperAnalysis.model_validate(payload)


def paper() -> object:
    return candidate(
        doi="10.1234/abcd",
        authors=["Ada Lovelace", "Grace Hopper"],
        publication_date=date(2026, 9, 18),
        venue="CoRL",
    )


def test_a_card_is_deterministic_and_ordered() -> None:
    first = render_card(analysis(), paper())  # type: ignore[arg-type]
    second = render_card(analysis(), paper())  # type: ignore[arg-type]

    assert first == second
    headings = [line for line in first.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Research problem",
        "## Main contribution",
        "## Method",
        "## Experimental setup",
        "## Datasets",
        "## Benchmarks",
        "## Main results",
        "## Strengths",
        "## Limitations",
        "## Key claims",
        "## Related work",
        "## Topic relevance",
    ]
    assert first.startswith("# Embodied Spatial Intelligence for Robots")
    assert "- **Model:** nvidia_nim/some-model" in first
    assert "- Memory improves navigation (section: Results; page 7)" in first


def test_an_abstract_only_analysis_says_so() -> None:
    card = render_card(analysis(abstract_only=True), paper())  # type: ignore[arg-type]

    assert "> Abstract-only analysis" in card


def test_empty_sections_are_omitted() -> None:
    card = render_card(
        analysis(datasets=[], benchmarks=[], experimental_setup=None, key_claims=[]),
        paper(),  # type: ignore[arg-type]
    )

    assert "## Datasets" not in card
    assert "## Experimental setup" not in card
    assert "## Key claims" not in card


def test_a_claim_without_provenance_is_labelled_rather_than_implied() -> None:
    card = render_card(
        analysis(key_claims=[Claim(text="Memory helps")]),
        paper(),  # type: ignore[arg-type]
    )

    assert "- Memory helps (provenance unavailable)" in card


def test_untrusted_text_cannot_inject_markup() -> None:
    card = render_card(
        analysis(
            main_contribution="```sh\nrm -rf /\n```",
            main_results=["# Not a heading\nsecond line"],
        ),
        paper(),  # type: ignore[arg-type]
    )

    assert "```" not in card
    assert "- # Not a heading second line" in card
    assert "\nrm -rf /" not in card


def test_paragraph_breaks_survive_but_headings_do_not() -> None:
    card = render_card(analysis(method="First para.\n\nSecond para."), paper())  # type: ignore[arg-type]

    assert "First para.\n\nSecond para." in card
