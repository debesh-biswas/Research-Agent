"""The reproducibility manifest.

TRD section 33 asks that a run be reproducible: the reporting period, the resolved topic
configuration, the enabled sources, the classifier selection and the model/provider choices must all
be recoverable afterwards. The database holds the results; this holds the inputs that produced them.
"""

from typing import Any

from research_agent.config import ApplicationSettings, TopicSettings
from research_agent.domain.runs import RunRecord

MANIFEST_VERSION = "run_manifest.v1"


def run_manifest(
    run: RunRecord,
    topic: TopicSettings,
    application: ApplicationSettings,
    counts: dict[str, int],
    models_used: list[str],
    prompt_versions: dict[str, str],
    queries: list[str] | None = None,
) -> dict[str, Any]:
    """Describe one run completely enough to repeat it, with no secret in it.

    Only names are recorded for providers and models. API keys live in the environment and are never
    read here, so a manifest is safe to keep beside the report or attach to a bug report.
    """
    return {
        "manifest_version": MANIFEST_VERSION,
        "run": {
            "id": run.id,
            "topic_id": run.topic_id,
            "started_at": run.started_at.isoformat(),
            "completed_at": None if run.completed_at is None else run.completed_at.isoformat(),
            "status": run.status,
            "duration_seconds": run.duration_seconds,
        },
        "topic": {
            "id": topic.id,
            "name": topic.name,
            "enabled": topic.enabled,
            "lookback_days": topic.lookback_days,
            "keywords": list(topic.keywords),
            "limits": topic.limits.model_dump(),
            "scheduling": topic.scheduling.model_dump(),
        },
        "sources_enabled": sorted(
            name
            for name, enabled in (
                ("openalex", topic.discovery.openalex),
                ("semantic_scholar", topic.discovery.semantic_scholar),
                ("arxiv", topic.discovery.arxiv),
            )
            if enabled
        ),
        "screening": {"service": "semantic_screening"},
        "models": {
            "strong_provider": application.strong_model_provider,
            "local_model": application.models.local.model,
            "nim_model": application.models.nim.model,
            "models_used": sorted(set(models_used)),
        },
        "prompt_versions": dict(sorted(prompt_versions.items())),
        "queries": list(queries or []),
        "settings": {
            "concurrency": application.concurrency.model_dump(),
            "retries": application.retries.model_dump(),
            "deduplication": application.deduplication.model_dump(),
            "queries": application.queries.model_dump(),
            "selection": application.selection.model_dump(),
            "analysis": application.analysis.model_dump(),
            "synthesis": application.synthesis.model_dump(),
            "ideation": application.ideation.model_dump(),
            "reports": application.reports.model_dump(),
        },
        "counts": dict(sorted(counts.items())),
    }
