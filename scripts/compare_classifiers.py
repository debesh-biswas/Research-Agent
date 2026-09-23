"""Classifier comparison entry point named by TRD section 47.

Thin wrapper: the metrics themselves live in ``research_agent.classifiers.comparison`` so the CLI
command and this script can never drift.

Usage: python scripts/compare_classifiers.py <topic_id> [runs]
"""

import sys
from pathlib import Path

from research_agent.classifiers.comparison import compare, render
from research_agent.cli import _open_connection
from research_agent.storage.results import SqliteResultRepository


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    topic_id = argv[0]
    runs = int(argv[1]) if len(argv) > 1 else 4
    connection = _open_connection(Path("config/settings.yaml"), Path("config/topics.yaml"))
    active, shadow = SqliteResultRepository(connection).classification_pairs(topic_id, runs)
    if not shadow:
        print(f"No shadow verdicts stored for {topic_id}.", file=sys.stderr)
        return 1

    print(render(compare(active, shadow)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
