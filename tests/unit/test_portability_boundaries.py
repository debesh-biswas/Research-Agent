"""Static guards on the boundaries that make the AWS substitutions possible.

These read the source rather than run it: the claim is about what the code is allowed to know, which
no runtime test can establish.
"""

import ast
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "research_agent"

# A workflow node may name a service or a repository, never a backend. `pathlib` is permitted
# nowhere in the graph: a node that builds a path has already chosen the filesystem.
_FORBIDDEN_IN_WORKFLOW = (
    "sqlite3",
    "pathlib",
    "os.path",
    "open(",
    "boto3",
    "LocalArtifactStore",
    "SqlitePaperRepository",
    "SqliteResultRepository",
    "SqliteRunRepository",
    "SqliteTopicRepository",
    "SqliteSelectionRepository",
    "DoclingParser",
    "PdfDownloader",
    "NvidiaNIMProvider",
    "LocalModelProvider",
)

_WORKFLOW_FILES = sorted((SOURCE_ROOT / "workflow").glob("*.py"))
_DOMAIN_FILES = sorted((SOURCE_ROOT / "domain").glob("*.py"))


def test_the_workflow_package_has_files_to_check() -> None:
    assert len(_WORKFLOW_FILES) >= 4, "the guard is only meaningful if it reads the real package"


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=lambda path: path.name)
def test_no_workflow_module_names_a_backend(path: Path) -> None:
    source = path.read_text(encoding="utf-8")

    found = [term for term in _FORBIDDEN_IN_WORKFLOW if term in source]

    assert not found, f"{path.name} names a backend directly: {found}"


@pytest.mark.parametrize("path", _DOMAIN_FILES, ids=lambda path: path.name)
def test_no_domain_model_names_a_provider_or_a_backend(path: Path) -> None:
    source = path.read_text(encoding="utf-8").lower()

    for term in ("boto3", "sqlite3", "openalex.org", "arxiv.org", "nvidia", "s3://"):
        assert term not in source, f"{path.name} leaks {term} into the domain"


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=lambda path: path.name)
def test_workflow_modules_import_only_interfaces_and_domain_types(path: Path) -> None:
    """A node imports services, domain models and settings, never a provider or storage module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    banned = {
        module
        for module in imported
        if module.startswith("research_agent.storage.")
        and not module.endswith(("artifacts", "papers", "results", "runs", "selections"))
    }
    assert not banned, f"{path.name} imports {banned}"
    assert not any(module.startswith("research_agent.documents.docling") for module in imported)
    assert not any(module.startswith("research_agent.models.chat") for module in imported)


def test_the_artifact_store_protocol_is_the_only_storage_contract_the_graph_uses() -> None:
    services = (SOURCE_ROOT / "workflow" / "services.py").read_text(encoding="utf-8")

    assert "ArtifactStore" in services, "the graph depends on the Protocol"
    assert "LocalArtifactStore" not in services, "not on its filesystem implementation"


def test_the_portability_package_adds_no_cloud_dependency() -> None:
    for path in sorted((SOURCE_ROOT / "portability").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "import boto3" not in source
        assert "botocore" not in source


def test_the_project_declares_no_aws_dependency() -> None:
    pyproject = (SOURCE_ROOT.parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    dependencies = pyproject.split("dependencies = [", 1)[1].split("]", 1)[0].lower()

    for term in ("boto3", "botocore", "aws"):
        assert term not in dependencies, "AWS support must never be required locally"
