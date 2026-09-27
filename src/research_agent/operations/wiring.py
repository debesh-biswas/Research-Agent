"""Construct one run's services.

This is the only place that knows how every service is built, which is what keeps the graph's nodes
and the CLI free of provider and storage detail.
"""

import sqlite3
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx

from research_agent.analysis.analyzer import PaperAnalyzer
from research_agent.classifiers.factory import build_classifier
from research_agent.classifiers.runner import ClassifierRunner
from research_agent.config import ApplicationSettings, TopicSettings
from research_agent.discovery.aggregator import DiscoveryAggregator, build_sources
from research_agent.documents.docling_parser import DoclingParser
from research_agent.documents.downloader import PdfDownloader
from research_agent.documents.parser import ParsingService
from research_agent.ideation.generator import IdeationService
from research_agent.models.router import build_router
from research_agent.queries.planner import QueryPlanner
from research_agent.reports.service import ReportService
from research_agent.storage.artifacts import LocalArtifactStore
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from research_agent.storage.selections import SqliteSelectionRepository
from research_agent.synthesis.synthesizer import WeeklySynthesizer
from research_agent.workflow.services import WorkflowServices

ClientFactory = Callable[[float], httpx.AsyncClient]


def default_client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True)


def build_services(
    client: httpx.AsyncClient,
    connection: sqlite3.Connection,
    application: ApplicationSettings,
    topic: TopicSettings,
    parser: object | None = None,
    search_client: httpx.AsyncClient | None = None,
    document_client: httpx.AsyncClient | None = None,
) -> WorkflowServices:
    """Wire every stage for one topic; `parser` exists so a test never has to load Docling.

    Each kind of work gets its own client, because their timeouts differ by an order of magnitude: a
    search that has not answered in 20s is stalled, while a deep read legitimately takes minutes.
    A test may pass one client for all three.
    """
    searching = search_client or client
    downloading = document_client or client
    store = LocalArtifactStore(application.data_directory)
    papers = SqlitePaperRepository(connection)
    results = SqliteResultRepository(connection)
    runs = SqliteRunRepository(connection)
    router = build_router(client, application)
    return WorkflowServices(
        settings=application,
        topic=topic,
        runs=runs,
        papers=papers,
        results=results,
        selections=SqliteSelectionRepository(connection),
        discovery=DiscoveryAggregator(
            build_sources(searching, application, topic.discovery),
            concurrency=application.concurrency.discovery,
            settings=application,
        ),
        classifiers=ClassifierRunner(
            build_classifier(topic.classifier.active, client, application),
            None
            if topic.classifier.shadow is None
            else build_classifier(topic.classifier.shadow, client, application),
        ),
        acquirer=PdfDownloader(
            downloading,
            store,
            papers,
            application.documents,
            retries=application.retries.pdf_download,
            concurrency=application.concurrency.downloads,
        ),
        parsing=ParsingService(parser or DoclingParser(), store, papers),  # type: ignore[arg-type]
        analyzer=PaperAnalyzer(
            router,
            results,
            papers,
            store,
            application.analysis,
            concurrency=application.concurrency.analysis,
        ),
        synthesizer=WeeklySynthesizer(router, results, application.synthesis),
        ideation=IdeationService(router, results, application.ideation),
        reports=ReportService(store, results, papers, runs, router, application.reports),
        store=store,
        planner=QueryPlanner(router, application.queries),
    )


def _search_timeout(application: ApplicationSettings) -> float:
    """The slowest source's own timeout; each adapter is paced separately but shares the client."""
    sources = application.sources
    return max(
        sources.openalex.timeout_seconds,
        sources.semantic_scholar.timeout_seconds,
        sources.arxiv.timeout_seconds,
    )


@asynccontextmanager
async def services_for(
    connection: sqlite3.Connection,
    application: ApplicationSettings,
    topic: TopicSettings,
    client_factory: ClientFactory = default_client,
    parser: object | None = None,
) -> AsyncIterator[WorkflowServices]:
    """Open one client per timeout class for the run, closing all of them however the run ends."""
    async with (
        client_factory(_search_timeout(application)) as searching,
        client_factory(application.documents.timeout_seconds) as downloading,
        client_factory(application.models.nim.timeout_seconds) as inferring,
    ):
        yield build_services(
            inferring,
            connection,
            application,
            topic,
            parser,
            search_client=searching,
            document_client=downloading,
        )
