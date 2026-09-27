# AWS Portability

The Research Agent runs locally and stays that way by default. This document records how each local
boundary maps to an AWS service, what the conformance tests prove about those boundaries, and which
services are deliberately out of bounds on cost grounds.

Nothing here creates cloud resources. There is no `boto3` dependency, and a test asserts there never
becomes one: AWS support must never be required to run locally.

## Boundary map

| Boundary | Local (default) | AWS | Proven by |
| --- | --- | --- | --- |
| Artifacts | `LocalArtifactStore` (filesystem) | S3 | `ObjectStore` conformance suite drives the real `ArtifactStore` Protocol with flat keys |
| Metadata | SQLite repositories | DynamoDB-style document table | `DocumentTable` round-trips `PaperCandidate` and `PaperAnalysis` through the same schemas |
| Scheduling | launchd / cron | EventBridge Scheduler | `EventBridgeScheduler` renders a deterministic schedule for the same `research-agent run` command |
| Logs | JSON lines on stderr | CloudWatch | The formatter emits one JSON object per line with a timezone-aware timestamp; CloudWatch ingests that as-is |
| Secrets | environment / `.env` | Parameter Store or Secrets Manager | `ParameterStoreSecrets` maps the same logical names to `/research-agent/<env>/<name>` through an injected fetcher |
| Worker | local process | EC2 free tier (or another long-running host) | The profile schema refuses `worker="lambda"` for an AWS target |

A `DeploymentProfile` names one backend per boundary and validates the combination: a local profile
cannot quietly point at S3, an AWS profile cannot quietly keep cron, and an AWS profile must actually
replace something.

```python
from research_agent.portability.profiles import AWS_PROFILE, LOCAL_PROFILE
```

## Execution design

TRD section 51 is explicit that the whole graph does not belong in one Lambda invocation — a weekly
run takes minutes to tens of minutes and holds a per-topic lock. The shape is:

```text
EventBridge Scheduler (weekly, per topic)
        │
        ▼
start-run Lambda  ──►  long-running worker (EC2 free tier)
                              │
                              ├── academic APIs (OpenAlex, Semantic Scholar, arXiv)
                              ├── inference (local runtime or NIM)
                              ├── S3            (PDFs, parsed text, cards, reports, manifests)
                              ├── DynamoDB      (runs, papers, verdicts, analyses, syntheses)
                              └── CloudWatch    (structured logs)
```

Lambda is right for: the start-run trigger, topic CRUD, fetching the latest report, and small
metadata reads. It is wrong for the run itself.

The worker runs exactly `research-agent run <topic_id>`, the same command an operator types and the
same command the local schedules invoke. That is the point of keeping scheduling outside the graph.

## What the conformance tests prove

`tests/unit/test_portability_conformance.py` and `tests/unit/test_portability_boundaries.py`, both in
the default suite:

- Substituting an object store for the filesystem needs no application change: a paper card is
  written and a parsed paper is read back through `load_parsed` over S3-shaped keys, and the
  latest-report lookup works from an object listing.
- An object store still refuses a key that escapes its topic prefix.
- Paper and analysis records round-trip through a partition/sort-keyed table via the same Pydantic
  models the SQLite repositories use, so the domain model is the contract rather than the SQL.
- The EventBridge schedule is deterministic, targets the same command, sets `MaximumRetryAttempts: 0`
  (a retry would collide with the per-topic lock), and contains no credential.
- Remote secret backends resolve the same logical names and **never** fall back to the environment;
  a missing secret names the secret and not a value.
- Logs are one JSON object per line with an aware timestamp — the CloudWatch contract.
- **Statically:** no module under `workflow/` names `sqlite3`, `pathlib`, `boto3`, a `Sqlite*`
  repository, `LocalArtifactStore`, `DoclingParser`, `PdfDownloader` or a model provider; no domain
  model mentions a provider or a backend; and `pyproject.toml` declares no AWS dependency.

## IAM and secrets

Grant the worker least privilege. The names below are the only ones the application uses
(`SecretMapping.names()`): `nim_api_key`, `semantic_scholar_api_key`, `openalex_mailto`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Artifacts",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::research-agent-<account>",
        "arn:aws:s3:::research-agent-<account>/topics/*"
      ]
    },
    {
      "Sid": "Metadata",
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query", "dynamodb:UpdateItem"],
      "Resource": "arn:aws:dynamodb:<region>:<account>:table/research-agent-*"
    },
    {
      "Sid": "Secrets",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter"],
      "Resource": "arn:aws:ssm:<region>:<account>:parameter/research-agent/*"
    },
    {
      "Sid": "Logs",
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:<region>:<account>:log-group:/research-agent/*"
    }
  ]
}
```

Rules that hold on both sides of the boundary: secrets are never written to a schedule, a manifest, a
report or a log; parameters are stored as `SecureString`; the run's own redaction filter covers
anything that reaches a log line anyway; and no credential is ever committed.

## Cost guardrails

`free_plan_only` defaults to true, and the profile refuses these outright: EKS or any Kubernetes,
NAT Gateway, OpenSearch or Elasticsearch, SageMaker, Fargate, RDS or Aurora, MSK, and paid GPU
endpoints. A deployment that genuinely needs one must set `free_plan_only=False` explicitly, which
makes the decision visible rather than accidental.

Cheap by construction: one weekly run per topic, S3 storage measured in megabytes, DynamoDB on-demand
at a few hundred writes per run, CloudWatch with a short retention, and a worker that exists only
while a run does. Inference stays the one place real money could appear — the capability router keeps
local inference the default and NIM optional.

## Runbook

1. Create the bucket, the tables, the parameter path, the log group and the scheduler role.
2. Store the secrets as `SecureString` under `/research-agent/<env>/`.
3. Deploy the worker with the project installed and a profile whose `target` is `aws`.
4. Render the schedule: `research-agent schedule generate --topic <id> --backend eventbridge`, fill
   in the real `Arn` and `RoleArn`, then `aws scheduler create-schedule --cli-input-json file://…`.
5. Verify with one manual `research-agent run <topic_id>` on the worker and read the manifest it
   writes beside the report.
6. To roll back to local, switch the profile to `local` and reinstall the launchd agent. No code
   changes, because nothing in the workflow knows which backend it is using.

## What is not here

No cloud resources are created, no deployment is performed, no multi-region story, and no thin AWS
adapter is shipped. Each of those would need credentials this project does not want, and the
boundaries are provable without them.
