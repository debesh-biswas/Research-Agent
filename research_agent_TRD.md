# Technical Requirements Document (TRD)
## Personal Weekly AI Research Intelligence Agent

**Version:** 1.0  
**Status:** Initial Technical Specification  
**Primary Runtime:** Python  
**Primary Orchestration:** LangGraph  
**Deployment Strategy:** Local-first, AWS-compatible  
**Cost Constraint:** Free/open-source/student-free-plan-oriented  
**Classifier Scope:** Classifier A and Classifier B only

---

# 1. Technical Objective

Build a modular weekly research-agent system that:

- Runs locally on a 24 GB Apple Silicon MacBook.
- Uses LangGraph for workflow orchestration.
- Discovers papers from OpenAlex, Semantic Scholar, and arXiv.
- Supports two hot-swappable pre-existing classifiers.
- Supports active/shadow classifier execution.
- Uses deterministic code for retrieval, normalization, deduplication, downloading, persistence, and validation.
- Uses local LLM inference for lightweight semantic tasks.
- Uses NVIDIA NIM free endpoints, when available, for expensive reasoning.
- Stores local metadata in SQLite.
- Stores papers and reports on the local filesystem.
- Can later map infrastructure components onto AWS student/free-plan services.

No custom classifier training pipeline is included.

---

# 2. High-Level Architecture

```text
                         Scheduler
                            │
                            ▼
                        LangGraph
                            │
          ┌─────────────────┼──────────────────┐
          │                 │                  │
          ▼                 ▼                  ▼
   Research Sources    Classifier Layer    Model Layer
   OpenAlex            Classifier A        Local LLM
   Semantic Scholar    Classifier B        NVIDIA NIM
   arXiv                                    fallback
          │                 │                  │
          └─────────────────┼──────────────────┘
                            ▼
                       PDF Pipeline
                       Download
                       Parse
                            │
                            ▼
                    Structured Analysis
                            │
                            ▼
                   Cross-Paper Synthesis
                            │
                            ▼
                    Weekly Markdown Report
                            │
               ┌────────────┴────────────┐
               ▼                         ▼
             SQLite                 Local Files
               │                         │
               └────────────┬────────────┘
                            ▼
                   Structured Run Logs
```

---

# 3. Recommended Repository Structure

```text
research-agent/
│
├── pyproject.toml
├── README.md
├── .env.example
├── config/
│   ├── settings.yaml
│   └── topics.yaml
│
├── src/
│   ├── main.py
│   │
│   ├── graph/
│   │   ├── builder.py
│   │   ├── state.py
│   │   ├── routing.py
│   │   └── nodes/
│   │       ├── plan_queries.py
│   │       ├── discover.py
│   │       ├── normalize.py
│   │       ├── deduplicate.py
│   │       ├── classify.py
│   │       ├── select.py
│   │       ├── acquire_pdf.py
│   │       ├── parse_pdf.py
│   │       ├── analyze.py
│   │       ├── synthesize.py
│   │       ├── ideate.py
│   │       ├── report.py
│   │       └── persist.py
│   │
│   ├── classifiers/
│   │   ├── base.py
│   │   ├── classifier_a.py
│   │   ├── classifier_b.py
│   │   └── factory.py
│   │
│   ├── models/
│   │   ├── base.py
│   │   ├── local.py
│   │   ├── nim.py
│   │   └── router.py
│   │
│   ├── discovery/
│   │   ├── base.py
│   │   ├── openalex.py
│   │   ├── semantic_scholar.py
│   │   ├── arxiv.py
│   │   └── aggregator.py
│   │
│   ├── documents/
│   │   ├── downloader.py
│   │   ├── parser.py
│   │   └── schemas.py
│   │
│   ├── storage/
│   │   ├── metadata.py
│   │   ├── filesystem.py
│   │   └── repositories/
│   │
│   ├── observability/
│   │   ├── logger.py
│   │   ├── metrics.py
│   │   └── tracing.py
│   │
│   └── utils/
│
├── data/
│   ├── research.db
│   ├── topics/
│   └── logs/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
└── scripts/
    ├── run_topic.py
    ├── run_all_topics.py
    └── compare_classifiers.py
```

