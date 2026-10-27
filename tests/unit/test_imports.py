import importlib

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "research_agent.discovery",
        "research_agent.documents",
        "research_agent.domain",
        "research_agent.graph",
        "research_agent.models",
        "research_agent.observability",
        "research_agent.screening",
        "research_agent.storage",
        "research_agent.utils",
    ],
)
def test_architecture_boundary_imports(module_name: str) -> None:
    module = importlib.import_module(module_name)
    # A leftover directory holding only __pycache__ still imports, as an empty namespace package.
    # That is how a deleted package kept passing here on one machine and failed on a fresh clone.
    assert module.__file__ is not None, f"{module_name} is not a regular package"
