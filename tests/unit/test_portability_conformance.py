"""Interface conformance for the AWS substitutions (TRD sections 50-51).

Each test replaces one local backend with an in-memory stand-in shaped like its AWS counterpart and
drives the real application code through it. Nothing here imports boto3 or touches a network: the
claim being proved is that the boundaries are sufficient, not that a particular SDK works.
"""

import json
import sqlite3
from datetime import UTC, date, datetime, time
from pathlib import Path, PurePosixPath

import pytest
from pydantic import ValidationError

from research_agent.analysis.cards import render_card
from research_agent.config import SchedulingSettings, TopicSettings
from research_agent.documents.parser import load_parsed
from research_agent.domain.analysis import PaperAnalysis
from research_agent.domain.documents import ParsedPaper, ParsedSection
from research_agent.domain.papers import PaperCandidate
from research_agent.operations.scheduling import (
    EventBridgeScheduler,
    ScheduleRequest,
    build_scheduler,
    command,
)
from research_agent.portability.profiles import (
    AWS_PROFILE,
    FORBIDDEN_SERVICES,
    LOCAL_PROFILE,
    DeploymentProfile,
)
from research_agent.portability.secrets import (
    EnvironmentSecrets,
    MissingSecretError,
    ParameterStoreSecrets,
    SecretMapping,
    build_resolver,
)
from research_agent.reports.naming import report_filename
from research_agent.storage.artifacts import ArtifactKind, ArtifactPathError, safe_name
from tests.unit.conftest import candidate

TOPIC_ID = "spatial_intelligence"


class ObjectStore:
    """An `ArtifactStore` backed by a dict, keyed the way S3 keys a bucket.

    This is the substitution the TRD asks for: the same `ArtifactStore` Protocol, with flat string
    keys and no filesystem underneath.
    """

    def __init__(self, bucket: str = "research-agent") -> None:
        self.bucket = bucket
        self.objects: dict[str, bytes] = {}

    def key_for(self, topic_id: str, kind: ArtifactKind, name: str) -> str:
        safe = safe_name(name)
        if safe != name.casefold() and "/" in name:
            raise ArtifactPathError(f"unsafe object name: {name!r}")
        return f"topics/{safe_name(topic_id)}/{kind}/{safe}"

    def path_for(self, topic_id: str, kind: ArtifactKind, name: str) -> Path:
        return Path(str(PurePosixPath(f"s3://{self.bucket}") / self.key_for(topic_id, kind, name)))

    def write_bytes(self, topic_id: str, kind: ArtifactKind, name: str, data: bytes) -> Path:
        self.objects[self.key_for(topic_id, kind, name)] = data
        return self.path_for(topic_id, kind, name)

    def write_text(self, topic_id: str, kind: ArtifactKind, name: str, text: str) -> Path:
        return self.write_bytes(topic_id, kind, name, text.encode("utf-8"))

    def read_text(self, topic_id: str, kind: ArtifactKind, name: str) -> str:
        return self.objects[self.key_for(topic_id, kind, name)].decode("utf-8")

    def exists(self, topic_id: str, kind: ArtifactKind, name: str) -> bool:
        return self.key_for(topic_id, kind, name) in self.objects

    def names(self, topic_id: str, kind: ArtifactKind) -> list[str]:
        prefix = f"topics/{safe_name(topic_id)}/{kind}/"
        return sorted(key.removeprefix(prefix) for key in self.objects if key.startswith(prefix))

    def delete(self, topic_id: str, kind: ArtifactKind, name: str) -> None:
        self.objects.pop(self.key_for(topic_id, kind, name), None)


