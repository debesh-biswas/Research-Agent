"""Legal, validated, failure-isolated PDF acquisition (TRD section 21).

Nothing here raises into the caller: every paper produces an outcome, so one unavailable or broken
document can never abort a run.
"""

import asyncio
import hashlib
import logging
from typing import Literal, Protocol

import httpx
from pydantic import Field

from research_agent.config import DocumentSettings, StrictModel
from research_agent.discovery.http import RateLimiter
from research_agent.documents.urls import pdf_candidates
from research_agent.domain.papers import PaperCandidate
from research_agent.storage.artifacts import ArtifactStore
from research_agent.storage.papers import PaperRepository

_LOGGER = logging.getLogger(__name__)
_PDF_SIGNATURE = b"%PDF-"
_PDF_TYPES = ("application/pdf", "application/octet-stream", "binary/octet-stream")
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_CHUNK_BYTES = 64 * 1024

DownloadStatus = Literal["stored", "cached", "unavailable", "failed"]


class DownloadOutcome(StrictModel):
    """What acquisition did with one paper, whether or not a file resulted."""

    paper_id: str = Field(min_length=1)
    status: DownloadStatus
    path: str | None = None
    byte_size: int = Field(default=0, ge=0)
    sha256: str | None = None
    url: str | None = None
    reason: str | None = None


class DocumentAcquirer(Protocol):
    """One document source, independent of transport; F12 and the graph depend on this."""

    async def acquire(
        self, paper: PaperCandidate, topic_id: str, run_id: str | None = None
    ) -> DownloadOutcome: ...

    async def acquire_many(
        self, papers: list[PaperCandidate], topic_id: str, run_id: str | None = None
    ) -> list[DownloadOutcome]: ...


class PdfDownloader:
    """Fetch open-access PDFs, validating every response before it is allowed onto disk."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        store: ArtifactStore,
        papers: PaperRepository,
        settings: DocumentSettings | None = None,
        retries: int = 2,
        concurrency: int = 4,
    ) -> None:
        self._client = client
        self._store = store
        self._papers = papers
        self._settings = settings or DocumentSettings()
        self._retries = retries
        self._limiter = RateLimiter(self._settings.requests_per_second)
        self._semaphore = asyncio.Semaphore(max(1, concurrency))

    async def acquire(
        self, paper: PaperCandidate, topic_id: str, run_id: str | None = None
    ) -> DownloadOutcome:
        """Download one paper's PDF, trying each legal candidate URL until one succeeds."""
        paper_id = paper.canonical_id or ""
        if not paper_id:
            return DownloadOutcome(
                paper_id="unknown", status="failed", reason="paper has no canonical id"
            )

        name = f"{paper_id}.pdf"
        if self._store.exists(topic_id, "papers", name):
            path = self._store.path_for(topic_id, "papers", name)
            return DownloadOutcome(paper_id=paper_id, status="cached", path=str(path))

        candidates = pdf_candidates(paper)
        if not candidates:
            return DownloadOutcome(
                paper_id=paper_id, status="unavailable", reason="no open-access PDF URL"
            )

        reason = "no attempt was made"
        for url in candidates:
            data, failure = await self._fetch(url)
            if data is not None:
                return self._store_pdf(paper_id, topic_id, run_id, url, data)
            reason = f"{url}: {failure}"
            _LOGGER.warning(
                "pdf candidate failed",
                extra={
                    "paper_id": paper_id,
                    "topic_id": topic_id,
                    "node_name": "acquire",
                    "error_type": "PDF_DOWNLOAD_ERROR",
                    "status": "candidate_failed",
                },
            )
        return DownloadOutcome(paper_id=paper_id, status="failed", reason=reason)

    async def acquire_many(
        self, papers: list[PaperCandidate], topic_id: str, run_id: str | None = None
    ) -> list[DownloadOutcome]:
        """Download a set with bounded concurrency; one failure never affects the others."""
        return list(
            await asyncio.gather(*(self._bounded(paper, topic_id, run_id) for paper in papers))
        )

    async def _bounded(
        self, paper: PaperCandidate, topic_id: str, run_id: str | None
    ) -> DownloadOutcome:
        async with self._semaphore:
            return await self.acquire(paper, topic_id, run_id)

    async def _fetch(self, url: str) -> tuple[bytes | None, str]:
        """Return the validated bytes of one URL, or None and the reason it was not usable."""
        failure = "no attempt was made"
        for attempt in range(self._retries + 1):
            await self._limiter.acquire()
            try:
                body, failure, retryable = await self._attempt(url)
            except httpx.TimeoutException as error:
                body, failure, retryable = None, f"timeout: {error}", True
            except httpx.TransportError as error:
                body, failure, retryable = None, f"transport error: {error}", True
            if body is not None:
                return body, ""
            if not retryable:
                return None, failure
            if attempt < self._retries:
                await asyncio.sleep(2**attempt)
        return None, failure

    async def _attempt(self, url: str) -> tuple[bytes | None, str, bool]:
        """One request. The body is streamed so an oversize file is abandoned, not buffered."""
        headers = {"user-agent": self._settings.user_agent, "accept": "application/pdf"}
        async with self._client.stream(
            "GET", url, headers=headers, follow_redirects=True
        ) as response:
            if response.status_code >= 400:
                return (
                    None,
                    f"HTTP {response.status_code}",
                    response.status_code in _RETRYABLE_STATUS,
                )
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type and content_type not in _PDF_TYPES:
                return None, f"unexpected content type: {content_type}", False

            chunks = bytearray()
            async for chunk in response.aiter_bytes(_CHUNK_BYTES):
                chunks.extend(chunk)
                if len(chunks) > self._settings.max_pdf_bytes:
                    return None, f"larger than {self._settings.max_pdf_bytes} bytes", False

        if not bytes(chunks).startswith(_PDF_SIGNATURE):
            # A login page served as application/pdf is the common case here.
            return None, "response is not a PDF", False
        return bytes(chunks), "", False

    def _store_pdf(
        self, paper_id: str, topic_id: str, run_id: str | None, url: str, data: bytes
    ) -> DownloadOutcome:
        digest = hashlib.sha256(data).hexdigest()
        path = self._store.write_bytes(topic_id, "papers", f"{paper_id}.pdf", data)
        self._papers.record_file(paper_id, "pdf", str(path), len(data), digest, run_id)
        return DownloadOutcome(
            paper_id=paper_id,
            status="stored",
            path=str(path),
            byte_size=len(data),
            sha256=digest,
            url=url,
        )
