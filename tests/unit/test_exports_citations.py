from datetime import UTC, date, datetime

from research_agent.domain.papers import PaperCandidate, SourceReference
from research_agent.exports.citations import to_bibtex, to_ris


def paper(**fields: object) -> PaperCandidate:
    payload: dict[str, object] = {
        "title": "Topological Maps for Home Robots",
        "authors": ["Ada Lovelace", "Grace Hopper"],
        "publication_date": date(2026, 9, 18),
        "discovered_at": datetime(2026, 9, 20, tzinfo=UTC),
        "sources": [SourceReference(source="openalex", source_id="W1", url="https://x.org/w1")],
    }
    payload.update(fields)
    return PaperCandidate.model_validate(payload)


def test_bibtex_for_an_article_and_an_arxiv_preprint() -> None:
    text = to_bibtex(
        [
            paper(doi="10.1234/abcd", venue="CVPR"),
            paper(title="Semantic SLAM", authors=["Alan Turing"], arxiv_id="2610.35817"),
        ]
    )

    assert text == (
        "@article{lovelace2026topological,\n"
        "  title = {{Topological Maps for Home Robots}},\n"
        "  author = {Ada Lovelace and Grace Hopper},\n"
        "  year = {2026},\n"
        "  journal = {CVPR},\n"
        "  doi = {10.1234/abcd},\n"
        "  url = {https://doi.org/10.1234/abcd}\n"
        "}\n"
        "\n"
        "@misc{turing2026semantic,\n"
        "  title = {{Semantic SLAM}},\n"
        "  author = {Alan Turing},\n"
        "  year = {2026},\n"
        "  eprint = {2610.35817},\n"
        "  archiveprefix = {arXiv},\n"
        "  url = {https://arxiv.org/abs/2610.35817}\n"
        "}\n"
    )


def test_bibtex_keys_are_ascii_and_unique_and_special_characters_are_escaped() -> None:
    papers = [
        paper(authors=["José Núñez"], title="Maps & Memory: 100% of {rooms}"),
        paper(authors=["José Núñez"], title="Maps & Memory: 100% of {rooms}"),
        paper(authors=[], title="Untitled_Draft", publication_date=None),
    ]

    text = to_bibtex(papers)

    assert "@misc{nunez2026mapsa," in text and "@misc{nunez2026mapsb," in text
    assert "@misc{anonndpaper," not in text and "@misc{anonnduntitleddraft," in text
    assert r"Maps \& Memory: 100\% of \{rooms\}" in text
    assert r"Untitled\_Draft" in text
    body = text.replace(r"\{", "").replace(r"\}", "")
    assert body.count("{") == body.count("}"), "every entry's braces balance"


def test_ris_records_one_per_paper_with_a_terminator() -> None:
    text = to_ris([paper(doi="10.1234/abcd", venue="CVPR"), paper(title="No venue")])

    first, second = text.split("ER  -\n")[:2]
    assert first.splitlines() == [
        "TY  - JOUR",
        "TI  - Topological Maps for Home Robots",
        "AU  - Ada Lovelace",
        "AU  - Grace Hopper",
        "PY  - 2026",
        "DA  - 2026/09/18",
        "JO  - CVPR",
        "DO  - 10.1234/abcd",
        "UR  - https://doi.org/10.1234/abcd",
    ]
    assert second.startswith("TY  - GEN\nTI  - No venue\n")
    assert "UR  - https://x.org/w1" in second, "falls back to the source page"
    assert text.count("ER  -") == 2
