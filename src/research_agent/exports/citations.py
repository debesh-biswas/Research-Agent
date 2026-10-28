"""BibTeX and RIS for reference managers (Zotero, Mendeley, EndNote, JabRef).

Pure functions of the stored metadata, so the same papers always export to the same text and the
same citation keys. A paper with a venue is exported as an article; anything else as a preprint
or generic record, since the library does not know a paper's publication type.
"""

import re
import unicodedata
from collections import Counter

from research_agent.domain.papers import PaperCandidate

_BIBTEX_SPECIAL = str.maketrans(
    {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "%": r"\%", "&": r"\&", "#": r"\#",
     "_": r"\_", "$": r"\$", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
)  # fmt: skip


def to_bibtex(papers: list[PaperCandidate]) -> str:
    """One entry per paper, keyed `<surname><year><firstword>` with a/b/… for collisions."""
    keys = _keys(papers)
    return "\n".join(_bibtex_entry(paper, key) for paper, key in zip(papers, keys, strict=True))


def to_ris(papers: list[PaperCandidate]) -> str:
    return "".join(_ris_record(paper) for paper in papers)


def _keys(papers: list[PaperCandidate]) -> list[str]:
    bases = [_key_base(paper) for paper in papers]
    totals = Counter(bases)
    seen: Counter[str] = Counter()
    keys = []
    for base in bases:
        if totals[base] == 1:
            keys.append(base)
            continue
        keys.append(base + "abcdefghijklmnopqrstuvwxyz"[seen[base] % 26])
        seen[base] += 1
    return keys


def _key_base(paper: PaperCandidate) -> str:
    surname = paper.authors[0].split()[-1] if paper.authors else "anon"
    year = str(paper.publication_date.year) if paper.publication_date else "nd"
    words = [word for word in re.findall(r"[A-Za-z0-9]+", _ascii(paper.title)) if len(word) > 3]
    return (_ascii(surname) + year + (words[0] if words else "paper")).lower()


def _ascii(text: str) -> str:
    """Keys must be plain ASCII letters and digits; accents fold to their base letter."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9 ]", "", folded)


def _bibtex_entry(paper: PaperCandidate, key: str) -> str:
    fields: list[tuple[str, str]] = [("title", "{" + _escape(paper.title) + "}")]
    if paper.authors:
        fields.append(("author", " and ".join(_escape(author) for author in paper.authors)))
    if paper.publication_date:
        fields.append(("year", str(paper.publication_date.year)))
    if paper.venue:
        fields.append(("journal", _escape(paper.venue)))
    if paper.doi:
        fields.append(("doi", paper.doi))
    if paper.arxiv_id:
        fields += [("eprint", paper.arxiv_id), ("archiveprefix", "arXiv")]
    url = _url(paper)
    if url:
        fields.append(("url", url))
    kind = "article" if paper.venue else "misc"
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
    return f"@{kind}{{{key},\n{body}\n}}\n"


def _escape(text: str) -> str:
    return " ".join(text.split()).translate(_BIBTEX_SPECIAL)


def _ris_record(paper: PaperCandidate) -> str:
    lines = [("TY", "JOUR" if paper.venue else "GEN"), ("TI", " ".join(paper.title.split()))]
    lines += [("AU", author) for author in paper.authors]
    if paper.publication_date:
        lines.append(("PY", str(paper.publication_date.year)))
        lines.append(("DA", paper.publication_date.strftime("%Y/%m/%d")))
    if paper.venue:
        lines.append(("JO", paper.venue))
    if paper.doi:
        lines.append(("DO", paper.doi))
    url = _url(paper)
    if url:
        lines.append(("UR", url))
    lines.append(("ER", ""))
    return "".join(f"{tag}  - {value}".rstrip() + "\n" for tag, value in lines)


def _url(paper: PaperCandidate) -> str | None:
    if paper.doi:
        return f"https://doi.org/{paper.doi}"
    if paper.arxiv_id:
        return f"https://arxiv.org/abs/{paper.arxiv_id}"
    return next((source.url for source in paper.sources if source.url), None)