class DocumentTable:
    """A `PaperRepository`-shaped store keyed by partition and sort key, as DynamoDB would be."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {}

    def put(self, partition: str, sort: str, item: dict[str, object]) -> None:
        self.items[(partition, sort)] = dict(item)

    def get(self, partition: str, sort: str) -> dict[str, object] | None:
        found = self.items.get((partition, sort))
        return None if found is None else dict(found)

    def query(self, partition: str) -> list[dict[str, object]]:
        return [dict(item) for (key, _sort), item in sorted(self.items.items()) if key == partition]


def analysis(paper_id: str = "doi_10_1234_abcd") -> PaperAnalysis:
    return PaperAnalysis(
        paper_id=paper_id,
        research_problem="Agents cannot reason about unseen rooms.",
        main_contribution="A spatial memory module.",
        method="A transformer over a metric map.",
        topic_relevance="Directly on topic.",
        model_provider="nvidia_nim",
        model_name="some-model",
        prompt_version="paper_analysis.v1",
    )


def test_the_local_profile_is_the_default() -> None:
    assert LOCAL_PROFILE.target == "local"
    assert (LOCAL_PROFILE.artifacts, LOCAL_PROFILE.metadata) == ("filesystem", "sqlite")
    assert (LOCAL_PROFILE.scheduler, LOCAL_PROFILE.logs) == ("launchd", "stderr")
    assert DeploymentProfile() == LOCAL_PROFILE, "constructing one with no arguments stays local"


def test_the_aws_profile_replaces_every_boundary() -> None:
    assert AWS_PROFILE.target == "aws"
    assert (AWS_PROFILE.artifacts, AWS_PROFILE.metadata) == ("s3", "dynamodb")
    assert (AWS_PROFILE.scheduler, AWS_PROFILE.logs) == ("eventbridge", "cloudwatch")
    assert AWS_PROFILE.secrets == "parameter_store"
    assert AWS_PROFILE.worker == "ec2_free_tier"


def test_a_local_profile_cannot_use_a_remote_backend() -> None:
    with pytest.raises(ValidationError, match="cannot use remote backends"):
        DeploymentProfile(artifacts="s3")


def test_an_aws_profile_must_actually_replace_something() -> None:
    with pytest.raises(ValidationError, match="must replace at least one backend"):
        DeploymentProfile(target="aws")


def test_an_aws_profile_cannot_schedule_locally() -> None:
    with pytest.raises(ValidationError, match="schedules with eventbridge"):
        DeploymentProfile(target="aws", artifacts="s3", scheduler="cron")


def test_the_whole_workflow_is_not_allowed_inside_one_lambda() -> None:
    with pytest.raises(ValidationError, match="one Lambda invocation"):
        DeploymentProfile(target="aws", artifacts="s3", scheduler="eventbridge", worker="lambda")


@pytest.mark.parametrize("service", sorted(FORBIDDEN_SERVICES))
def test_expensive_services_are_refused(service: str) -> None:
    with pytest.raises(ValidationError, match="not permitted"):
        DeploymentProfile(target="aws", artifacts="s3", scheduler="eventbridge", services=[service])


def test_an_expensive_service_is_allowed_only_when_free_plan_only_is_waived() -> None:
    profile = DeploymentProfile(
        target="aws",
        artifacts="s3",
        scheduler="eventbridge",
        services=["rds"],
        free_plan_only=False,
    )

    assert profile.services == ["rds"], "the guardrail is explicit, not silent"


def test_artifacts_round_trip_through_an_object_store() -> None:
    """filesystem → S3: the same code writes a card and reads a parse back."""
    store = ObjectStore()

    card_path = store.write_text(
        TOPIC_ID, "analyses", "doi_10_1234_abcd.md", render_card(analysis(), candidate())
    )
    parsed = ParsedPaper(
        paper_id="doi_10_1234_abcd",
        source_pdf_path="s3://research-agent/topics/x/papers/doi_10_1234_abcd.pdf",
        sections=[ParsedSection(title="Results", text="SPL rises.")],
        parser_name="docling",
    )
    store.write_text(TOPIC_ID, "parsed", "doi_10_1234_abcd.json", parsed.model_dump_json())

    # `Path` collapses the `//` in an s3 URI, so the key is what this asserts on.
    assert store.key_for(TOPIC_ID, "analyses", "doi_10_1234_abcd.md") == (
        "topics/spatial_intelligence/analyses/doi_10_1234_abcd.md"
    )
    assert str(card_path).endswith("topics/spatial_intelligence/analyses/doi_10_1234_abcd.md")
    assert "## Main contribution" in store.read_text(TOPIC_ID, "analyses", "doi_10_1234_abcd.md")
    loaded = load_parsed(store, "doi_10_1234_abcd", TOPIC_ID)
    assert loaded is not None and loaded.sections[0].title == "Results"


def test_the_report_lookup_works_over_an_object_store() -> None:
    """`ReportService.latest` only needs `names`, which an object listing provides."""
    store = ObjectStore()
    store.write_text(TOPIC_ID, "reports", report_filename(date(2026, 9, 27)), "# first")
    store.write_text(TOPIC_ID, "reports", report_filename(date(2026, 10, 4)), "# second")

    assert store.names(TOPIC_ID, "reports") == [
        "2026-09-27_weekly_report.md",
        "2026-10-04_weekly_report.md",
    ]


def test_an_object_store_refuses_a_key_that_escapes_its_prefix() -> None:
    store = ObjectStore()

    with pytest.raises(ArtifactPathError):
        store.write_text(TOPIC_ID, "reports", "../../etc/passwd", "nope")


def test_paper_metadata_round_trips_through_a_document_table() -> None:
    """SQLite → DynamoDB: the domain model is the contract, not the SQL."""
    table = DocumentTable()
    paper = candidate(canonical_id="doi_10_1234_abcd", doi="10.1234/abcd")

    table.put("papers", paper.canonical_id or "", json.loads(paper.model_dump_json()))
    stored = table.get("papers", "doi_10_1234_abcd")

    assert stored is not None
    # Rehydrated through the same schema the SQLite repository uses: the model is the contract.
    assert PaperCandidate.model_validate(stored) == paper


def test_analyses_round_trip_through_a_document_table() -> None:
    table = DocumentTable()
    stored_analysis = analysis()

    table.put("analyses", stored_analysis.paper_id, json.loads(stored_analysis.model_dump_json()))
    item = table.get("analyses", stored_analysis.paper_id)

    assert item is not None
    assert PaperAnalysis.model_validate(item) == stored_analysis


def test_a_document_table_query_is_ordered_and_scoped() -> None:
    table = DocumentTable()
    table.put("analyses", "b", {"paper_id": "b"})
    table.put("analyses", "a", {"paper_id": "a"})
    table.put("papers", "c", {"paper_id": "c"})

    assert [item["paper_id"] for item in table.query("analyses")] == ["a", "b"]


def test_the_scheduler_factory_covers_every_backend() -> None:
    assert build_scheduler("launchd").backend == "launchd"
    assert build_scheduler("cron").backend == "cron"
    assert build_scheduler("eventbridge").backend == "eventbridge"


def test_an_eventbridge_schedule_is_deterministic_and_runs_the_same_command() -> None:
    request = ScheduleRequest(
        topic_id=TOPIC_ID, scheduling=SchedulingSettings(day="wednesday"), at=time(6, 15)
    )

    first = EventBridgeScheduler().render(request)
    second = EventBridgeScheduler().render(request)

    assert first.content == second.content
    payload = json.loads(first.content)
    assert payload["ScheduleExpression"] == "cron(15 6 ? * WED *)"
    assert payload["ScheduleExpressionTimezone"] == "UTC"
    assert json.loads(payload["Target"]["Input"])["command"] == command(request)
    assert payload["Target"]["RetryPolicy"]["MaximumRetryAttempts"] == 0
    assert "aws scheduler create-schedule" in first.install_hint


def test_an_eventbridge_schedule_carries_no_credential() -> None:
    artifact = EventBridgeScheduler().render(
        ScheduleRequest(topic_id=TOPIC_ID, scheduling=SchedulingSettings())
    )

    lowered = artifact.content.lower()
    assert "api_key" not in lowered and "secret" not in lowered
    assert "research_agent_" not in lowered


def test_environment_secrets_resolve_by_prefixed_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_NIM_API_KEY", "local-value")
    resolver = EnvironmentSecrets()

    assert resolver.get("nim_api_key") == "local-value"
    assert resolver.require("nim_api_key") == "local-value"
    assert resolver.get("absent_secret") is None


def test_a_missing_secret_names_the_secret_and_not_a_value() -> None:
    with pytest.raises(MissingSecretError) as raised:
        EnvironmentSecrets().require("nim_api_key")

    assert "nim_api_key" in str(raised.value)


def test_parameter_store_maps_a_logical_name_to_a_path() -> None:
    """environment → Parameter Store: the same logical names, resolved remotely."""
    fetched: list[str] = []

    def fetch(parameter_name: str) -> str | None:
        fetched.append(parameter_name)
        return "remote-value" if parameter_name.endswith("nim_api_key") else None

    resolver = ParameterStoreSecrets("/research-agent/prod", fetch)

    assert resolver.require("nim_api_key") == "remote-value"
    assert resolver.get("semantic_scholar_api_key") is None
    assert fetched == [
        "/research-agent/prod/nim_api_key",
        "/research-agent/prod/semantic_scholar_api_key",
    ]


def test_a_remote_secret_backend_never_falls_back_to_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_NIM_API_KEY", "local-value")

    with pytest.raises(MissingSecretError, match="needs a fetcher"):
        build_resolver("secrets_manager")


def test_the_resolver_factory_covers_every_backend() -> None:
    assert build_resolver("environment").backend == "environment"
    assert build_resolver("parameter_store", lambda name: None).backend == "parameter_store"
    assert build_resolver("secrets_manager", lambda name: None).backend == "secrets_manager"
    with pytest.raises(ValueError, match="unknown secret backend"):
        build_resolver("vault")


def test_the_secret_mapping_names_exactly_what_the_application_needs() -> None:
    assert SecretMapping().names() == [
        "nim_api_key",
        "openalex_mailto",
        "semantic_scholar_api_key",
    ]


def test_logs_are_one_json_object_per_line_which_is_what_cloudwatch_ingests() -> None:
    """local JSON logs → CloudWatch: no adapter needed, only a format guarantee."""
    import logging
    from io import StringIO

    from research_agent.observability.logging import JsonFormatter, SecretRedactingFilter

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactingFilter())
    logger = logging.getLogger("cloudwatch-conformance")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info("stage complete", extra={"run_id": "run1", "node_name": "analyze"})
    logger.warning("stage degraded", extra={"run_id": "run1", "error_type": "MODEL_API_ERROR"})

    lines = [line for line in stream.getvalue().splitlines() if line]
    assert len(lines) == 2
    for line in lines:
        payload = json.loads(line)
        assert payload["run_id"] == "run1"
        assert datetime.fromisoformat(payload["timestamp"]).tzinfo is not None


def test_the_local_suite_still_uses_the_local_backends(connection: sqlite3.Connection) -> None:
    """The regression guard: nothing here made a remote backend necessary locally."""
    from research_agent.storage.artifacts import LocalArtifactStore
    from research_agent.storage.papers import SqlitePaperRepository

    repository = SqlitePaperRepository(connection)
    paper_id = repository.upsert(candidate(doi="10.1234/abcd"))

    assert repository.get(paper_id) is not None
    assert isinstance(LocalArtifactStore(Path("/tmp")), LocalArtifactStore)
    assert LOCAL_PROFILE.target == "local"


def test_topics_remain_provider_neutral() -> None:
    """A topic carries no backend detail, so the same topic runs under either profile."""
    topic = TopicSettings.model_validate({"id": TOPIC_ID, "name": "Spatial Intelligence"})
    dumped = json.dumps(topic.model_dump(), default=str).lower()

    for term in ("s3", "dynamodb", "bucket", "arn", "/users/", "sqlite"):
        assert term not in dumped


def test_datetimes_crossing_the_boundary_stay_timezone_aware() -> None:
    paper = candidate(doi="10.1234/abcd")

    assert paper.discovered_at.tzinfo is not None
    assert paper.discovered_at.astimezone(UTC).tzinfo is UTC
