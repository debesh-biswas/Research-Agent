"""Typed configuration loading and validation."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class ConfigurationError(ValueError):
    """Raised when a configuration file cannot be loaded safely."""


class StrictModel(BaseModel):
    """Base model that rejects unknown configuration keys."""

    model_config = ConfigDict(extra="forbid")


class ConcurrencySettings(StrictModel):
    discovery: int = Field(default=3, gt=0)
    downloads: int = Field(default=4, gt=0)
    analysis: int = Field(default=2, gt=0)


class RetrySettings(StrictModel):
    academic_apis: int = Field(default=3, ge=0)
    nim: int = Field(default=2, ge=0)
    classifier_repair: int = Field(default=1, ge=0)
    pdf_download: int = Field(default=2, ge=0)


class DeduplicationSettings(StrictModel):
    title_similarity: float = Field(default=95.0, ge=0, le=100)
    require_author_overlap: bool = True


class SourceSettings(StrictModel):
    requests_per_second: float = Field(default=2.0, gt=0)
    timeout_seconds: float = Field(default=20.0, gt=0)
    max_page_size: int = Field(default=100, gt=0)


class DiscoveryClientSettings(StrictModel):
    """Per-provider pacing and credentials; limits differ, so they are never global."""

    openalex: SourceSettings = SourceSettings(requests_per_second=5.0)
    semantic_scholar: SourceSettings = SourceSettings(requests_per_second=0.2)
    arxiv: SourceSettings = SourceSettings(requests_per_second=0.33)
    openalex_mailto: str | None = None
    semantic_scholar_api_key: str | None = None


class ModelEndpointSettings(StrictModel):
    """One OpenAI-compatible chat-completions endpoint."""

    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen3:8b"
    api_key: str | None = None
    requests_per_second: float = Field(default=4.0, gt=0)
    timeout_seconds: float = Field(default=120.0, gt=0)
    max_output_tokens: int = Field(default=2048, gt=0)
    temperature: float = Field(default=0.2, ge=0, le=2)


class NimEndpointSettings(ModelEndpointSettings):
    """NIM defaults live on their own class so a partial override keeps the rest of them."""

    base_url: str = "https://integrate.api.nvidia.com/v1"
    model: str = "meta/llama-3.1-70b-instruct"


class ModelSettings(StrictModel):
    """Local inference is always configured; NIM is optional and keyed from the environment."""

    local: ModelEndpointSettings = Field(default_factory=ModelEndpointSettings)
    nim: NimEndpointSettings = Field(default_factory=NimEndpointSettings)


class QuerySettings(StrictModel):
    """Bounds for a generated search plan; TRD section 17 asks for roughly five to twenty."""

    min_queries: int = Field(default=5, gt=0)
    max_queries: int = Field(default=20, gt=0)
    history_syntheses: int = Field(default=1, ge=0)

    @model_validator(mode="after")
    def require_monotonic_bounds(self) -> "QuerySettings":
        if self.min_queries > self.max_queries:
            raise ValueError("min_queries cannot exceed max_queries")
        return self


class ClassifierASettings(StrictModel):
    """Tuning for the lightweight classifier; thresholds set both relevance and action."""

    deep_read_at: float = Field(default=0.6, ge=0, le=1)
    summarize_at: float = Field(default=0.3, ge=0, le=1)
    embedding_model: str | None = None
    """Enables the embedding half of the score; without it Classifier A is purely lexical."""
    embedding_weight: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def require_ordered_thresholds(self) -> "ClassifierASettings":
        if self.summarize_at >= self.deep_read_at:
            raise ValueError("summarize_at must be below deep_read_at")
        return self


class ClassifierBSettings(StrictModel):
    """Bounds for the LLM classifier prompt; the runtime and model come from `models.local`."""

    max_abstract_chars: int = Field(default=2000, gt=0)


class SelectionSettings(StrictModel):
    """Thresholds beneath the classifier's own action; limits live in `ResourceLimits`."""

    min_relevance_score: float = Field(default=0.3, ge=0, le=1)
    require_action: bool = True
    """When true, a paper the classifier marked `ignore` is never selected whatever it scored."""