---

# 4. Core Technology Choices

## Language

Python 3.11+ recommended.

Reasons:

- LangGraph ecosystem
- Academic API libraries
- MLX/Ollama integrations
- PDF tooling
- Pydantic
- SQLite
- AWS SDK compatibility

---

## Dependency Management

Recommended:

- `uv`, or
- standard `venv` + `pip`

The project should not require Docker for local development.

---

# 5. LangGraph Requirements

LangGraph is the central workflow orchestrator.

It is responsible for:

- State propagation
- Node execution
- Conditional routing
- Retry-aware branching
- Failure handling
- Persistent run state where enabled

LangGraph must **not** directly own:

- Model implementation details
- Storage implementation details
- Academic API logic
- Classifier implementation details

Those must remain behind interfaces.

---

# 6. Graph State Schema

Suggested Pydantic-style state:

```python
class ResearchState(BaseModel):
    run_id: str
    topic_id: str
    topic_name: str
    date_start: datetime
    date_end: datetime

    search_queries: list[str] = []

    raw_candidates: list[PaperCandidate] = []
    normalized_candidates: list[PaperCandidate] = []
    deduplicated_candidates: list[PaperCandidate] = []

    classification_results: list[ClassificationResult] = []
    selected_papers: list[PaperCandidate] = []

    downloaded_papers: list[DownloadedPaper] = []
    parsed_papers: list[ParsedPaper] = []
    paper_analyses: list[PaperAnalysis] = []

    trends: list[TrendFinding] = []
    gaps: list[ResearchGap] = []
    ideas: list[ResearchIdea] = []

    report_markdown: str | None = None

    warnings: list[str] = []
    errors: list[RunError] = []
```

Large binary/PDF contents should never be embedded directly in graph state.

Store file paths or object references instead.

---

# 7. LangGraph Node Flow

```text
START
  ↓
load_topic_config
  ↓
generate_queries
  ↓
discover_papers
  ↓
normalize_metadata
  ↓
deduplicate_candidates
  ↓
classify_candidates
  ↓
select_papers
  ↓
acquire_pdfs
  ↓
parse_pdfs
  ↓
analyze_papers
  ↓
synthesize_week
  ↓
detect_gaps
  ↓
generate_ideas
  ↓
generate_report
  ↓
persist_run
  ↓
END
```

---

# 8. Conditional Routing

Example conditions:

### No candidates

```text
discover_papers
    ↓
candidate_count == 0
    ↓
generate_empty_week_report
```

### Too few relevant papers

```text
classify_candidates
    ↓
selected_count < configured_minimum
    ↓
broaden_query_once
```

Only one automatic query broadening pass should occur initially to avoid loops.

### PDF unavailable

```text
download_pdf
    ↓
unavailable
    ↓
retain metadata + abstract
```

### PDF parse failure

```text
parse_pdf
    ↓
failure
    ↓
fallback to abstract-only analysis
```

### NIM unavailable

```text
NIM call
   ↓
retry
   ↓
local fallback
```

---

# 9. Topic Configuration Schema

Example YAML:

```yaml
topics:
  - id: embodied_spatial_intelligence
    name: "Embodied Spatial Intelligence"
    enabled: true

    lookback_days: 10

    classifier:
      active: "A"
      shadow: "B"

    discovery:
      openalex: true
      semantic_scholar: true
      arxiv: true

    limits:
      max_candidates: 500
      max_classified: 250
      max_downloads: 50
      max_deep_reads: 15

    scheduling:
      frequency: weekly
      day: sunday
```

---

# 10. Classifier Abstraction

Both classifiers must implement one common interface.

```python
class PaperClassifier(Protocol):

    def classify(
        self,
        paper: PaperCandidate,
        topic: TopicConfig,
    ) -> ClassificationResult:
        ...
```

Normalized result:

```python
class ClassificationResult(BaseModel):
    paper_id: str
    classifier_name: str

    relevance: Literal["high", "medium", "low"]
    relevance_score: float | None

    paper_type: Literal[
        "method",
        "dataset",
        "benchmark",
        "survey",
        "application",
        "other",
    ]

    action: Literal[
        "ignore",
        "summarize",
        "deep_read",
    ]

    confidence: float | None
    reason_short: str | None

    latency_ms: int | None
    raw_response: dict | str | None
```

