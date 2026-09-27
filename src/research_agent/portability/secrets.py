"""Secret resolution behind one interface.

Locally a secret is an environment variable. On AWS the same value arrives from Parameter Store or
Secrets Manager, which both resolve a *name* to a value — so the boundary is a name mapping, and no
caller needs to know which side of it they are on. Nothing here logs or returns a value in an error.
"""

import os
from typing import Protocol

from research_agent.config import StrictModel

ENV_PREFIX = "RESEARCH_AGENT_"


class MissingSecretError(RuntimeError):
    """A required secret was not resolvable. The message names the secret, never a value."""


class SecretResolver(Protocol):
    """Resolve a logical secret name to its value."""

    @property
    def backend(self) -> str: ...

    def get(self, name: str) -> str | None: ...

    def require(self, name: str) -> str: ...


class _Resolver:
    """Shared `require`, so every backend fails the same way."""

    backend = "unset"

    def get(self, name: str) -> str | None:  # pragma: no cover - overridden
        raise NotImplementedError

    def require(self, name: str) -> str:
        value = self.get(name)
        if not value:
            raise MissingSecretError(f"{self.backend} has no value for {name!r}")
        return value


class EnvironmentSecrets(_Resolver):
    """The local default: `nim_api_key` reads `RESEARCH_AGENT_NIM_API_KEY`."""

    backend = "environment"

    def __init__(self, prefix: str = ENV_PREFIX) -> None:
        self._prefix = prefix

    def get(self, name: str) -> str | None:
        return os.environ.get(f"{self._prefix}{name.upper()}") or os.environ.get(name.upper())


class ParameterStoreSecrets(_Resolver):
    """A Parameter Store / Secrets Manager shaped resolver over an injected fetcher.

    The fetcher is what a thin `boto3` adapter would implement. Keeping it injected means this class
    is fully testable, adds no dependency, and cannot become required locally.
    """

    def __init__(
        self,
        path_prefix: str,
        fetch: "SecretFetcher",
        backend: str = "parameter_store",
    ) -> None:
        self._prefix = path_prefix.rstrip("/")
        self._fetch = fetch
        self.backend = backend

    def parameter_name(self, name: str) -> str:
        """The remote name for a logical secret: `/research-agent/prod/nim_api_key`."""
        return f"{self._prefix}/{name.strip('/')}"

    def get(self, name: str) -> str | None:
        return self._fetch(self.parameter_name(name))


class SecretFetcher(Protocol):
    """One remote lookup: a name in, a value or None out."""

    def __call__(self, parameter_name: str) -> str | None: ...


class SecretMapping(StrictModel):
    """The logical secrets this application uses, and nothing else.

    Written down so a deployment can grant least-privilege access to exactly these names.
    """

    nim_api_key: str = "nim_api_key"
    semantic_scholar_api_key: str = "semantic_scholar_api_key"
    openalex_mailto: str = "openalex_mailto"

    def names(self) -> list[str]:
        return sorted(self.model_dump().values())


def build_resolver(
    backend: str, fetch: SecretFetcher | None = None, path_prefix: str = "/research-agent"
) -> SecretResolver:
    """Resolve a profile's secret backend to an implementation.

    A remote backend needs a fetcher injected; without one this raises rather than silently falling
    back to the environment, because a silent fallback is how a deployment reads the wrong secrets.
    """
    if backend == "environment":
        return EnvironmentSecrets()
    if backend in ("parameter_store", "secrets_manager"):
        if fetch is None:
            raise MissingSecretError(f"{backend} needs a fetcher; none was provided")
        return ParameterStoreSecrets(path_prefix, fetch, backend)
    raise ValueError(f"unknown secret backend: {backend}")
