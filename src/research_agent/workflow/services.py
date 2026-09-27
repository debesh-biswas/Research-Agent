"""The dependencies the graph's nodes are given.

Nodes hold no provider, endpoint or SQL knowledge: everything they use arrives here as an already
constructed service, which is what lets the tests run the whole graph against fakes.
"""

from dataclasses import dataclass

from research_agent.analysis.analyzer import PaperAnalyzer
from research_agent.classifiers.runner import ClassifierRunner
from research_agent.config import ApplicationSettings, TopicSettings
from research_agent.discovery.aggregator import DiscoveryAggregator
from research_agent.documents.downloader import DocumentAcquirer
from research_agent.documents.parser import ParsingService
from research_agent.ideation.generator import IdeationService
from research_agent.queries.planner import QueryPlanner
from research_agent.reports.service import ReportService
from research_agent.storage.papers import PaperRepository
from research_agent.storage.results import ResultRepository
from research_agent.storage.runs import RunRepository
from research_agent.storage.selections import SelectionRepository
from research_agent.synthesis.synthesizer import WeeklySynthesizer


@dataclass(frozen=True)
class WorkflowServices:
    """One run's collaborators, injected into the graph builder."""

    settings: ApplicationSettings
    topic: TopicSettings
    runs: RunRepository
    papers: PaperRepository
    results: ResultRepository
    selections: SelectionRepository
    discovery: DiscoveryAggregator
    classifiers: ClassifierRunner
    acquirer: DocumentAcquirer
    parsing: ParsingService
    analyzer: PaperAnalyzer
    synthesizer: WeeklySynthesizer
    ideation: IdeationService
    reports: ReportService
    planner: QueryPlanner | None = None
    """Optional: without it the run uses the deterministic base query alone."""