---

# 11. Classifier A

Classifier A is a pre-existing lightweight Jev-style decision classifier.

Technical requirements:

- Exposed through `PaperClassifier`.
- Produces normalized structured output.
- Must not leak implementation-specific output into LangGraph.
- Must record confidence/probabilities when available.
- Must support batch processing if underlying implementation allows it.
- Must support local execution where feasible.

If the specific model/library changes later, only `classifier_a.py` should change.

---

# 12. Classifier B

Classifier B is a pre-existing Qwen-style small LLM used for structured classification.

Technical requirements:

- Runs locally where feasible.
- Prefer MLX-compatible quantized model on Apple Silicon.
- Prompt must enforce structured output.
- Output must be validated using Pydantic.
- Invalid responses should retry once with a repair instruction.

Classifier B returns exactly the same application schema as Classifier A.

---

# 13. Classifier Factory

Example:

```python
def get_classifier(name: str) -> PaperClassifier:
    match name.upper():
        case "A":
            return ClassifierA(...)
        case "B":
            return ClassifierB(...)
        case _:
            raise ValueError("Unsupported classifier")
```

LangGraph must call the factory, not instantiate implementations itself.

---

# 14. Active + Shadow Execution

Configuration:

```yaml
classifier:
  active: "A"
  shadow: "B"
```

Execution:

```text
candidate
   │
   ├── active classifier
   │      ↓
   │   controls routing
   │
   └── shadow classifier
          ↓
       logged only
```

Storage must distinguish:

```text
is_active_result = true/false
```

If shadow classification fails, the main run must continue.

---

# 15. Academic Discovery Interfaces

Define:

```python
class ResearchSource(Protocol):

    async def search(
        self,
        query: str,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> list[PaperCandidate]:
        ...
```

Adapters:

- `OpenAlexSource`
- `SemanticScholarSource`
- `ArxivSource`

---

# 16. Candidate Paper Schema

```python
class PaperCandidate(BaseModel):
    canonical_id: str | None

    title: str
    abstract: str | None

    authors: list[str]

    publication_date: date | None
    discovered_at: datetime

    source: str
    source_id: str

    doi: str | None
    arxiv_id: str | None

    url: str | None
    pdf_url: str | None

    venue: str | None
    citation_count: int | None
```

---

# 17. Search Query Generation

Input:

```text
topic name
historical topic summary
optional known keywords
```

Output:

```python
list[str]
```

The initial implementation should generate approximately:

```text
5-20 queries/topic/run
```

depending on topic breadth.

Query generation may use a local model.

---

# 18. Metadata Normalization

Normalize:

- Unicode
- Whitespace
- DOI format
- arXiv identifiers
- Dates
- URLs
- Author names where feasible

Canonical DOI form:

```text
10.xxxx/xxxxx
```

without `https://doi.org/`.

---

# 19. Deduplication Logic

Order:

```text
1. DOI exact match
2. arXiv ID exact match
3. normalized title exact match
4. fuzzy title similarity + author overlap
```

Recommended fuzzy comparison:

- RapidFuzz

Threshold should be configurable.

Possible default:

```text
title_similarity >= 95
```

with at least one overlapping author.

---

# 20. Persistent Seen-Paper Check

Before classification, compare against stored papers.

Each paper should have:

```text
first_seen_at
last_seen_at
first_analyzed_at
last_analyzed_at
```

Previously seen papers may still be retained when:

- New revision detected
- Metadata changed
- User explicitly requests re-analysis

---

# 21. PDF Acquisition

Requirements:

- Prefer open-access PDF URLs.
- Store HTTP metadata where useful.
- Validate content type.
- Enforce size limit.
- Use deterministic filename.

Example:

```text
<canonical_paper_id>.pdf
```

Failures must not abort the run.

---

# 22. PDF Parsing

Primary parser:

- Docling

Parser output should be normalized into:

