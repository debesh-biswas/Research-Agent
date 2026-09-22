# Product Requirements Document (PRD)
## Personal Weekly AI Research Intelligence Agent

**Version:** 1.0  
**Status:** Initial Build Specification  
**Project Type:** Personal / Student Project  
**Primary Goal:** Build a zero- or near-zero-cost AI research agent that automatically discovers, filters, analyzes, organizes, and summarizes the latest research for a configured topic on a weekly basis.

---

## 1. Product Summary

The product is a personal AI research intelligence system that runs once per configured topic per week.

For each topic, the system will:

1. Discover recent research papers from academic sources.
2. Expand the topic into multiple search queries.
3. Deduplicate candidate papers.
4. Classify and rank papers using one of two hot-swappable classifiers.
5. Download legally accessible paper PDFs.
6. Parse papers into structured text.
7. Use stronger LLM inference to deeply analyze selected papers.
8. Compare findings across the week's papers.
9. Identify notable advances, emerging directions, disagreements, limitations, and research gaps.
10. Generate research ideas based on the evidence collected.
11. Produce a structured weekly Markdown report.
12. Store papers, metadata, analyses, reports, and execution history for future retrieval.
13. Preserve historical topic context so future weekly runs focus on what changed rather than restarting from scratch.

The project should be usable locally on a 24 GB Apple Silicon MacBook and later deployable to AWS using student/free-plan-friendly services without fundamentally rewriting the application.

---

## 2. Product Vision

The system should behave less like a generic "paper summarizer" and more like a persistent research intelligence assistant.

Over time, each topic should accumulate:

- Papers
- Paper metadata
- Structured paper analyses
- Authors and institutions
- Methods
- Benchmarks
- Datasets
- Research directions
- Open problems
- Weekly trend history
- Research ideas
- Reports
- Evidence provenance

The user should be able to inspect not only "what was published this week," but also:

- What changed relative to previous weeks?
- Which research directions are accelerating?
- Which methods are appearing repeatedly?
- Which papers contradict one another?
- Which benchmarks or datasets are becoming important?
- Which open questions remain unresolved?
- Which papers deserve immediate reading?
- What research ideas follow from current gaps?

---

## 3. Target User

Primary user:

- One technically proficient student/researcher.
- Runs the application for personal research.
- Configures one or more topics.
- Wants automated weekly research intelligence.
- Wants to compare multiple classification approaches.
- Wants the project to demonstrate practical skills in:
  - Agentic AI
  - LangGraph
  - Local LLM inference
  - API-based LLM inference
  - Research retrieval
  - PDF/document processing
  - Model routing
  - Observability
  - AWS serverless/cloud services

The initial system is **single-user** and does not require multi-tenant functionality.

---

## 4. Core Product Principles

### 4.1 Evidence First
Every important finding should be traceable to source papers or source metadata.

### 4.2 Local-First
The system should operate locally without requiring paid infrastructure.

### 4.3 Free-Tier Friendly
External services should be free, open source, or usable under free/student allowances whenever possible.

### 4.4 Modular Model Usage
The system must not be tightly coupled to a specific classifier or LLM provider.

### 4.5 Deterministic Where Possible
Tasks such as deduplication, file storage, scheduling, date filtering, schema validation, and identifier matching should use deterministic code rather than LLMs.

### 4.6 Agentic Where Useful
LLMs should be used for tasks requiring semantic judgment, synthesis, comparison, interpretation, and ideation.

### 4.7 Historical Continuity
Weekly runs should build on previous runs.

### 4.8 Observable by Design
The user should be able to inspect what happened during every research run.

---

# 5. Scope

## 5.1 In Scope

### Topic Management
The user can:

- Add a research topic.
- Enable or disable a topic.
- Set a weekly run schedule.
- Configure lookback duration.
- Select which classifier controls paper triage.
- Enable optional shadow classification for comparison.

### Academic Discovery
The system searches:

- OpenAlex
- Semantic Scholar
- arXiv

Optional future-compatible adapters may be added for other sources, but they are not required in the initial implementation.

### Search Expansion
The system generates multiple search formulations from a topic, including:

- Synonyms
- Closely related concepts
- Model names
- Method names
- Application areas
- Dataset/benchmark terms where applicable

### Candidate Paper Processing
The system:

