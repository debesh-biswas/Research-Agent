# Local Operations

How to run, inspect and schedule the Research Agent on one machine. Everything here is local and
free: no paid infrastructure, no always-on service.

## Prerequisites

- Python 3.12 or newer and [`uv`](https://docs.astral.sh/uv/).
- `uv sync` once, to install the project and its dependencies.
- A `.env` holding whatever optional credentials you have. It is gitignored and must stay that way.
  `.env.example` lists every supported variable; none of them is required for a local run.

## One-off commands

Each stage can be run on its own, which is how to inspect or re-do part of a week:

| Command | What it does |
| --- | --- |
| `research-agent config validate` | Check settings and topics without touching anything |
| `research-agent topic list` | Show stored topics and whether they are enabled |
| `research-agent model check` | Confirm the configured providers answer (key presence only) |
| `research-agent classify --topic <id>` | Discover, triage and select, saving a run |
| `research-agent acquire --topic <id>` | Download the run's open-access PDFs |
| `research-agent parse --topic <id>` | Convert those PDFs into reusable text |
| `research-agent analyze --topic <id>` | Analyse the selected papers and write paper cards |
| `research-agent synthesize --topic <id>` | Compare the week's papers and recent history |
| `research-agent ideate --topic <id>` | Derive supported gaps and research ideas |
| `research-agent report generate --topic <id>` | Assemble the weekly Markdown report |
| `research-agent report latest <id>` | Print the newest stored report's path |

## Whole runs

```bash
uv run research-agent run <topic_id>     # one topic, start to report
uv run research-agent run-all            # every enabled topic in turn
```

`run` executes the complete LangGraph workflow. It holds a per-topic lock for the duration
(`data/locks/<topic_id>.lock`), so a scheduled run and a manual one cannot collide; a second
invocation exits non-zero with `locked`. A lock left behind by a process that no longer exists is
reclaimed automatically.

Exit codes:

| Outcome | Exit code | Meaning |
| --- | --- | --- |
| `completed` | 0 | Every stage succeeded |
| `degraded` | 0 | Some stage failed, a report was still produced |
| `failed` | 1 | No report was produced; partial artifacts are kept |
| `skipped` | 1 | The topic is disabled |
| `locked` | 1 | Another run of this topic is in progress |

A degraded run is normal: a paper with no open-access PDF, one unparseable file or a provider outage
each degrade one part of the report and are listed in its Run Provenance section. Interrupting a run
with Ctrl-C closes the open run as `failed` and leaves everything already written on disk.

## Where things land

```text
data/
  research_agent.db                      # runs, papers, verdicts, analyses, syntheses, gaps, ideas
  locks/<topic_id>.lock                  # held only while a run is in progress
  topics/<topic_id>/papers/              # downloaded PDFs
  topics/<topic_id>/parsed/              # parsed Markdown and JSON
  topics/<topic_id>/analyses/            # per-paper cards
  topics/<topic_id>/runs/                # per-run ideation artifacts
  topics/<topic_id>/reports/             # YYYY-MM-DD_weekly_report.md
```

Nothing under `data/` is committed.

## Weekly schedule

Scheduling lives outside the workflow: the scheduler runs exactly the command you would type.

```bash
uv run research-agent schedule generate --topic <id>                     # launchd (macOS default)
uv run research-agent schedule generate --topic <id> --backend cron      # crontab line
uv run research-agent schedule generate --topic <id> --at 06:15 --output weekly.plist
```

The day comes from the topic's `scheduling.day`; `--at` sets the local time of day. The rendered
schedule contains a command and paths only — never a credential — so it is safe to commit or share.
The output ends with the one command that installs it (`launchctl bootstrap …` or `crontab …`).

The same command is what an AWS EventBridge Scheduler target would invoke later; nothing about the
workflow changes.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `locked` | A run is in progress. Wait, or delete `data/locks/<topic_id>.lock` if you are sure none is. |
| `skipped` | The topic is disabled: `research-agent topic enable --id <id>`. |
| Every paper is abstract-only | No open-access PDF was found, or parsing failed. The report says which. |
| `MODEL_API_ERROR` in the report | The configured provider did not answer. `research-agent model check`. |
| Empty week | Nothing new matched. The run broadens its search once automatically before concluding this. |
| A report looks stale | An unchanged paper is not re-analysed. Force it with `analyze --force`. |