```python
class ParsedPaper(BaseModel):
    paper_id: str
    source_pdf_path: str

    title: str | None
    sections: list[ParsedSection]
    tables: list[ParsedTable]
    figures: list[ParsedFigure]
    references: list[ParsedReference]

    parser_name: str
    parser_version: str | None
```

Parsed Markdown should also be saved to disk.

---

# 23. Model Provider Abstraction

Define:

```python
class ModelProvider(Protocol):

    async def generate(
        self,
        task: str,
        messages: list[dict],
        response_schema: type[BaseModel] | None = None,
    ):
        ...
```

Implementations:

- `LocalModelProvider`
- `NvidiaNIMProvider`

No LangGraph node should directly contain provider-specific API code.

---

# 24. Local Inference

Preferred Apple Silicon options:

1. MLX-LM
2. Ollama
3. llama.cpp

Local tasks:

- Search query expansion
- Classifier B
- Simple summarization
- Extraction
- Fallback analysis

Target model range:

```text
approximately 4B-14B quantized
```

Actual model should be configurable.

---

# 25. NVIDIA NIM Integration

NIM is used when free developer endpoints are available.

Primary tasks:

- Deep paper analysis
- Cross-paper comparison
- Weekly synthesis
- Trend detection
- Gap detection
- Research ideation
- Final report generation

Required configuration:

```env
NVIDIA_API_KEY=...
NVIDIA_BASE_URL=...
NVIDIA_MODEL=...
```

NIM must remain optional.

---

# 26. Model Routing

Suggested internal API:

```python
router.generate(
    capability="deep_reasoning",
    ...
)
```

Capabilities:

```text
cheap_text
classification
deep_reasoning
synthesis
ideation
report_writing
```

Initial mapping:

```text
cheap_text      → local
classification  → active classifier
deep_reasoning  → NIM
synthesis       → NIM
ideation        → NIM
report_writing  → NIM
```

Fallback:

```text
NIM unavailable → local model
```

---

# 27. Structured Paper Analysis Schema

```python
class PaperAnalysis(BaseModel):
    paper_id: str

    research_problem: str
    main_contribution: str
    method: str

    datasets: list[str]
    benchmarks: list[str]

    experimental_setup: str | None
    main_results: list[str]

    strengths: list[str]
    limitations: list[str]

    key_claims: list[Claim]
    related_work: list[str]

    topic_relevance: str

    model_provider: str
    model_name: str
```

---

# 28. Claim Provenance

Where feasible:

```python
class Claim(BaseModel):
    text: str
    source_section: str | None
    page: int | None
    evidence_excerpt: str | None
```

Exact page provenance depends on parser quality and is best-effort initially.

---

# 29. Cross-Paper Synthesis

Input:

```text
selected PaperAnalysis records
historical topic summary
```

Output:

```python
class WeeklySynthesis(BaseModel):
    major_developments: list[str]
    emerging_directions: list[str]
    methods_gaining_attention: list[str]
    new_datasets: list[str]
    new_benchmarks: list[str]
    contradictions: list[str]
    changes_from_history: list[str]
```

---

# 30. Research Gap Schema

```python
class ResearchGap(BaseModel):
    title: str
    description: str
    supporting_paper_ids: list[str]
    confidence: float | None
```

---

# 31. Research Idea Schema

```python
class ResearchIdea(BaseModel):
    title: str
    hypothesis: str
    motivation: str
    supporting_paper_ids: list[str]
    identified_gap: str
    proposed_direction: str
    evaluation_plan: str
    risks: list[str]
```

---

# 32. Report Generation

Output format:

```text
Markdown
```

File naming:

```text
YYYY-MM-DD_weekly_report.md
```

The report generator consumes structured stored objects rather than raw PDFs.

---

# 33. SQLite Schema

Minimum tables:

```text
topics
runs
papers
paper_sources
classifications
paper_files
paper_analyses
weekly_syntheses
research_gaps
research_ideas
errors
```

---

# 34. Example Database Entities

## topics

```text
id
name
enabled
lookback_days
active_classifier
shadow_classifier
created_at
updated_at
```

## runs

```text
id
topic_id
started_at
completed_at
status
papers_found
papers_selected
active_classifier
shadow_classifier
duration_seconds
```