class ApplicationSettings(BaseSettings):
    """Local application settings with environment-first precedence."""

    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_AGENT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    storage_backend: Literal["local"] = "local"
    metadata_backend: Literal["sqlite"] = "sqlite"
    scheduler_backend: Literal["launchd", "cron", "none"] = "launchd"
    strong_model_provider: Literal["local", "nvidia_nim"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    data_directory: Path = Path("data")
    concurrency: ConcurrencySettings = Field(default_factory=ConcurrencySettings)
    retries: RetrySettings = Field(default_factory=RetrySettings)
    deduplication: DeduplicationSettings = Field(default_factory=DeduplicationSettings)
    sources: DiscoveryClientSettings = Field(default_factory=DiscoveryClientSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    queries: QuerySettings = Field(default_factory=QuerySettings)
    classifier_a: ClassifierASettings = Field(default_factory=ClassifierASettings)
    classifier_b: ClassifierBSettings = Field(default_factory=ClassifierBSettings)
    selection: SelectionSettings = Field(default_factory=SelectionSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Make process environment and .env values override YAML initializer values."""
        del settings_cls
        return env_settings, dotenv_settings, init_settings, file_secret_settings


class ClassifierSettings(StrictModel):
    active: Literal["A", "B"] = "A"
    shadow: Literal["A", "B"] | None = None

    @model_validator(mode="after")
    def require_distinct_shadow(self) -> "ClassifierSettings":
        if self.shadow == self.active:
            raise ValueError("shadow classifier must differ from active classifier")
        return self


class DiscoverySettings(StrictModel):
    openalex: bool = True
    semantic_scholar: bool = True
    arxiv: bool = True

    @model_validator(mode="after")
    def require_enabled_source(self) -> "DiscoverySettings":
        if not any((self.openalex, self.semantic_scholar, self.arxiv)):
            raise ValueError("at least one discovery source must be enabled")
        return self


class ResourceLimits(StrictModel):
    max_candidates: int = Field(default=500, gt=0)
    max_classified: int = Field(default=250, gt=0)
    max_downloads: int = Field(default=50, ge=0)
    max_deep_reads: int = Field(default=15, ge=0)

    @model_validator(mode="after")
    def require_monotonic_limits(self) -> "ResourceLimits":
        if self.max_classified > self.max_candidates:
            raise ValueError("max_classified cannot exceed max_candidates")
        if self.max_downloads > self.max_classified:
            raise ValueError("max_downloads cannot exceed max_classified")
        if self.max_deep_reads > self.max_downloads:
            raise ValueError("max_deep_reads cannot exceed max_downloads")
        return self


class SchedulingSettings(StrictModel):
    frequency: Literal["weekly"] = "weekly"
    day: Literal[
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ] = "sunday"


class TopicSettings(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    name: str = Field(min_length=1)
    enabled: bool = True
    lookback_days: int = Field(default=10, gt=0)
    keywords: list[str] = Field(default_factory=list)
    classifier: ClassifierSettings = Field(default_factory=ClassifierSettings)
    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    limits: ResourceLimits = Field(default_factory=ResourceLimits)
    scheduling: SchedulingSettings = Field(default_factory=SchedulingSettings)


class TopicsConfiguration(StrictModel):
    topics: list[TopicSettings] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_topic_ids(self) -> "TopicsConfiguration":
        topic_ids = [topic.id for topic in self.topics]
        if len(topic_ids) != len(set(topic_ids)):
            raise ValueError("topic ids must be unique")
        return self


class ProjectConfiguration(StrictModel):
    settings: ApplicationSettings
    topics: TopicsConfiguration


def _load_yaml_mapping(path: Path) -> Mapping[str, Any]:
    try:
        with path.open(encoding="utf-8") as config_file:
            content = yaml.safe_load(config_file)
    except FileNotFoundError as error:
        raise ConfigurationError(f"configuration file not found: {path}") from error
    except OSError as error:
        raise ConfigurationError(f"unable to read configuration file {path}: {error}") from error
    except yaml.YAMLError as error:
        raise ConfigurationError(f"invalid YAML in {path}: {error}") from error

    if not isinstance(content, Mapping):
        raise ConfigurationError(f"configuration file must contain a mapping: {path}")
    return content


def load_configuration(
    settings_path: Path = Path("config/settings.yaml"),
    topics_path: Path = Path("config/topics.yaml"),
) -> ProjectConfiguration:
    """Load and validate application and topic configuration."""
    settings_data = _load_yaml_mapping(settings_path)
    topics_data = _load_yaml_mapping(topics_path)
    return ProjectConfiguration(
        settings=ApplicationSettings(**settings_data),
        topics=TopicsConfiguration.model_validate(topics_data),
    )
