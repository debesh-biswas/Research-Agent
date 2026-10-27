"""Deterministic report filenames.

One report per topic per reporting period, named from the period's end date, so the newest report
is also the last one in sorted order.
"""

from datetime import date

_SUFFIX = "_weekly_report.md"


def report_filename(period_end: date) -> str:
    """`YYYY-MM-DD_weekly_report.md`, which the artifact store then makes path-safe."""
    return f"{period_end.isoformat()}{_SUFFIX}"


def is_report(name: str) -> bool:
    return name.endswith(_SUFFIX)
