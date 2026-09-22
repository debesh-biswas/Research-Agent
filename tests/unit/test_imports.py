import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "research_agent.classifiers",
        "research_agent.discovery",
        "research_agent.documents",
        "research_agent.domain",
        "research_agent.graph",
        "research_agent.models",
        "research_agent.observability",
        "research_agent.storage",
        "research_agent.utils",
    ],
)
def test_architecture_boundary_imports(module_name: str) -> None:
    assert importlib.import_module(module_name)
