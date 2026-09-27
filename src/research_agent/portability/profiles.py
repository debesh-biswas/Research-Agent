"""The local/AWS configuration profile.

A profile names a backend per boundary. The point is not to configure AWS from here but to make the
substitution explicit and validated, so an unsupported or expensive combination fails at start-up
rather than in a deployment.
"""

from typing import Literal

from pydantic import Field, model_validator

from research_agent.config import StrictModel

Target = Literal["local", "aws"]
ArtifactBackend = Literal["filesystem", "s3"]
MetadataBackend = Literal["sqlite", "dynamodb"]
SchedulerBackend = Literal["launchd", "cron", "eventbridge"]
LogBackend = Literal["stderr", "cloudwatch"]
SecretBackend = Literal["environment", "parameter_store", "secrets_manager"]
WorkerKind = Literal["local_process", "lambda", "ec2_free_tier"]

_LOCAL_ONLY: dict[str, tuple[str, ...]] = {
    "artifacts": ("filesystem",),
    "metadata": ("sqlite",),
    "scheduler": ("launchd", "cron"),
    "logs": ("stderr",),
    "secrets": ("environment",),
    "worker": ("local_process",),
}

# PRD section 6 and the roadmap's cross-feature rules forbid these outright: they are the expensive
# defaults a "just make it cloud-native" reflex reaches for.
FORBIDDEN_SERVICES: frozenset[str] = frozenset(
    {
        "eks",
        "kubernetes",
        "nat_gateway",
        "opensearch",
        "elasticsearch",
        "sagemaker",
        "fargate",
        "rds",
        "aurora",
        "msk",
        "gpu_endpoint",
    }
)


class DeploymentProfile(StrictModel):
    """Which backend serves each replaceable boundary, and the guardrails on that choice."""

    target: Target = "local"
    artifacts: ArtifactBackend = "filesystem"
    metadata: MetadataBackend = "sqlite"
    scheduler: SchedulerBackend = "launchd"
    logs: LogBackend = "stderr"
    secrets: SecretBackend = "environment"
    worker: WorkerKind = "local_process"
    free_plan_only: bool = True
    services: list[str] = Field(default_factory=list)
    """Extra AWS services a deployment intends to use, checked against the forbidden list."""

    @model_validator(mode="after")
    def require_a_coherent_target(self) -> "DeploymentProfile":
        """A local target uses local backends; an AWS target must not silently keep them."""
        chosen = {
            "artifacts": self.artifacts,
            "metadata": self.metadata,
            "scheduler": self.scheduler,
            "logs": self.logs,
            "secrets": self.secrets,
            "worker": self.worker,
        }
        if self.target == "local":
            wrong = {
                name: value for name, value in chosen.items() if value not in _LOCAL_ONLY[name]
            }
            if wrong:
                raise ValueError(f"a local profile cannot use remote backends: {wrong}")
            return self

        remote = {name: value for name, value in chosen.items() if value not in _LOCAL_ONLY[name]}
        if not remote:
            raise ValueError("an aws profile must replace at least one backend")
        if self.scheduler in ("launchd", "cron"):
            raise ValueError("an aws profile schedules with eventbridge")
        return self

    @model_validator(mode="after")
    def reject_expensive_services(self) -> "DeploymentProfile":
        """Fail early on the services the PRD rules out, rather than in a billing alert."""
        named = {service.strip().lower().replace("-", "_") for service in self.services}
        forbidden = sorted(named & FORBIDDEN_SERVICES)
        if forbidden and self.free_plan_only:
            raise ValueError(
                "these services are not permitted under the project's cost rules: "
                + ", ".join(forbidden)
            )
        if self.worker == "lambda" and self.target == "aws":
            # TRD section 51 is explicit: a weekly research run is long, and Lambda's ceiling makes
            # it the wrong host for the whole graph. Lambda stays for API and CRUD work.
            raise ValueError(
                "the complete workflow does not run in one Lambda invocation; "
                "use ec2_free_tier for the worker and lambda for API tasks"
            )
        return self


LOCAL_PROFILE = DeploymentProfile()
AWS_PROFILE = DeploymentProfile(
    target="aws",
    artifacts="s3",
    metadata="dynamodb",
    scheduler="eventbridge",
    logs="cloudwatch",
    secrets="parameter_store",
    worker="ec2_free_tier",
)