- Normalizes metadata.
- Deduplicates results.
- Tracks identifiers.
- Checks whether a paper has previously been seen.
- Calculates basic recency and source metadata.

### Dual Classifier Support
The system supports two pre-existing classifier implementations:

- **Classifier A:** lightweight Jev-style / small decision-classifier approach.
- **Classifier B:** Qwen-style small LLM used as a structured classifier.

The system must allow hot switching between A and B without changing LangGraph workflow logic.

### Shadow Classification
Optional mode:

- One classifier is active.
- The second classifier also runs.
- Only the active classifier controls routing.
- Both outputs are logged for comparison.

### PDF Acquisition
The system should:

- Download open-access PDFs where legally accessible.
- Store metadata and source links when PDF download is unavailable.
- Avoid unauthorized paywall bypassing.

### PDF Parsing
The system should convert PDFs to structured text using an open-source parser such as Docling.

### Paper Analysis
For selected papers, the system generates structured analyses containing:

- Research problem
- Main contribution
- Method
- Datasets
- Benchmarks
- Experimental setup
- Main results
- Strengths
- Limitations
- Important claims
- Related work
- Relevance to the configured topic

### Cross-Paper Synthesis
The system should identify:

- Common themes
- Emerging methods
- Trends
- Contradictions
- Repeated limitations
- New datasets
- New benchmarks
- New evaluation methods
- Potential research gaps

### Research Ideation
The system should generate evidence-backed research ideas containing:

- Problem
- Motivation
- Supporting papers
- Research gap
- Proposed direction
- Potential evaluation method
- Risks or uncertainties

### Weekly Report
The system outputs one Markdown report per topic per run.

### Persistence
The system stores:

- Topic definitions
- Search queries
- Candidate papers
- Classifier outputs
- Selected papers
- Parsed paper text
- Paper analyses
- Weekly syntheses
- Research ideas
- Reports
- Run metadata
- Errors
- Timing information

### Observability
The system records:

- Which nodes executed
- Which model/provider was used
- Search sources
- Paper counts
- Classifier outcomes
- Failures
- Retries
- Duration
- Estimated token usage where available
- API/provider errors

### AWS Deployment Compatibility
The local design must support later replacement of:

- Local scheduler → EventBridge Scheduler
- Local files → S3
- Local run metadata/logging → DynamoDB and/or CloudWatch
- Local API → API Gateway + Lambda where appropriate

The core LangGraph workflow should remain reusable.

---

## 5.2 Explicitly Out of Scope

The following are **not** part of this specification:

- Training a new custom classifier
- Fine-tuning any classifier
- Building a custom foundation model
- Paid GPU infrastructure
- Kubernetes / EKS
- Multi-tenant SaaS architecture
- Enterprise identity management
- Billing/subscriptions
- Mobile application
- Fully autonomous publication submission
- Automated citation manipulation
- Unauthorized paywall bypassing
- Large-scale web crawling
- Production-scale multi-region deployment

---

# 6. User Flow

## 6.1 Topic Setup

User creates a topic, for example:

> Embodied Spatial Intelligence

Configuration:

```yaml
topic_name: "Embodied Spatial Intelligence"
enabled: true
lookback_days: 10
schedule: "weekly"
classifier_active: "A"
classifier_shadow: "B"
deep_read_limit: 15
```

---

## 6.2 Weekly Run

The end-to-end product flow is:

```text
User Topic
   ↓
Weekly Trigger
   ↓
Generate Search Queries
   ↓
Search OpenAlex + Semantic Scholar + arXiv
   ↓
Normalize Metadata
   ↓
Deduplicate
   ↓
Remove Already-Known Papers Where Appropriate
   ↓
Classifier A/B
   ↓
Rank + Select Papers
   ↓
Download Accessible PDFs
   ↓
Parse PDFs
   ↓
Deep Paper Analysis
   ↓
Cross-Paper Synthesis
   ↓
Trend / Gap Detection
   ↓
Research Ideation
   ↓
Generate Weekly Markdown Report
   ↓
Store Artifacts + Metadata + Logs
```

---

# 7. Classifier Product Requirements

## 7.1 Classifier A

Classifier A represents the lightweight Jev-style decision-classifier path.

Required outputs:

```json
{
  "relevance": "high | medium | low",
  "relevance_score": 0.0,
  "paper_type": "method | dataset | benchmark | survey | application | other",
  "action": "ignore | summarize | deep_read",
  "confidence": 0.0,
  "reason_short": "..."
}
```

Classifier A should prioritize:

- Low latency
- Small compute footprint
- Structured decisions
- Confidence output where supported

---

## 7.2 Classifier B

Classifier B represents the Qwen-style small LLM classifier path.

It must return the same normalized application schema as Classifier A.

Classifier B should prioritize:

- Better semantic judgment
- Flexible classification
- Context-sensitive relevance decisions
- Structured JSON output

---

## 7.3 Hot Switching

The user must be able to change:

```text
CLASSIFIER_ACTIVE=A
```

to:

```text
CLASSIFIER_ACTIVE=B
```

without changing:

- LangGraph topology
- Storage schema
- Report generation logic
- Search logic
- Analysis logic

---

## 7.4 Shadow Mode

Example:

```text
ACTIVE=A
SHADOW=B
```

Behavior:

- A controls paper routing.
- B runs on the same candidate.
- B's result is logged.
- B cannot affect the run.

The reverse must also be supported.

---

# 8. Research Discovery Requirements

The search system should:

- Use multiple queries per topic.
- Search each configured source.
- Merge results.
- Normalize identifiers.
- Prefer DOI and arXiv ID where available.
- Store source-specific identifiers.
- Retain discovery timestamps.

Each candidate paper should include at minimum:

```text
title
abstract
authors
publication_date
first_seen_at
source
source_id
doi
arxiv_id
url
pdf_url_if_known
citation_count_if_available
venue_if_available
```

---

# 9. Deduplication Requirements

Duplicates should be identified by priority:

1. DOI exact match
2. arXiv ID exact match
3. Canonical title match
4. High title similarity + overlapping authors

The system should avoid analyzing the same paper multiple times simply because it appears in multiple databases.

---

# 10. Weekly Lookback Behavior

Default lookback:

```text
10 days
```

despite weekly execution.

Reason:

- Indexing delays
- Source ingestion delays
- API update timing differences

The system must deduplicate against previously processed papers.

---

# 11. Paper Selection Requirements

The system should support configurable limits:

```yaml
max_candidates: 500
max_classified: 250
max_downloads: 50
max_deep_reads: 15
```

Limits are configurable to keep local compute and free API usage under control.

---

# 12. Paper Analysis Requirements

Every deeply analyzed paper receives a standard paper card.

```markdown
# Paper Card

## Metadata
- Title
- Authors
- Institution(s)
- Date
- Venue
- DOI
- arXiv ID
- Source URL

## Research Problem

## Main Contribution

## Method

## Dataset(s)

## Benchmark(s)

## Experimental Setup

## Main Results

## Comparison to Prior Work

## Strengths

## Limitations

## Key Claims

## Relevance to Topic

## Important Figures/Tables

## Related Papers

## Code / Project Links
```

---

# 13. Weekly Report Requirements

Each report should include:

```markdown
# Weekly Research Intelligence Report

## Topic
## Reporting Period

## Executive Summary

## Most Important Developments

## Important New Papers

## Emerging Research Directions

## Methods Gaining Attention

## New Datasets / Benchmarks

## Contradictory or Competing Findings

## Changes From Previous Weeks

## Open Research Problems

## Research Gaps

## Potential Research Ideas

## Recommended Reading Order
### Essential
### Useful
### Peripheral

## Sources
```

---

# 14. Historical Context Requirements

The system should retain historical topic information so later runs can answer:

- Was this method previously seen?
- Is this dataset new?
- Is this benchmark increasing in usage?
- Did this week's papers cite older important papers not yet in the local library?
- Is a research direction appearing more frequently?

The initial version does not require a dedicated graph database.

---

# 15. Storage Requirements

Local-first storage:

### SQLite
Stores structured metadata.

### Local filesystem
Stores:

- PDFs
- Parsed Markdown/text
- Weekly reports
- JSON analysis artifacts

Suggested structure:

```text
data/
├── research.db
├── topics/
│   └── <topic_slug>/
│       ├── papers/
│       ├── parsed/
│       ├── analyses/
│       ├── reports/
│       └── runs/
└── logs/
```

---

# 16. Inference Requirements

## Local Inference

Local inference should support Apple Silicon through:

- MLX-LM, or
- Ollama / llama.cpp where appropriate

Use local models for:

- Query expansion
- Classification
- Simple extraction
- Basic summarization

## Stronger Inference

Use NVIDIA NIM free developer endpoints where available for:

- Deep paper analysis
- Cross-paper synthesis
- Trend detection
- Gap analysis
- Research ideation
- Final report generation

The application must not assume that free NIM access is permanently available.

Provider access must therefore be abstracted.

---

# 17. Model Fallback Behavior

Example:

```text
Primary strong model: NVIDIA NIM
        ↓ failure
Retry
        ↓ failure
Fallback to configured local model
```

The system should complete a degraded report rather than fail the entire weekly run when possible.

---

# 18. Observability Requirements

Each weekly run should generate a run record containing:

```json
{
  "run_id": "...",
  "topic_id": "...",
  "started_at": "...",
  "completed_at": "...",
  "papers_found": 0,
  "papers_deduplicated": 0,
  "papers_classified": 0,
  "papers_selected": 0,
  "pdfs_downloaded": 0,
  "pdf_parse_failures": 0,
  "deep_reads": 0,
  "active_classifier": "A",
  "shadow_classifier": "B",
  "models_used": [],
  "errors": [],
  "duration_seconds": 0
}
```

The system should initially support simple structured local logs.

Optional later integration:

- OpenTelemetry
- Langfuse
- CloudWatch after AWS deployment

---

# 19. AWS Deployment Product Requirements

AWS deployment is intended for portfolio demonstration while remaining student/free-plan conscious.

Preferred services:

- EventBridge Scheduler
- S3
- DynamoDB where justified
- CloudWatch
- IAM
- API Gateway
- Lambda for lightweight API/backend tasks

The main research execution may remain on a normal Python worker if Lambda runtime limits make the complete workflow unsuitable.

Avoid by default:

- EKS
- GPU EC2
- SageMaker endpoints
- NAT Gateway
- OpenSearch
- Expensive always-on services

---

# 20. Non-Functional Requirements

## Cost
Target recurring cost:

```text
$0 or as close to $0 as realistically possible.
```

## Reliability
A failure in one source or one paper should not terminate the entire weekly run.

## Reproducibility
Each report should record:

- Run date
- Topic configuration
- Active classifier
- Model/provider used
- Search sources

## Portability
Core workflow should run:

- Locally on macOS
- Later on an AWS-hosted Python environment

## Modularity
Classifier, storage, model provider, and scheduler must be replaceable through configuration/interfaces.

## Security
API keys must:

- Never be hardcoded.
- Be stored in environment variables locally.
- Use AWS-native secret/config handling after deployment.

---

# 21. Success Metrics

The initial project is successful when:

1. A topic can be configured once and processed automatically.
2. The system discovers recent papers from all three core academic sources.
3. Duplicate papers are removed.
4. Either Classifier A or B can be selected without code changes to the workflow.
5. Shadow mode records both classifier decisions.
6. Selected PDFs are downloaded where legally available.
7. Papers are parsed and analyzed.
8. A coherent weekly research report is generated.
9. Reports contain links/provenance back to source papers.
10. Previous weekly state is retained.
11. Runs are logged sufficiently to diagnose failures.
12. The same core workflow can later be deployed onto AWS infrastructure.

---

# 22. Acceptance Criteria

A complete MVP run for one topic must:

- Execute from start to finish.
- Search all configured academic sources.
- Return at least one normalized candidate set.
- Deduplicate candidate papers.
- Execute the configured active classifier.
- Optionally execute the shadow classifier.
- Persist all classifier outputs.
- Select papers according to configured thresholds.
- Download available PDFs.
- Parse successfully downloaded PDFs.
- Generate at least one paper analysis.
- Generate a weekly synthesis.
- Generate research directions/gaps.
- Generate research ideas.
- Save a Markdown report.
- Save run metadata.
- Complete without any paid infrastructure dependency.

---

# 23. Future-Compatible but Not Required

The architecture should leave room for:

- Web dashboard
- Full-text semantic search
- Citation graph visualization
- Author/lab tracking
- Email notifications
- GitHub repository linking
- Paper revision detection
- Langfuse dashboards
- Multi-topic comparative reports
- Additional academic sources

These are not required for the initial build.