## papers

```text
id
title
abstract
doi
arxiv_id
publication_date
first_seen_at
last_seen_at
```

## classifications

```text
id
run_id
paper_id
classifier_name
is_active
relevance
relevance_score
paper_type
action
confidence
reason_short
latency_ms
raw_response_json
```

---

# 35. File Storage Layout

```text
data/
└── topics/
    └── embodied_spatial_intelligence/
        ├── papers/
        │   └── <paper_id>.pdf
        ├── parsed/
        │   └── <paper_id>.md
        ├── analyses/
        │   └── <paper_id>.json
        ├── reports/
        │   └── 2026-09-22_weekly_report.md
        └── runs/
            └── <run_id>.json
```

---

# 36. Scheduling

Local scheduling options:

- macOS `launchd`
- cron

The scheduler invokes:

```bash
python -m src.main --run-all-enabled
```

LangGraph does not need to own weekly scheduling.

---

# 37. Logging

Use Python structured logging.

Each log event should include when available:

```text
timestamp
run_id
topic_id
node_name
paper_id
provider
model
classifier
duration_ms
status
error_type
```

JSON logs recommended.

---

# 38. Observability

Initial:

```text
local structured logs
+
run summary JSON
+
SQLite run records
```

Optional later:

```text
OpenTelemetry
→ Langfuse
```

AWS deployment:

```text
CloudWatch logs/metrics
```

---

# 39. Error Handling

Errors should be categorized:

```text
DISCOVERY_ERROR
RATE_LIMIT
NETWORK_ERROR
CLASSIFIER_ERROR
INVALID_CLASSIFIER_OUTPUT
PDF_DOWNLOAD_ERROR
PDF_PARSE_ERROR
MODEL_API_ERROR
MODEL_TIMEOUT
STORAGE_ERROR
REPORT_ERROR
```

Each error should record:

```text
run_id
paper_id if applicable
node
recoverable true/false
message
timestamp
```

---

# 40. Retry Policy

Recommended defaults:

### Academic APIs
- Maximum 3 retries
- Exponential backoff

### NIM
- Maximum 2 retries
- Then local fallback

### Classifier B malformed JSON
- One repair retry

### PDF download
- Maximum 2 retries

Do not retry deterministic validation errors indefinitely.

---

# 41. Concurrency

Use bounded concurrency for:

- Academic API calls
- PDF downloads
- Independent paper analysis

Do not send hundreds of simultaneous requests.

Configuration example:

```yaml
concurrency:
  discovery: 3
  downloads: 4
  analysis: 2
```

---

# 42. Rate Limiting

Each academic source adapter should support:

```text
request pacing
429 handling
Retry-After honoring
```

Rate limits must not be hardcoded globally because providers differ.

---

# 43. Caching

Cache:

- Search results within one run
- Metadata for known papers
- Parsed PDFs
- Completed deep analyses

Avoid repeating expensive model calls for unchanged papers.

---

# 44. Historical Comparison

Before weekly synthesis, query previous:

```text
N weekly_syntheses
```

Suggested default:

```text
4 previous weeks
```

Use this context to identify changes.

---

# 45. Security

Local:

```text
.env
```

must contain secrets.

Never commit:

```text
NVIDIA_API_KEY
AWS credentials
other provider credentials
```

`.gitignore` must include:

```text
.env
data/
*.db
```

unless sanitized sample data is intentionally committed.

---

# 46. Testing Requirements

## Unit Tests

Required for:

- DOI normalization
- arXiv ID normalization
- Deduplication
- Classifier factory
- Classifier output validation
- Storage repositories
- Report filename generation

## Integration Tests

Required for:

- OpenAlex adapter
- Semantic Scholar adapter
- arXiv adapter
- End-to-end local mock run
- Classifier A switch
- Classifier B switch
- Shadow mode

## Fixtures

Maintain static test papers/metadata to avoid requiring live APIs for every test.

---

# 47. Classifier Comparison Script

Provide:

```bash
python scripts/compare_classifiers.py
```

Purpose:

- Run A and B over the same stored candidate set.
- Produce comparison metrics.

Report:

```text
agreement rate
disagreement count
average latency
confidence distribution
action distribution
relevance distribution
```

This script is for evaluation only and does not train any model.

---

# 48. Local Development Environment

Target machine:

```text
Apple Silicon Mac
24 GB unified memory
```

Recommended:

```text
Python
uv
MLX-LM or Ollama
SQLite
Docling
LangGraph
```

No Kubernetes required.

Docker is optional.

---

# 49. Docker Requirement

Docker is **not required** for local MVP execution.

Optional later uses:

- Reproducible API container
- AWS deployment packaging
- Supporting services

Do not containerize MLX inference unless there is a clear benefit; native macOS execution is preferred.

---

# 50. AWS Mapping

The application architecture must allow:

| Local Component | AWS Mapping |
|---|---|
| cron / launchd | EventBridge Scheduler |
| local filesystem | S3 |
| SQLite metadata | DynamoDB where appropriate |
| local JSON logs | CloudWatch |
| local API | API Gateway + Lambda |
| environment variables | Parameter Store / Secrets Manager where free-plan usage permits |
| Python worker | Lambda for short tasks or lightweight EC2/other free-plan-compatible worker for long tasks |

---

# 51. AWS Execution Strategy

Do not assume the entire LangGraph workflow belongs inside one Lambda invocation.

Preferred pattern:

```text
EventBridge
   ↓
start research worker
   ↓
LangGraph
   ↓
academic APIs + NIM
   ↓
S3/DynamoDB
   ↓
CloudWatch
```

Lambda can handle:

- API endpoints
- Topic CRUD
- Lightweight trigger logic
- Small metadata operations

Long-running PDF/research work should use a suitable Python worker.

---

# 52. AWS Services Allowed by Default

Preferred:

- S3
- EventBridge Scheduler
- DynamoDB
- CloudWatch
- IAM
- Lambda
- API Gateway

Avoid unless explicitly justified:

- EKS
- NAT Gateway
- SageMaker GPU endpoints
- OpenSearch
- Paid GPU EC2
- Always-on load balancers

---

# 53. Migration Constraint

No LangGraph node should contain direct local path assumptions.

Use interfaces such as:

```python
storage.save_pdf(...)
storage.save_report(...)
storage.get_paper(...)
```

Local implementation:

```text
filesystem
```

AWS implementation:

```text
S3
```

Likewise:

```python
metadata_repo.save(...)
```

Local:

```text
SQLite
```

AWS:

```text
DynamoDB adapter
```

---

# 54. Configuration Management

Environment-specific settings:

```text
config/local.yaml
config/aws.yaml
```

Example:

```yaml
storage_backend: local
metadata_backend: sqlite
scheduler_backend: launchd
strong_model_provider: nvidia_nim
```

AWS:

```yaml
storage_backend: s3
metadata_backend: dynamodb
scheduler_backend: eventbridge
strong_model_provider: nvidia_nim
```

---

# 55. CLI Requirements

Minimum commands:

```bash
research-agent topic add
research-agent topic list
research-agent run <topic_id>
research-agent run-all
research-agent classifier set A
research-agent classifier set B
research-agent compare-classifiers <topic_id>
research-agent report latest <topic_id>
```

CLI may initially be implemented with Typer.

---

# 56. Definition of Done

The system is technically complete for v1 when:

1. LangGraph executes the complete research workflow.
2. OpenAlex, Semantic Scholar, and arXiv adapters work.
3. Metadata normalization works.
4. Deduplication works.
5. Classifier A is integrated through the common interface.
6. Classifier B is integrated through the same interface.
7. Active classifier switching requires configuration only.
8. Shadow mode works.
9. PDFs can be downloaded and stored.
10. Docling parses downloaded PDFs.
11. Selected papers are analyzed.
12. Cross-paper synthesis is generated.
13. Research gaps and ideas are generated.
14. Markdown weekly reports are produced.
15. SQLite persists metadata.
16. Local filesystem persists artifacts.
17. Structured logs exist for each run.
18. The system works without paid infrastructure.
19. Storage/scheduler/provider interfaces are sufficiently abstracted for AWS migration.
20. No custom-model training code exists in the project.
