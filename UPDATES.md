# Project Updates

This is the append-at-top handoff log for the Personal Weekly AI Research Intelligence Agent. Follow the required entry format and workflow in `AGENTS.md`. Never record secrets.

## 2026-10-29 — Retry brief local-model failures (complete)

- **Feature/branch:** `FIX23-retry-local-model`, off `main` at `c4dbb4b`.
- **Status:** Complete; merged into `main`. Asked for by the user after the 29 Oct cloud run.
- **Problem:** On that run, 8 of 147 papers went unscreened and one analysis failed. Each hit a
  brief OpenRouter error (HTTP 502, or a dropped connection), and the local model was built with
  0 retries. Search sources retry 3 times, PDFs 2 and NIM 2, but the local model had none.
- **Summary:**
  - `retries.local_model` (default 2, also in `config/settings.yaml` and on the Settings page)
    now reaches `LocalModelProvider`, which serves both a local server and OpenRouter-style cloud
    endpoints. It retries HTTP 5xx/429 and dropped connections, with the existing 1 s / 2 s
    backoff and `Retry-After` handling.
  - Timeouts are not retried. A model call may take its whole timeout (600 s in the configs), so
    repeating one would turn a stuck call into half an hour.
  - NIM keeps its 2 router-level retries before falling back to the local model, which now gets
    its own retries too.
  - Fixed along the way: the error message said "failed after 3 attempts" even when it stopped
    after one. It now counts the attempts really made.
- **Files affected:**
  - `src/research_agent/config.py`
  - `src/research_agent/discovery/http.py`: `retry_timeouts`, and the attempt count.
  - `src/research_agent/models/chat.py`
  - `src/research_agent/models/router.py`
  - `src/research_agent/desk/settings_page.py`
  - `config/settings.yaml`
  - `tests/unit/test_models_chat.py`
- **Verification:**
  - A 502, then a dropped connection, then a success gives one result after 3 calls.
  - A timeout makes 1 call and reports "after 1 attempts".
  - `build_router` gives the local model 2 retries.
  - `ruff format --check`, `ruff check` and `mypy` are clean. `uv run pytest -q`: 646 passed,
    3 deselected, coverage 92.98%.
- **Known issues:** An empty reply ("a choice without text content", which is what failed the
  synthesis) is not an HTTP failure, so it is not retried here. That is the synthesis question
  below.
- **Next step:** Synthesis is cut at `synthesis.max_input_chars` (24,000), so a 45-paper week
  reaches the model only partly. On the 29 Oct run it cited 10 of 45 papers. Proposed fix, for the
  user to decide: synthesize in batches that each fit, with thinking kept on, then merge.

## 2026-10-28 — Topic breadth instead of keywords (complete)

- **Feature/branch:** `F57-topic-breadth`, off `main` at `15e9787`.
- **Status:** Complete; merged into `main`. The user asked for it: topics are named, not
  keyworded, and the model decides the terms at a chosen breadth.
- **Summary:**
  - **New topic fields.** A topic now has a `description` (optional, up to 1,000 characters) and
    a `breadth`: `focused`, `balanced` (the default) or `exploratory`.
    - Focused: only papers squarely on the topic, found with its core terms.
    - Balanced: the topic and its close sub-areas, methods and datasets.
    - Exploratory: also neighbouring fields whose ideas could carry over.
  - **Queries.** The query planner's prompt (`query_expansion.v2`) gets the description and the
    breadth's search guidance, so the model chooses the searches each run.
  - **Screening.** The screening prompt (`screening.v3`) gets the description and the breadth's
    acceptance rule. Exploratory accepts adjacent work but scores it medium.
  - **Re-screening.** Changing a topic's breadth or description changes the screening prompt, so
    F53 screens the papers again rather than reusing old verdicts.
  - **Desk forms.** New topic is now one form: name, "What it covers", "How widely to search"
    (three options), then advanced settings. There is no keyword step. The edit page swaps the
    keyword box for the same two fields.
  - **Topics page.** Shows "Exploratory search · <description>" in place of the keywords.
  - **Week page.** Lists the queries the run sent ("Searched for N queries"), from the new
    `RunSummary.queries`, so the model's choices are visible.
  - **Old keywords.** Keywords set through the CLI or `topics.yaml` still work as extra terms,
    and a desk edit keeps them.
- **Files affected:**
  - `src/research_agent/config.py`: `Breadth`, plus `TopicSettings.description` and
    `TopicSettings.breadth`.
  - `src/research_agent/storage/database.py` and `storage/topics.py`: two topic columns.
  - New `src/research_agent/topics/breadth.py`: the guidance text.
  - `src/research_agent/queries/prompts.py` and `planner.py`.
  - `src/research_agent/screening/prompts.py`.
  - `src/research_agent/domain/runs.py` and `workflow/nodes.py`: `queries`.
  - `src/research_agent/desk/shelf.py`.
  - `src/research_agent/desk/server.py`: removed `/api/topics/suggest`, `TopicSuggestRequest`
    and `suggest`.
  - `web/js/desk.js`: `breadthField`, `describeField`, the new `viewNewTopic`, `queriesBlock`;
    chips and the suggestion step removed.
  - `web/css/desk.css`: breadth options; chip styles removed.
  - `README.md`.
  - Tests in `test_topic_breadth.py`, `test_storage_topics.py`, `test_desk_server.py`,
    `test_desk_shelf.py`, `test_reading_desk.py` and `tests/integration/test_run_cli.py`. Pinned
    prompt versions were updated.
- **Decisions:**
  - Terms are chosen per run by the planner, not stored. The planner already ran the model every
    run, and this keeps the terms tracking recent developments (history) as well as the breadth.
  - The desk's keyword-suggestion route was removed rather than left as dead code. The CLI's
    `topic new` keeps `suggest_keywords`.
  - Breadth does not change selection's minimum relevance score. It works through the screener's
    scores, so the Settings page's threshold still means one thing.
- **Verification:**
  - Real model (OpenRouter `nvidia/nemotron-3.5-super-vl:free`), topic "Embodied Spatial
    Intelligence" with a description, on 6 papers from the cloud run:
    - focused searched the core ("embodied metric semantic mapping", …) and scored the two papers
      the cloud run kept 0.25 and 0.25;
    - balanced added SLAM and Matterport benchmarks and scored them 0.8 and 0.25;
    - exploratory added cognitive mapping and RL navigation and scored them 0.9 and 0.55;
    - the four off-topic papers stayed at 0.0–0.1 at every breadth.

    These are single samples from a free model, so individual scores vary call to call, but the
    order held.
  - Browser on the real desk with a copy of the cloud-run library (run start stubbed):
    - balanced was the default;
    - submitting with no name said "Give the topic a name.";
    - creating "Spatial Memory" as exploratory stored its description and breadth and started its
      run;
    - the Topics row read "Exploratory search · …";
    - editing it to focused saved, and kept keywords `[]`;
    - the Week page listed the 3 searched queries;
    - axe found 0 violations on the new and edit pages;
    - no page errors.
  - `ruff format --check`, `ruff check` and `mypy` are clean. `uv run pytest -q`: 644 passed,
    3 deselected, coverage 92.97%.
- **Known issues:** Existing topics start as balanced with no description. Adding a description
  is the best way to steer them. The cloud run showed a bare name screens too narrowly.
- **Next step:** On the user's side:
  - give each real topic a description and choose a breadth;
  - run it, and check "Searched for" on the Week page.

  The deferred Mac timing run remains.

## 2026-10-28 — Settings page in the desk (complete)

- **Feature/branch:** `F34-settings-screen`, off `main` at `7d00904`.
- **Status:** Complete; merged into `main`. The user asked for it, and for F50 (undo after
  clearing) to stay off.
- **Summary:** A Settings page (`#/settings`, linked in the footer) edits 15 common settings in
  three groups:
  - **Models:** which provider does deep reads, the local model's address, name and timeout,
    and the NIM model name and timeout.
  - **Choosing papers:** the minimum relevance score, the quality weight, the recency window and
    the preferred venues.
  - **Speed and retries:** downloads and model calls at once, and retries for sources, NIM and
    PDFs.

  It also shows the library folder (read-only), and whether the NIM key, the Semantic Scholar
  key and the OpenAlex email are set. It never shows their values.
  - **Saving.** Changes go to the library's new `app_settings` table. `settings.yaml` is never
    rewritten, so its comments survive.
  - **Precedence.** Highest first: environment, `.env`, desk changes, `settings.yaml`, defaults.
  - **Everywhere.** Every CLI command now loads settings through
    `storage.app_settings.load_settings`, so desk changes apply to runs started from the terminal
    too. The desk uses them from the next run or question on; a run already going keeps its own.
  - **Locked fields.** A field set by an environment variable or a `.env` line is disabled, with
    the variable's name. A value submitted for it anyway is never saved.
  - **Reset.** "Reset to the settings file" (behind a confirm dialog) clears every desk change.
- **Files affected:**
  - `src/research_agent/storage/database.py`: `app_settings` migration.
  - New `src/research_agent/storage/app_settings.py`: `SqliteSettingsOverrides`, `merged`,
    `load_settings`, `read_overrides`.
  - New `src/research_agent/desk/settings_page.py`: `FIELDS`, `page`, `overrides_for`,
    `SettingsProblem`.
  - `src/research_agent/desk/server.py`: `LocalDesk(..., settings_file=)`, `settings_page`,
    `save_settings`, and `GET`/`PUT`/`DELETE /api/settings`.
  - `src/research_agent/cli.py`: 21 call sites now use `load_settings`, and the desk is given
    its settings file.
  - `web/js/desk.js`, `web/css/desk.css` and `README.md`.
  - Tests in `tests/unit/test_settings_page.py`, `test_desk_server.py` and
    `test_reading_desk.py`.
- **Decisions:**
  - Desk changes live in the library rather than in a rewritten YAML file, which would lose the
    explanatory comments. A backup carries them with the library.
  - Only values that differ from the file are stored. Setting a field back to the file's value
    removes the change.
  - A saved change that a later version rejects is ignored with a warning, so it can never stop
    every command from starting.
  - The library folder is not editable: moving it would leave the library behind.
  - Sources' pacing and token limits are left to the file. They are tuning that rarely needs
    changing.
- **Verification:**
  - Unit tests cover:
    - precedence: file, then desk, then environment;
    - an invalid saved change being ignored;
    - a missing database or table;
    - only real differences being saved;
    - a bad value refused by its label, and an unknown field refused;
    - `.env` lock detection, where a commented line does not count;
    - secrets never on the page;
    - a LocalDesk save, which a fresh `load_settings` (as a command would run) then sees;
    - reset, and refusal without a settings file.
  - Server tests cover the three routes and their 400s.
  - Browser on the real desk, started from a folder whose `.env` sets the NIM model:
    - that field was locked and named the variable;
    - saving NIM retries 0, minimum score 0.5 and venues "CVPR, CoRL" showed "Settings saved." and
      marked those fields as changed;
    - after a reload they were still set;
    - reset through the dialog restored the file values;
    - `settings.yaml` was byte-for-byte unchanged;
    - axe found 0 violations;
    - nothing overflowed at 390 px (long variable names now wrap);
    - no page errors.
  - `ruff format --check`, `ruff check` and `mypy` are clean. `uv run pytest -q`: 638 passed,
    3 deselected, coverage 92.85%.
- **Known issues:** `log_level` and the library folder still need the file. The page does not
  warn about unsaved edits when you navigate away.
- **Next step:** `F57`: topic breadth. Topics get a breadth setting (focused / balanced /
  exploratory). The model derives the search terms from the topic name and description at that
  breadth, so the reader never types keywords, and screening is told how widely to accept.

## 2026-10-28 — Packaging and licence review (complete)

- **Feature/branch:** `F56-packaging-and-licences`, off `main` at `6b0768a`.
- **Status:** Complete; merged into `main`. Roadmap M12. F34 (settings screen) still needs a
  decision from the user and was not built.
- **Summary:**
  - **Desk page in the wheel.** The wheel now ships the desk's page, fonts and favicon as
    `research_agent/web/`, through a hatch `force-include`.
  - **Found from any folder.** `research-agent desk` finds them next to the installed package, or
    beside the source in a checkout (`cli._web_root`), never in the current directory. Before
    this, the desk worked only when started from the repository root, and an installed copy had
    no page at all.
  - **LICENSE added.** It holds the MIT licence `pyproject.toml` already declared, credited to its
    author, and is now in the wheel's `dist-info/licenses/`.
  - **README.** It explains that commands read `config/` from the current folder, and how to
    install the command with `uv tool install .`. A new "Licences" section was added.
- **Licence review:**
  - Direct dependencies are MIT (Docling, LangGraph, Pydantic, pydantic-settings, PyYAML,
    RapidFuzz, Typer) or BSD-3-Clause (HTTPX). All are compatible with MIT.
  - A scan of all 155 installed distributions found nothing in the GPL family. certifi, orjson,
    pathspec and tqdm are MPL-2.0, which is file-level copyleft and fine when used unmodified.
  - The fonts are under the SIL OFL 1.1, with licences shipped (F52).
  - The vendored ponytail skill is MIT, with its licence in `.claude/skills/ponytail/`.
  - Docling's runtime-downloaded models carry their publishers' licences. The README notes this.
- **Files affected:** `pyproject.toml`, `src/research_agent/cli.py`, `LICENSE`, `README.md`,
  `tests/unit/test_reading_desk.py`.
- **Decisions:**
  - Defaults stay relative to the current folder (`config/…`, `data`). Moving them to a user
    config directory would change where existing libraries live, for no gain to a single user who
    runs from one folder.
  - No installer script: `uv sync` (checkout) and `uv tool install .` (command) already cover it.
- **Verification:**
  - `uv build --wheel`: the wheel has all 16 `research_agent/web/` files and the licence.
  - The extracted wheel, imported with `-I` from an unrelated folder (with
    `cli.__file__` inside the extracted wheel), served `/`, a woff2, the favicon and
    `/api/shelf`, all with HTTP 200 and the right types.
  - A new test confirms `_web_root()` from a foreign working directory, and that the wheel
    includes `web/`.
  - `ruff format --check`, `ruff check` and `mypy` are clean. `uv run pytest -q`: 630 passed,
    3 deselected, coverage 92.65%.
- **Known issues:** `uv tool install .` itself was not run here: it downloads Docling's full torch
  stack. The wheel it would install is the one verified above.
- **Next step:** The roadmap is built through M12. Left for the user:
  - decide whether to build F34, the settings screen;
  - decide whether to build F50, undo after clearing (backups cover recovery today);
  - run the deferred timing run on their Mac;
  - add keywords to their real topics, which the cloud run showed matter for screening.

## 2026-10-28 — Retry failed full-text reads on the next run (complete)

- **Feature/branch:** `F55-retry-failed-full-text`, off `main` at `d6dd8de`.
- **Status:** Complete; merged into `main`. Roadmap M11, third and last item.
- **Finding:** Most failures were already retried by running the topic again:
  - searches run again;
  - a failed analysis stores nothing, so it is redone;
  - cached downloads, parses, analyses and (since F53) screenings are reused.

  One gap was real. A transient PDF download or parse failure (timeout, 5xx) still produced an
  abstract-only analysis, and the paper then counted as analyzed. Selection skipped it
  (`already_analyzed`) on every later run, so one timeout left a paper abstract-only for good.
- **Summary of the fix:**
  - `select_papers` makes a paper eligible again when all of these hold: its stored analysis is
    abstract-only, it has no parsed text, and it has a legal PDF URL (`pdf_candidates`). It is
    re-selected, its download or parse is retried, and it is kept on that run.
  - `PaperAnalyzer.analyze` redoes an abstract-only analysis once parsed text is available,
    instead of returning the cached one.
  - Papers with no open-access PDF stay abstract-only: there is nothing to retry.
  - Papers already read in full are still never redone.
  - The Week page's error list now says: "Run the topic again to retry what failed. Screening and
    full-text reads that already worked are reused, not redone."
- **Files affected:**
  - `src/research_agent/workflow/nodes.py`: `_full_text_worth_retrying`.
  - `src/research_agent/analysis/analyzer.py`.
  - `web/js/desk.js`: `errorBlock`.
  - Tests in `tests/unit/test_workflow_nodes.py`, `test_analysis_analyzer.py` and
    `tests/integration/test_run_cli.py`.
- **Decisions:**
  - No separate "retry" button or command. "Run now" already does the right thing now that this
    gap is closed, and a second path would duplicate the workflow.
  - No retry ceiling is needed. A paper only comes back while discovery finds it again, which is
    the lookback window or a re-run.
- **Verification:**
  - New CLI integration test: run 1 with every PDF failing gave abstract-only reads for both
    papers. Run 2 with PDFs back read both in full, and both runs kept them. Without the fix, run 2
    made no new reads and the test fails.
  - Companion test: two healthy runs leave the analysis count unchanged, and the only unselected
    reason is `already_analyzed`.
  - Unit tests cover the predicate (6 cases, including no PDF URL, parsed text present, a full read
    and no analysis) and the analyzer (cached, then upgraded with full text, then cached again; two
    model calls).
  - Browser: the hint shows under the cloud run's 10 errors, with no page errors.
  - `ruff format --check`, `ruff check` and `mypy` are clean. `uv run pytest -q`: 628 passed,
    3 deselected, coverage 92.67%.
- **Known issues:** A paper whose PDF URL is permanently broken (a 404) is retried each time
  discovery returns it. That costs one failed request per run, and the paper is still read from
  its abstract.
- **Next step:** Roadmap M12. `F56`: packaging, installer and licence review.
  - Check that a built wheel carries `web/` (the desk's page, fonts and favicon) and
    `config/` defaults.
  - Check that `research-agent desk` finds `web/` when installed rather than run from the repo.
  - Check that third-party licences are compatible and listed.

  The F34 settings screen is deferred to here too; ask the user before building it.

## 2026-10-28 — Model usage per run (complete)

- **Feature/branch:** `F54-model-usage`, off `main` at `58313cb`.
- **Status:** Complete; merged into `main`. Roadmap M11, second item.
- **Summary:** Each run now records what it asked of the models, per provider and model: calls,
  prompt tokens, completion tokens, time, and how many calls were fallbacks.
  - It is stored in the run summary (`RunSummary.model_usage`).
  - The Week page shows a collapsible line such as "96 model calls · 214k tokens in · 18k out",
    with one row per model.
  - Tokens come from the server's `usage` field; a server that does not report them counts 0.
- **Files affected:**
  - `src/research_agent/domain/runs.py`: `ModelUsage` and `RunSummary.model_usage`.
  - New `src/research_agent/models/usage.py`: `UsageMeter`.
  - `src/research_agent/models/router.py`: `meter=`, and `_call` for every provider call;
    `build_router(..., meter=)`.
  - `src/research_agent/operations/wiring.py` and `workflow/services.py` (`usage`).
  - `src/research_agent/workflow/nodes.py`: persist writes the totals.
  - `src/research_agent/desk/shelf.py`: `modelUsage`.
  - `web/js/desk.js` (`usageBlock`, `formatCount`) and `web/css/desk.css`.
  - Tests in `test_models_router.py`, `test_desk_shelf.py` and `tests/integration/test_run_cli.py`.
- **Decisions:**
  - Replies are counted before validation, because a malformed reply still used tokens.
  - Calls that raised (timeouts, HTTP errors) are not counted: the server reports no usage for
    them, and the run's error list already records them.
  - No money figure is shown. NIM's free tier, local models and OpenRouter's free models carry
    no price in the configuration, and a made-up rate would mislead. Tokens are the honest unit.
  - Old runs simply have no usage line.
- **Verification:**
  - Router test: 2 failed NIM attempts were not counted; the fallback, a plain local call and an
    invalid-JSON reply were (3 calls, 1 fallback).
  - Meter test: tokens and time add per model, `None` counts as 0, and the order is stable.
  - Shelf test: the camelCase fields.
  - The CLI run test now asserts the persisted `model_usage` (local, with calls > 0).
  - Browser on a copy of the cloud-run library with injected usage: "96 model calls · 214k tokens
    in · 18k out", and a row with "28 min · 4 as fallback". No page errors.
  - `ruff format --check`, `ruff check` and `mypy` are clean. `uv run pytest -q`: 619 passed,
    3 deselected, coverage 92.65%.
- **Known issues:** Desk Ask and keyword suggestions are not metered, since they belong to no
  run.
- **Next step:** Roadmap M11. `F55`: retry the failed downloads and analyses of a finished run
  without a full re-run. First check whether a re-run already skips the work that succeeded:
  F53 covers screening, and `analyzed_unchanged` covers analyses.

## 2026-10-28 — Reuse screening for unchanged papers (complete)

- **Feature/branch:** `F53-reuse-screening`, off `main` at `1da502e`.
- **Status:** Complete; merged into `main`. Roadmap M11, first item.
- **Summary:** Screening now reuses an earlier verdict when the model would be asked exactly the
  same question. Before, every run screened every candidate again, including the days a weekly
  10-day lookback shares with the previous week and every paper in a re-run after a failure.
  - Each screening is keyed by a SHA-256 of: the prompt version, the configured NIM and local
    model names, the system prompt, and the rendered prompt. The rendered prompt holds the topic
    name and keywords, the reader's vote examples, the paper title and the abstract.
  - On a match, the stored active verdict is copied into this run, with provenance
    `{"reused": true, "prompt_key": …}`, and no model is called.
  - Any change to a paper's text, the topic's keywords, the votes, the prompt version or a model
    name asks the model again.
  - The run counts gain `screening_reused`, so the manifest shows how many were reused.
- **Files affected:**
  - `src/research_agent/storage/database.py`: migration adding `classifications.prompt_key`
    plus an index.
  - `src/research_agent/storage/results.py`: `save_classification(..., prompt_key=)` and
    `screening_for`.
  - `src/research_agent/screening/service.py`: `ScreeningCache` protocol, `cache=`,
    `_prompt_key`.
  - `src/research_agent/workflow/nodes.py`: classify stores the key and counts reuse.
  - `src/research_agent/operations/wiring.py`: passes the results repository as the cache.
  - Tests in `tests/unit/test_screening_service.py` and `tests/integration/test_run_cli.py`.
- **Decisions:**
  - The key is the exact prompt, not a hand-picked list of "topic definition" fields. That keeps
    it correct whenever the prompt changes: anything the model sees is in the key, and nothing it
    does not see is.
  - Failed screenings store no row, so they are always retried.
  - Shadow (`is_active = 0`) rows are never reused.
  - Rows from before this migration have no key, so the first run after upgrading screens as
    before.
  - Switching between NIM and local without renaming a model reuses verdicts. To force a fresh
    screen, change the model name or the keywords.
  - The standalone `classify` CLI stage does not persist, so it is left without a cache.
- **Verification:**
  - Unit tests with the real SQLite repository:
    - the second identical screen made no model call and was marked reused, with the same key;
    - new keywords, new vote examples and a different local model each called the model again;
    - shadow rows and rows without a key never match.
  - New CLI integration test: two `research-agent run` calls over the mocked endpoints. The
    second run sent 0 screening requests, and its classifications were all marked reused.
    Disabling the cache in the wiring makes it fail (4 calls against 2).
  - `ruff format --check`, `ruff check` and `mypy` are clean. `uv run pytest -q`: 617 passed,
    3 deselected, coverage 92.61%.
- **Known issues:** None found.
- **Next step:** Roadmap M11. `F54`: a usage view showing model calls, tokens and time per run
  from the stored provenance. Check first which token counts are recorded (`ModelResult` has
  `prompt_tokens` and `completion_tokens`), and whether they are persisted anywhere.

## 2026-10-28 — Offline fonts, favicon, period labels, accessibility (complete)

- **Feature/branch:** `F52-offline-fonts-and-polish`, off `main` at `7514bef`.
- **Status:** Complete; merged into `main`. Roadmap M10, second and last item.
- **Summary:**
  - **Self-hosted fonts.** The desk now serves its three fonts from `web/fonts/`: IBM Plex Mono
    400/500, and Literata and Schibsted Grotesk as variable fonts. Only the latin and latin-ext
    subsets are included, 276 KB of woff2 in total. The page makes no third-party request, so it
    renders the same offline and tells Google nothing. The server serves `.woff2` as `font/woff2`.
  - **Favicon.** A favicon SVG was added.
  - **Period labels.** A single-day period now reads "27 Oct 2026" instead of "27–27 Oct 2026".
    A period that crosses a year names both years ("28 Dec 2026 – 6 Jan 2027").
  - **Contrast.** `--faint` darkens from `#7c8484` to `#656d6d`, which gives at least 4.63:1 on
    every surface. It is still lighter than `--muted`, so the hierarchy holds.
- **Files affected:**
  - `web/index.html`;
  - `web/fonts/` (8 woff2, `fonts.css`, `OFL-*.txt`);
  - `web/favicon.svg`;
  - `web/css/desk.css`;
  - `web/js/desk.js` (`formatPeriod`);
  - `src/research_agent/desk/server.py` (`_TYPES`);
  - tests in `tests/unit/test_reading_desk.py` and `test_desk_server.py`.
- **Decisions:**
  - Fonts came from Google Fonts' CSS API, and the licences from `google/fonts`. The SIL OFL 1.1
    allows redistribution with the licence, so each family's licence ships beside its files.
  - Cyrillic, Greek and Vietnamese subsets were left out. Those characters fall back to the system
    fonts in each stack.
  - The accessibility work is based on measurement. axe-core 4.10.2 (WCAG 2 A/AA, 2.1 AA and best
    practice) ran on all 13 pages, against a copy of the cloud-run library:
    - before: colour contrast was the only finding, on every page (`--faint` at 3.34–3.82:1);
    - after: 0 violations on every page and in the open confirm dialog.
  - A keyboard pass tabbed 40 stops on the Week, Topics, Library and Runs pages. Every focused
    element showed an outline or ring.
  - Dark mode and keyboard shortcuts were not built: they are optional, and nothing asked for them.
- **Verification:**
  - Browser:
    - no request left 127.0.0.1;
    - all 10 font faces reported loaded;
    - `formatPeriod` gave "27 Oct 2026", "17–27 Oct 2026", "28 Sept – 7 Oct 2026" and
      "28 Dec 2026 – 6 Jan 2027";
    - the favicon and fonts were served with their types.
  - Tests:
    - every `url()` in `fonts.css` exists;
    - each licence is present;
    - `index.html` has no Google Fonts link;
    - the server serves `.woff2`.
  - `ruff format --check`, `ruff check` and `mypy` are clean. `uv run pytest -q`: 614 passed,
    3 deselected.
- **Known issues:** `en-GB` short months write September as "Sept" (browser ICU data). That is
  correct British usage, so it was left.
- **Next step:** Roadmap M11. `F53`: skip re-screening papers whose stored screening result is
  for the same topic definition and prompt version. Check first how classification reuse
  already works, so the fix is not rebuilding something that exists.

## 2026-10-28 — Confirm dialogs and request timeouts (complete)

- **Feature/branch:** `F51-dialogs-and-timeouts`, off `main` at `d57e718`.
- **Status:** Complete; merged into `main`. Roadmap M10, first item.
- **Summary:**
  - **Confirm dialog.** The four destructive actions now ask in an in-page `<dialog>` instead of
    the browser's `confirm()`: clear a run, clear all runs, delete a topic, and start an Ask
    conversation over. The button names the action ("Clear run", "Delete topic", …), styled in
    the carmine danger colour. Cancel has focus, so Enter and Escape both cancel, and focus
    returns to the button that opened it.
  - **Request timeouts.** Calls that only read or write the library give up after 20 s
    (`REQUEST_MS`, through `request()` with `AbortSignal.timeout`). These are the shelf, library,
    old runs, screened papers, reading state, Ask threads, storage and topic changes. A stuck
    request can no longer stall the progress poll or leave a page loading. Ask, keyword
    suggestions and the setup check keep no client timeout: they wait on models and already
    time out on the server.
- **Files affected:** `web/js/desk.js` (`confirmAction`, `request`, `REQUEST_MS`),
  `web/css/desk.css` (`.confirm`, `.danger`), `tests/unit/test_reading_desk.py`.
- **Decisions:**
  - No toast system. Every action that needs feedback already shows a status line (topics, runs,
    notes, Ask turns), and a second channel would say the same thing twice.
  - The dialog is built once and kept outside `#app`, because `render()` replaces `#app`.
- **Verification:** Browser on the real desk with a copy of the cloud-run library:
  - the dialog opened with focus on Cancel, the action "Clear run" and the full message;
  - Escape and Enter each kept both runs, and focus went back to the Clear button;
  - "Clear run" removed one run;
  - topic delete showed "Delete topic" and Cancel kept the topic;
  - no native dialogs fired, and no page errors;
  - with `/api/storage` held open forever, `state.storage` went from pending to failed at the
    20 s timeout, and the Topics page stayed usable.

  The static test asserts no native `confirm(` remains and the shelf uses `request()`.
  `ruff format --check`, `ruff check` and `mypy` are clean. `uv run pytest -q`: 612 passed,
  3 deselected.
- **Known issues:** None found.
- **Next step:** Roadmap M10. `F52`:
  - fix the same-day period label ("27–27 Oct" should read "27 Oct");
  - self-host the fonts so the desk works offline and makes no third-party request;
  - add a favicon;
  - run an accessibility pass (focus styles, labels, contrast).

  Dark mode and keyboard shortcuts are optional: build them only if cheap.

## 2026-10-28 — Clearing runs safely, and storage use (complete)

- **Feature/branch:** `F49-run-files-and-storage`, off `main` at `0fbdc94`.
- **Status:** Complete; merged into `main`. Roadmap M9, second item.
- **Summary:**
  - **Refused while running.** Clearing a run, or all of a topic's runs, now holds the topic's run
    lock. While that topic is running, it is refused with 409: "<Topic> is running; clear runs
    after it finishes." The Runs page shows that message and keeps the run.
  - **Run files deleted.** Clearing now also deletes the files only that run owns: its
    `runs/<run_id>-*` files (manifest, ideation) and its dated report. The report is kept when a
    run that stays ends on the same day, because they share that report file. Papers, their PDFs,
    parsed text, analyses and notes stay in the library. The confirm text says so.
  - **Storage use.** `GET /api/storage` returns the bytes per topic folder, the database (with
    its `-wal`/`-shm` files) and free disk. The Topics page shows "N MB on disk" for each topic and
    "The library uses … on disk; … free." It is fetched once per visit to the page.
- **Files affected:**
  - `src/research_agent/desk/shelf.py`: `owned_files`.
  - `src/research_agent/desk/server.py`: `LocalDesk.delete_run/clear_topic/_idle/_clear/storage`,
    `_folder_bytes`, and the DELETE routes mapping `RunLocked` to 409.
  - `src/research_agent/storage/runs.py`: removed the now-unused `delete_for_topic` and its test.
  - `web/js/desk.js`: `clearRuns`, `state.runsStatus`, `storageLine`, `loadStorage`,
    `formatBytes`.
  - Tests in `tests/unit/test_desk_server.py`.
- **Decisions:**
  - Paper files are never deleted on clear. A paper is a library item (saved, noted, found by
    search) beyond the run that kept it, and deduplication means a later run would not fetch it
    again.
  - No "also delete files" checkbox. The only run-owned files are small and meaningless once their
    run is gone, so they always go.
  - The lock blocks clearing any run of a topic while it is running, not only the running run
    itself, because a running run reads earlier runs' syntheses as history.
  - F50 (undo after clearing) is not built: `research-agent backup` already covers recovery. Build
    it only if the user asks.
- **Verification:**
  - LocalDesk test with three runs, two of them on the same day:
    - clearing the old one deleted its manifest, ideation and report, and kept the PDF and the
      other run's files;
    - clearing one same-day run kept the shared report;
    - storage counted the topic's bytes;
    - a lock held by a live pid refused both kinds of clear and kept the run;
    - clear-all left only the PDF and kept the topic;
    - an unknown run is a no-op.
  - Server: 409 bodies and `/api/storage`.
  - Browser on the real desk with a copy of the cloud-run library:
    - Topics showed "15 MB on disk" and "21.8 GB free";
    - with a live lock, Clear showed the running message and kept both runs;
    - after the lock went, clearing the real run deleted exactly its report and manifest, and kept
      its 8 paper files;
    - no page errors.
  - `ruff format --check`, `ruff check` and `mypy` are clean. `uv run pytest -q`: 611 passed,
    3 deselected, coverage 92.59%.
- **Known issues:** Storage is per topic folder and database only; Docling's model cache lives
  outside the library and is not counted.
- **Next step:** Roadmap M10. `F51`: in-app confirm dialogs instead of `confirm()`, a short
  toast after actions, and request timeouts so a hung server call does not leave a button
  spinning.

## 2026-10-28 — SQLite WAL and busy timeout (complete)

- **Feature/branch:** `FIX22-sqlite-wal`, off `main` at `afceca8`.
- **Status:** Complete; merged into `main`. Roadmap M9, first item.
- **Summary:** `storage.database.connect` now opens every connection with
  `PRAGMA journal_mode = WAL`, which is persistent in the file, so existing libraries switch on
  their next open. The busy timeout rises from 5 s to 30 s (`BUSY_TIMEOUT_SECONDS`). The desk
  can now read while a run writes.
- **Files affected:** `src/research_agent/storage/database.py`,
  `tests/unit/test_storage_migrations.py`, `README.md` (use `backup`, not a hand copy, because of
  the `-wal` file).
- **Decisions:** The fix is based on a measurement, not a guess. On a copy of the cloud-run
  library, one process wrote small transactions in a loop (like `mark_stage` and error rows)
  while two processes built the desk shelf for 20 s:

  | | Rollback journal (before) | WAL (after) |
  |---|---|---|
  | Shelves built | 13–15 | 159–162 |
  | Slowest shelf | 14.2 s | 0.56 s |
  | "database is locked" | once | none |
  | Writer transactions | 5,959 | 39,812 |

  The shelf alone takes 0.17 s. `*.db-*` was already git-ignored. Backups already use SQLite's
  online backup API, which reads through the WAL.
- **Verification:**
  - New regression test: a reader with a 100 ms busy timeout reads committed data while a writer
    holds `BEGIN EXCLUSIVE`, then sees the row after the commit. Without the fix it fails, and a
    direct check of the old mode gave "database is locked".
  - `ruff format --check`, `ruff check` and `mypy` are clean.
  - `uv run pytest -q`: 611 passed, 3 deselected, coverage 92.44%. The backup and restore tests
    pass under WAL.
- **Known issues:** The CLI's `_open_repository` leaves connections for the process to close
  (the ResourceWarnings in the test run). That is harmless, since exit closes them and removes the
  `-wal` file, but it is untidy. It predates this change.
- **Next step:** Roadmap M9. `F49`: show storage use per topic, offer to delete a run's files when
  clearing it, and refuse to clear a run that is still going.

## 2026-10-28 — Ask across weeks (complete)

- **Feature/branch:** `F48-ask-across-weeks`, off `main` at `da69177`.
- **Status:** Complete; merged into `main`. Roadmap M8, second and last item.
- **Summary:** A question about the week now also sends `earlier_weeks`: up to 4 earlier runs of
  the same topic from the shelf (newest first; runs with no summary and no developments, such as
  a run still going, are skipped), each with its period, summary (cut at 500 characters) and first
  3 developments. It also sends this run's `changes_from_history`. A question about one paper does
  not. The Ask page gains the chip "How does this compare with earlier weeks?". The prompt
  (`desk_ask.v3`) now also asks the model to name papers by title in the prose, never by id.
- **Files affected:** `src/research_agent/desk/ask.py` (`_earlier_weeks`, `EARLIER_WEEKS`,
  `_context(..., weeks=)`), `web/js/desk.js`, `README.md`, `tests/unit/test_desk_ask.py`.
- **Decisions:** Earlier weeks come from the shelf the desk already builds, not from a new query.
  They have their own budget, a quarter of `reports.max_input_chars`, and the oldest is dropped
  first. The first version shared the card budget, and the real check showed why that fails: at
  the default 8,000 characters, two cards already fill it, so every earlier week was dropped. The
  model then reported that "the earlier_weeks list is empty". The key is now left out when no
  week fits. Citations stay limited to this run's cards, because the page can only link papers on
  the open run. Earlier weeks are named by period.
- **Verification:** Unit tests cover:
  - the window: older runs only, newest first, empty runs skipped, at most 4;
  - none for a paper question or for the oldest run;
  - their own budget, which never costs this week a card;
  - no key when nothing fits;
  - compact entries.

  Real model (OpenRouter `nvidia/nemotron-3.5-super-vl:free`), on a scratch copy of the cloud-run
  library with one added older week:
  - "Which paper should I read first?" then "Why that one rather than the other?": the follow-up
    resolved "that one" from the stored turn.
  - "How does this compare with earlier weeks?" contrasted 1–10 Oct with this week by period, and
    named papers by title.

  `ruff format --check`, `ruff check` and `mypy` are clean. `uv run pytest -q`: 610 passed,
  3 deselected, coverage 92.44%.
- **Known issues:** Earlier weeks come from the shelf, which holds the newest 12 runs per topic. A
  run opened from the Library beyond that still cannot be asked about (see F47).
- **Next step:** Roadmap M9. `FIX22`: open SQLite with WAL and a busy timeout, so the desk and a
  run writing at the same time do not fail with "database is locked". Then `F49`: storage usage,
  an option to delete a run's files when clearing it, and refusing to clear a running run.

## 2026-10-28 — Ask keeps the conversation (complete)

- **Feature/branch:** `F47-ask-conversation`, off `main` at `8afc4b0`.
- **Status:** Complete; merged into `main`. Roadmap M8, first item.
- **Summary:** Ask conversations are stored in SQLite, one thread per run (the week) and one
  per paper on that run. A follow-up question is sent with the thread's last 4 turns, so "and the
  second one?" works. Threads come back after a reload, in a new tab, or after a desk restart,
  and "Start over" deletes one (after a confirm). Clearing a run deletes its threads. When no model
  answers, the reply says why (rate-limited / unreachable or too slow / the model returned an
  error) and links to the setup check; failed turns are shown but not stored.
- **Files affected:** `src/research_agent/storage/database.py` (migration: `ask_turns` table with
  `run_id` FK `ON DELETE CASCADE`, plus an index), new `src/research_agent/storage/asks.py`
  (`AskTurn`, `SqliteAskRepository.turns/add/clear`), `src/research_agent/desk/ask.py`
  (`PROMPT_VERSION = "desk_ask.v2"`, `history=`, `HISTORY_TURNS`, `failure_message`),
  `src/research_agent/desk/server.py` (`LocalDesk.ask` reads and appends the thread;
  `thread`/`clear_thread`; `GET`/`DELETE /api/runs/<id>/ask[?paper=<id>]`; the 502 body carries
  `setup: true`), `web/js/desk.js` (threads load from the server instead of sessionStorage),
  `README.md`, tests in `tests/unit/test_storage_asks.py`, `test_desk_ask.py`,
  `test_desk_server.py`.
- **Decisions:** Earlier turns go in the one user message as a short Q/A transcript (each answer
  cut at 1,000 characters) rather than as chat-role messages, so the JSON-only reply contract and
  the card budget are unchanged for every provider. Only the last 4 turns are sent: enough for
  follow-ups, small next to the cards. A turn is saved only after a validated answer. Threads are
  per run, not per paper across runs, because the cards being asked about belong to a run. Ask
  still uses `reports.max_input_chars` for its card budget; a separate setting was not added.
- **Verification:** Repository: threads per run and per paper, oldest first, cites and notes kept,
  clearing one thread leaves the others, deleting the run deletes its threads. Prompt: no history
  block on a first question, only the latest 4 turns on a follow-up, a message per error category.
  Server: thread routes with and without `?paper=`, the 502 body, and `LocalDesk.ask` passing the
  earlier turns (with a stubbed model) and not storing a failed turn. Browser against a copy of the
  cloud-run library with a stubbed model: follow-ups saw 1 and 2 earlier turns, a timeout showed
  the reachability message with a working setup link and was not counted, a new tab showed the
  stored thread, the paper thread stayed apart from the week's, and "Start over" emptied the
  thread across a reload; no page errors. `ruff format --check`, `ruff check`, `mypy` clean;
  `uv run pytest -q` → 605 passed, 3 deselected, coverage 92.43%.
- **Known issues:** Ask still answers only runs on the shelf (the newest 12 per topic); a run
  opened from the Library beyond that cannot be asked about yet.
- **Next step:** Roadmap M8 — `F48`: ask across weeks, answering from the topic's stored
  syntheses as well as this run's cards.

## 2026-10-28 — Search the library (complete)

- **Feature/branch:** `F46-library-search`, off `main` at `6ce9ff8`.
- **Status:** Complete; merged into `main`. Roadmap M7, second and last item.
- **Summary:** The Library page has a search box: "Search titles, authors, methods, datasets".
  A paper matches when every typed word appears, ignoring case, in its title, venue or abstract,
  one of its authors, or any stored analysis of it (problem, contribution, method, datasets,
  benchmarks, results, claims, …). Search combines with the All/Unread/Saved and topic filters and
  pages like the rest of the library. `GET /api/library` takes `q` (up to 200 characters).
- **Files affected:** `src/research_agent/storage/library.py` (`page(..., search=...)`,
  `_MATCHES_WORD`, `_escape_like`), `src/research_agent/desk/server.py` (`LibraryQuery.q`),
  `web/js/desk.js`, tests in `tests/unit/test_storage_library.py`, `test_desk_server.py`,
  `test_reading_desk.py`.
- **Decisions:** Plain `LIKE` scans rather than an FTS5 index: instant at one reader's library size
  and nothing to keep in sync. Authors are matched through `json_each`, because `authors_json`
  stores non-ASCII characters escaped (`"Jos\\u00e9"`) and a plain `LIKE` would never find "José".
  A typed `%` or `_` is escaped, so it is found literally. Typing is debounced by 300 ms, and the
  redraw restores focus and the caret so no keystroke is lost.
- **Verification:** Repository: title (any case), accented authors ("josé", "Núñez"), venue,
  abstract, a dataset that appears only in the analysis, every word required, `%`/`_` literal,
  a blank search matching everything, and totals. Browser with the seeded 30-paper library:
  typing "week 13" one character at a time kept every keystroke and focus in the box and showed the
  3 matching papers; adding the author kept them; a nonsense search said "No papers match.";
  clearing restored 30; no page errors. `ruff format --check`, `ruff check`, `mypy` clean;
  `uv run pytest -q` → 598 passed, 3 deselected, coverage 92.16%.
- **Known issues:** SQLite's `LIKE` folds case for ASCII letters only, so "ÉCOLE" does not match
  "école".
- **Next step:** Roadmap M8 — `F47`: Ask keeps the conversation (follow-up questions see earlier
  turns), saves threads, and says what failed when the model does.

## 2026-10-28 — Library: every kept paper across topics and runs (complete)

- **Feature/branch:** `F45-library-view`, off `main` at `950ec6b`.
- **Status:** Complete; merged into `main`. Roadmap M7, first item.
- **Summary:** The desk only ever showed the 12 most recent runs per topic, one run at a time. A
  new Library page (`#/library`, in the nav) lists every paper ever kept, across all topics and
  runs, newest run first — each paper once, under the latest run that kept it — with All / Unread /
  Saved filters, a topic filter, and 25 per page with Previous/Next. Opening a paper from a run
  older than the shelf's window fetches that run (`GET /api/runs/<id>`, same shape as the shelf)
  so its full card works: notes, votes, PDF, Ask.
- **Files affected:** `src/research_agent/storage/library.py` (new: `SqliteLibraryRepository.page`
  with a `ROW_NUMBER() OVER (PARTITION BY paper ORDER BY run start DESC)` query, filters and a
  total), `src/research_agent/desk/shelf.py` (`build_run`), `src/research_agent/desk/server.py`
  (`LibraryQuery` validation — `show` all/unread/saved, `offset ≥ 0`, `1 ≤ limit ≤ 100`;
  `GET /api/library`, `GET /api/runs/<id>`), `web/js/desk.js` (`viewLibrary`, `loadLibrary`,
  `openLibraryPaper`, `keepOlderRuns`), `web/css/desk.css`, tests in
  `tests/unit/test_storage_library.py` (new), `test_desk_server.py`, `test_reading_desk.py`.
- **Decisions:**
  - Runs fetched for the library are kept in `state.olderRuns` and re-attached after every shelf
    reload; otherwise F31's polling would replace the shelf and the open paper would read "Not in
    this run".
  - The library reloads whenever it is opened, so reading changes made elsewhere show at once.
  - The header's "New topic" link was removed: the seventh nav link pushed the nav onto two rows at
    every desktop width (measured: the nav box is capped at 457 px, the links need 510 px), and the
    link duplicated the New topic button on the Topics page, the welcome page and the setup page.
    The nav now fits on one row from 1080 px up with 34–54 px to spare.
- **Verification:** Repository: a paper kept in two runs appears once under the newer run, a
  paper only ever dropped is absent, saved/unread/topic filters, paging totals. `LocalDesk.run`
  and `.library` against a real database; routes 200/404/400. Browser with a seeded library of 14
  runs (two beyond the shelf's 12) and 30 kept papers: "Showing 1–25 of 30", Next → "26–30 of 30",
  opening a week-0 paper (not on the shelf) showed its card, which survived a shelf reload; the
  Unread filter then counted 29; header one row at 1600/1280/1100/1080/1000 px; no page errors.
  `ruff format --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 596 passed,
  3 deselected, coverage 92.15%.
- **Next step:** Roadmap M7 — `F46`: search the library by title, author, venue, method or
  dataset text.

## 2026-10-28 — Notify when a run finishes (complete)

- **Feature/branch:** `F44-finish-notification`, off `main` at `03dbd1d`.
- **Status:** Complete; merged into `main`. Roadmap M6, fourth and last item.
- **Summary:** A run takes tens of minutes and the reader goes elsewhere. The desk now uses the
  browser's Notification API: pressing Run now or creating a topic asks for permission once (from
  that click, never unprompted), and when F31's polling sees a run finish while the desk tab is in
  the background, a system notification says "<topic> finished: <status>." With the tab visible
  the banner already says so, so nothing extra appears; with permission declined, nothing changes.
- **Files affected:** `web/js/desk.js` (`askToNotify`, `notifyFinished`), `tests/unit/test_reading_desk.py`.
- **Decisions:** Browser notifications rather than an OS-specific helper (`osascript`) or email:
  runs are started from the desk, it works on macOS, Windows and Linux, needs no backend or
  dependency, and `127.0.0.1` counts as a secure origin. Email was out of scope unless asked
  (ponytail review). A CLI `run` started from a terminal does not notify; the terminal shows it.
- **Verification:** Browser with a stand-in `Notification` installed before the page loads and the
  harness flipping the run's status in SQLite: the first Run now requested permission once; with
  permission granted and the tab hidden, finishing the run produced one notification ("Existing
  topic finished: Degraded."); with the tab visible, none. `ruff format --check`, `ruff check`
  clean; `uv run pytest -q` → 593 passed, 3 deselected, coverage 91.98%.
- **Not verified:** a real OS notification popping up (headless Chromium has no notification
  centre); on the development Mac the browser shows its own permission prompt on first Run now.
- **Next step:** Roadmap M7 — `F45`: a library view across all runs and topics, with paging
  (lifts the 12-run cap on what the desk shows).

## 2026-10-28 — Library backup and restore (complete)

- **Feature/branch:** `F43-backup-restore`, off `main` at `b451c76`.
- **Status:** Complete; merged into `main`. Roadmap M6, third item.
- **Summary:** There was no way to back up or move the library. New:
  - `research-agent backup [--output FILE]` writes one zip: a manifest (`backup.json`: kind, app
    version, time, the library's folder), a consistent copy of `research_agent.db` made with
    SQLite's online backup API, and every file under `topics/` (PDFs, parsed text, analyses,
    reports, manifests). Locks are not included.
  - `research-agent restore FILE [--yes]` checks the whole archive first — a zip, a Research Agent
    manifest, the database present, and every member either the manifest, the database, or under
    `topics/` with no absolute path or `..` — then extracts into a staging folder beside the
    library and swaps it in. An existing library needs `--yes` and is renamed to
    `<folder>.before-restore-<UTC time>`, never deleted.
  - Both refuse while a run is in progress (a live lock in `locks/`), since a run writes into the
    library for minutes.
- **Bug avoided on the way:** the library records absolute file paths (`paper_files.path`), so a
  library restored to a different folder or machine would have pointed Open PDF and the parse cache
  at the old location. Restore now rewrites paths under the backup's recorded folder to the new
  one, in the staged copy, before the swap; paths outside the library are left as they are.
- **Files affected:** `src/research_agent/operations/backup.py` (new), `src/research_agent/cli.py`
  (`backup`, `restore`), `README.md`, `tests/unit/test_operations_backup.py` (new),
  `tests/integration/test_backup_cli.py` (new).
- **Verification:** Round trip into an empty folder (topics restored, files byte-identical, no
  manifest or locks extracted); restore over a library moves it aside intact; five untrustworthy
  archives (wrong kind, no manifest, `../`, absolute path, outside `topics/`) refused with nothing
  written; a non-zip refused; both commands refused under a held lock; no library → refused;
  restore elsewhere repoints recorded paths and leaves outside paths alone; CLI backup → restore
  refused without `--yes` → replaced with `--yes`. Real data: backed up the cloud-run library
  (14.0 MB), restored it elsewhere — identical row counts across 7 tables and all 10 artifact files
  byte-identical — and the real desk on the restored copy served a PDF via Open PDF (HTTP 200,
  2.3 MB, `%PDF-`). `ruff format --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 592
  passed, 3 deselected, coverage 91.98%.
- **Known issues:** Backups include PDFs, so they grow with the library (about 7 MB per deep-read
  paper here). The desk has no backup button; the CLI is enough for one user.
- **Next step:** Roadmap M6 — `F44`: notify when a run finishes (a macOS notification; email only
  if the user asks).

## 2026-10-28 — Citation export: BibTeX and RIS (complete)

- **Feature/branch:** `F42-citation-export`, off `main` at `d4973e0`.
- **Status:** Complete; merged into `main`. Roadmap M6, second item.
- **Summary:** Papers could not leave the desk for a reference manager. The Papers page now offers
  "Export these papers for Zotero or Mendeley: BibTeX · RIS" (the run's kept papers) and, when any
  paper is saved, "Your saved papers: BibTeX · RIS" (every saved paper in the library).
  `research_agent/exports/citations.py` holds two pure functions: `to_bibtex` (an `@article` when
  the paper has a venue, otherwise `@misc` with `eprint`/`archiveprefix` for arXiv; title in double
  braces to keep its capitalisation; special characters escaped; deterministic ASCII keys
  `<surname><year><first long word>` with a/b/… suffixes on collisions) and `to_ris` (`JOUR` or
  `GEN`, one `AU` per author, `PY`/`DA`, `JO`, `DO`, `UR`, `ER`).
- **Files affected:** `src/research_agent/exports/` (new package), `src/research_agent/storage/reading.py`
  (`saved_ids`), `src/research_agent/desk/server.py` (`DeskBackend.citations`;
  `GET /api/runs/<id>/citations?format=bib|ris` and `GET /api/saved/citations?format=…`, with
  BibTeX/RIS content types and download names), `web/js/desk.js`, `web/css/desk.css`, tests in
  `tests/unit/test_exports_citations.py` (new), `test_desk_server.py`, `test_storage_reading.py`,
  `test_reading_desk.py`.
- **Decisions:** No new dependency: the formats are simple enough to write by hand, and the tests
  pin the exact output. The saved-papers link shows no count, because the shelf holds only recent
  runs while the export covers every saved paper.
- **Verification:** Exact BibTeX for an article and an arXiv preprint; ASCII-folded, unique keys
  for colliding authors; `& % { } _` escaped and braces balanced; RIS field order and terminators
  with a source-URL fallback; `saved_ids`; `LocalDesk.citations` exports only kept papers for a run
  and only saved papers otherwise; route formats, headers, 400 for an unknown format, 404 for an
  unknown run. Browser on a copy of the real cloud-run library: all four links downloaded files
  named `embodied_spatial_intelligence_2026-10-27_papers.{bib,ris}` and `saved_papers.{bib,ris}`,
  which independent parsers (`bibtexparser` 1.4.3, `rispy` 0.9.0, installed only in the session
  scratchpad) read back completely — entry types, keys, arXiv ids, and all 14 and 15 authors.
  `ruff format --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 579 passed,
  3 deselected, coverage 92.03%.
- **Next step:** Roadmap M6 — `F43`: library backup and restore (`research-agent backup` /
  `restore`: the database plus artifacts).

## 2026-10-28 — Download or print the weekly report from the desk (complete)

- **Feature/branch:** `F41-report-download`, off `main` at `ef3649c`.
- **Status:** Complete; merged into `main`. Roadmap M6, first item.
- **Summary:** The Markdown report existed only on disk (`report latest` printed its path). The
  Report page now has "Download Markdown" (when a report file exists) and "Print or save as PDF".
  `GET /api/runs/<id>/report` serves the run's report as `text/markdown` with a download name of
  `<topic_id>_<YYYY-MM-DD>_weekly_report.md`. A print stylesheet hides the header, footer,
  banner, buttons and status stamps, prints black on white with page margins, and keeps findings
  from splitting across pages — so the browser's own Save as PDF produces the report alone, with no
  PDF dependency added.
- **Files affected:** `src/research_agent/desk/shelf.py` (`run_report`; runs carry `hasReport`),
  `src/research_agent/desk/server.py` (`DeskBackend.report`, route; `_bytes` takes extra headers),
  `web/js/desk.js`, `web/css/desk.css`, tests.
- **Decisions:** The report is located the way the shelf already finds a run's period (synthesis
  period, else run dates) and `report_filename`, so there is one source of truth. The download
  name is safe to put in a header: topic ids are `[a-z0-9_]` and the file name is fixed-format.
  Reports remain one per topic per period end (by design in `reports/naming.py`), so two runs
  ending on the same day share — and the later one overwrites — that file.
- **Verification:** `run_report` against real repositories and store (missing report, unknown run,
  found report with its download name); route headers and body, 404 when absent. Browser on the
  real cloud-run library: both buttons shown; the download saved
  `embodied_spatial_intelligence_2026-10-27_weekly_report.md` (2,599 words, starting with the
  report title); the print button called `window.print`; under print media the header, footer and
  buttons are hidden; Chromium's print-to-PDF produced a clean 206 KB report (first page checked
  visually). `ruff format --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 573 passed,
  3 deselected, coverage 91.83%.
- **Next step:** Roadmap M6 — `F42`: citation export (BibTeX, RIS) per run and for saved papers.

## 2026-10-28 — Treat browser disconnects as normal in the desk server (complete)

- **Feature/branch:** `FIX21-quiet-client-disconnects`, off `main` at `04a1624`.
- **Status:** Complete; merged into `main`.
- **Summary:** Found while testing F40: when the browser drops a connection while the desk is
  still writing a reply (a fast reload, a closed tab), `BaseHTTPRequestHandler` let a
  `BrokenPipeError` escape and `socketserver` printed a full traceback in the desk's terminal —
  harmless, but it reads like a crash. `DeskHandler._bytes` (every response goes through it) now
  treats `BrokenPipeError`/`ConnectionResetError` while sending as the client leaving: the
  connection is marked closed and a debug-level line is logged. Any other error still surfaces.
- **Files affected:** `src/research_agent/desk/server.py`, `tests/unit/test_desk_server.py`.
- **Verification:** New test writes a reply into a connection that raises `BrokenPipeError`: no
  exception, connection marked closed; it fails without the fix. Not reproduced live (whether the
  kernel buffer or the peer reset wins is a race), so the unit test is the regression guard.
  `ruff format --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 571 passed,
  3 deselected, coverage 91.85%.
- **Next step:** Roadmap M6 — `F41`: download the weekly report from the desk (Markdown, plus a
  print stylesheet for PDF).

## 2026-10-28 — Relevance feedback steers screening (complete)

- **Feature/branch:** `F40-relevance-feedback`, off `main` at `6480cf3`.
- **Status:** Complete; merged into `main`. Roadmap M5, fourth item.
- **Summary:** Screening repeated the same misjudgements every week (the cloud run dropped
  on-topic humanoid and locomotion papers with nothing the reader could do). The reader can now
  vote "👍 Relevant" or "👎 Not relevant" on any paper — on its page, and on every row of the
  Screened papers list, including dropped ones. Votes are per topic. The next run's screening
  prompt includes the topic's newest 5 relevant and 5 not-relevant titles as guidance. Prompt
  context only — nothing is trained, per AGENTS.md's guardrails.
- **Files affected:** `src/research_agent/domain/feedback.py` (new: `Vote`,
  `FeedbackExamples`), `src/research_agent/storage/feedback.py` (new: `FeedbackRepository`,
  `SqliteFeedbackRepository`), `src/research_agent/storage/database.py` (migration:
  `relevance_feedback` keyed by topic and paper, cascading with both),
  `src/research_agent/screening/prompts.py` (`screening.v2`; `render(..., examples)` adds the
  guidance block only when there are votes; titles cut at 200 chars),
  `src/research_agent/screening/service.py` (`screen_many(..., examples)`; provenance records
  `feedback_examples`), `src/research_agent/workflow/services.py` (`FeedbackReader` protocol,
  optional `feedback` service), `src/research_agent/workflow/nodes.py` (classify loads examples),
  `src/research_agent/operations/wiring.py`, `src/research_agent/desk/shelf.py` (cards and
  screened rows carry `vote`), `src/research_agent/desk/server.py`
  (`PUT /api/topics/<topic>/feedback/<paper>` with vote 1/-1/0; 404 for an unknown topic or
  paper), `web/js/desk.js`, `web/css/desk.css`, and tests.
- **Decisions:** `workflow/services.py` declares its own one-method `FeedbackReader` protocol
  (the `QueryPlanWriter` precedent) instead of importing a storage module, so the portability
  boundary test stays as strict as it was. Pressing an active vote again clears it. With no votes
  the screening prompt is byte-for-byte what it was before (tested).
- **Verification:** Repository (set, change, clear, per-topic independence; examples newest first
  and bounded); screener (no votes → prompt unchanged; votes → guidance lines; provenance counts);
  a full mocked graph run where every screening request sent to the model carried the vote;
  desk route 200/400/404 and `LocalDesk.set_vote` against a real database; votes on shelf cards
  and screened rows. Browser on a copy of the real cloud-run library: 👍 on a dropped paper and 👎
  on a kept one both persisted across reloads, a second press cleared a vote, and the database
  then held exactly the examples the next run would use. `ruff format --check`, `ruff check`,
  `mypy` clean; `uv run pytest -q` → 570 passed, 3 deselected, coverage 91.84%.
- **Not verified:** a live run measuring how much the votes change a real model's decisions.
- **Known issues:** Found while testing: when the browser drops a connection mid-response (a fast
  reload), the desk prints a `BrokenPipeError` traceback. Harmless, but alarming; fixing next.
- **Next step:** `FIX21` — treat client disconnects as normal in the desk server.

## 2026-10-28 — Reading state: read/unread, saved, notes (complete)

- **Feature/branch:** `F39-reading-state`, off `main` at `491c427`.
- **Status:** Complete; merged into `main`. Roadmap M5, third item.
- **Summary:** The desk had no memory of what the reader had done. Each paper now has a reading
  state — read, saved, and a free-text note — kept per paper (not per run): a paper read once
  stays read when it reappears in a later week or another topic, and clearing a run never loses a
  note. In the desk: opening a paper marks it read (once per session, so "Mark unread" sticks);
  the paper page has "☆ Save"/"★ Saved" and "Mark read"/"Mark unread" buttons and a "Your notes"
  box with Save note; the Papers list shows a dot on unread papers and ★ on saved ones, with
  Unread and Saved filters.
- **Files affected:** `src/research_agent/storage/database.py` (migration: `reading_state`
  keyed by `paper_id`, cascading with `papers`), `src/research_agent/storage/reading.py` (new:
  `ReadingState`, `ReadingRepository`, `SqliteReadingRepository`; notes capped at 20,000 chars),
  `src/research_agent/desk/shelf.py` (cards carry `reading`, loaded in one query per run;
  `build_shelf(..., reading=...)` is optional), `src/research_agent/desk/server.py`
  (`PUT /api/papers/<id>/reading`, partial update merged with the stored state; 400 for unknown
  fields or an over-long note, 404 for an unknown paper), `web/js/desk.js`, `web/css/desk.css`,
  tests in `tests/unit/test_storage_reading.py` (new), `test_desk_server.py`,
  `test_desk_shelf.py`, `test_reading_desk.py`.
- **Decisions:** An unsaved note is kept as a draft in page state on every keystroke, so F31's
  progress redraws and navigation never lose it. A change updates every copy of the paper on the
  shelf (one paper can sit in several runs). No separate "reading list" page yet: the Saved filter
  covers it within a run; a library-wide view is roadmap F45.
- **Verification:** Repository round trip and upsert; note bound; `LocalDesk.update_reading`
  merges partial changes and rejects an unknown paper; route 200/400/404; a shelf card carries the
  stored state. Browser on a copy of the real cloud-run library: Unread 2 → opening a paper →
  Unread 1; Save → ★ in the list and Saved 1; a note draft survived navigating away and back;
  "Note saved."; Mark unread stayed unread across a redraw; after a full reload the note and ★
  persisted; no page errors. `ruff format --check`, `ruff check`, `mypy` clean;
  `uv run pytest -q` → 563 passed, 3 deselected, coverage 91.74%.
- **Next step:** Roadmap M5 — `F40`: relevance feedback (thumbs up/down) stored and fed into the
  screening prompt as examples.

## 2026-10-28 — Complete the paper card: setup, related work, open the PDF (complete)

- **Feature/branch:** `F38-complete-paper-card`, off `main` at `3d62708`.
- **Status:** Complete; merged into `main`. Roadmap M5, second item.
- **Summary:** Each analysis stores `experimental_setup` and `related_work`, and each acquired
  paper has a PDF in the library, but the desk showed neither. The paper page now has
  "Experimental setup" (after Method) and "Related work" (after Limitations) sections, and an
  "Open PDF" link beside DOI/arXiv when a PDF is stored. `GET /api/papers/<id>/pdf` serves it as
  `application/pdf`; the shelf card carries `setup`, `relatedWork` and `hasPdf`.
- **Files affected:** `src/research_agent/desk/shelf.py`, `src/research_agent/desk/server.py`
  (`DeskBackend.pdf_path`, `LocalDesk.pdf_path`, route), `web/js/desk.js`,
  `tests/unit/test_desk_server.py`, `tests/unit/test_reading_desk.py`.
- **Decisions:** The route serves a file only when the library recorded it as that paper's PDF
  *and* it resolves inside `data_directory`, ends in `.pdf` and exists — so a stale or tampered
  `paper_files` row cannot be used to read another file; every other case is a 404. The route is
  a plain GET behind FIX15's Host check (opening a link in a new tab sends no `Origin`).
- **Verification:** `LocalDesk.pdf_path` against a real database: a PDF inside the library is
  served; one outside the library, a non-`.pdf` file and a missing file all return none, as does
  an unknown paper. Route test: 200 with `application/pdf` and the file's bytes, 404 otherwise.
  Browser on the real cloud-run library: both papers show Experimental setup and Related work;
  Open PDF returned the stored files (2.2 MB and 12.4 MB, `application/pdf`, starting `%PDF-`);
  no page errors. `ruff format --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 559
  passed, 3 deselected, coverage 91.66%.
- **Next step:** Roadmap M5 — `F39`: reading state per paper (read/unread, saved, notes).

## 2026-10-28 — Keep the desk header on one line with long topic names (complete)

- **Feature/branch:** `FIX20-header-one-line`, off `main` at `3a4a2c7`.
- **Status:** Complete; merged into `main`.
- **Summary:** Found while verifying F37 on the real cloud-run library: with a long topic name
  ("Embodied Spatial Intelligence") and the run switcher shown, the header nav wrapped "Topics"
  onto a second line at 1280 px (header 116 px tall instead of 78) — a regression from F28's extra
  nav item that short test names hid. The switchers now cap at 11rem with an ellipsis (the full
  name shows when the select opens), and the header's stacked layout starts below 1080 px instead
  of 860 px; the page body keeps its 860 px breakpoint.
- **Files affected:** `web/css/desk.css` only (the three header rules moved, not copied, into a
  new `max-width: 1080px` block).
- **Decisions:** Measured the candidates in Chromium across widths before choosing. `flex-wrap:
  nowrap` on the nav was rejected: it kept one row by sliding the links under the switchers (up to
  193 px of overlap at 870–1000 px). A narrower switcher alone fixed ≥1100 px but still wrapped
  between 860 and 1100 px.
- **Verification:** Chromium on the real library at 1440, 1280, 1100, 1080, 1000, 900 and 390 px:
  one nav row with no nav/switcher overlap at every width (stacked header at ≤1080 px; two nav
  rows only at 390 px, as before), no horizontal page overflow; screenshots checked at 1280 and
  1000 px. `ruff format --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 557 passed,
  3 deselected, coverage 91.62%.
- **Next step:** Roadmap M5 — `F38`: show `experimental_setup` and `related_work` on paper cards
  and open the stored PDF from the desk.

## 2026-10-28 — Show why each paper was kept or dropped (complete)

- **Feature/branch:** `F37-why-papers-were-kept`, off `main` at `2832c61`.
- **Status:** Complete; merged into `main`. Roadmap M5, first item. (F34, a settings screen, was
  deferred by the user to the packaging stage, M12.)
- **Summary:** The cloud run kept 2 of 87 papers and the desk could not say why. The screener's
  verdict (relevance score, level, one-line `reason_short`) and the selection decision (rank and
  reason) were stored but never shown. Now:
  - Each kept paper's card carries `screening` (`score`, `level`, `reason`, `decision`, `rank`),
    and the paper page shows "Why it's on the shelf: Kept for a deep read · relevance 0.88" with
    the screener's reason.
  - `GET /api/runs/<id>/screened` (`desk/shelf.py::screened_papers`) lists every screened paper,
    kept or dropped, in selection-rank order. The Papers page links to a new Screened papers page
    (`#/screened`) with All / Kept / Dropped filters; each row shows the score, a plain-language
    decision ("Dropped: the screener judged it off-topic", "Skipped: already read in an earlier
    run", …) and the reason. Kept papers link to their card, dropped ones to DOI/arXiv in a new tab.
- **Files affected:** `src/research_agent/desk/shelf.py`, `src/research_agent/desk/server.py`
  (`DeskBackend.screened`, route), `web/js/desk.js`, `web/css/desk.css`,
  `tests/unit/test_desk_shelf.py`, `tests/unit/test_desk_server.py`,
  `tests/unit/test_reading_desk.py`.
- **Decisions:** The full list is fetched on demand rather than carried on the shelf: a run screens
  up to hundreds of papers, and the shelf is polled every 5 s while a run is in flight (F31).
  Earlier in this session the cloud run's reasons looked empty; that was a wrong key in an ad-hoc
  query — all 87 screened papers had a reason.
- **Verification:** `screened_papers` test with one kept and one dropped paper (order, decisions,
  reasons) and the shelf card's `screening` block; route test against the fake backend. Browser
  on the real cloud-run library served by the real `research-agent desk`: Papers shows "See all
  87 screened, including the dropped ones"; a kept paper shows "Kept for a deep read · relevance
  0.88" and its reason; the screened page lists 87 by relevance, Dropped shows 85 and Kept 2,
  dropped titles open arXiv in a new tab; no page errors. `ruff format --check`, `ruff check`,
  `mypy` clean; `uv run pytest -q` → 557 passed, 3 deselected, coverage 91.62%.
- **Known issues:** Found while checking: with a long topic name and the run switcher shown, the
  header nav wraps "Topics" onto a second line at 1280 px (regression from F28's extra nav item).
  Fixing next as its own item.
- **Next step:** `FIX20` — keep the header on one line with long topic names.

## 2026-10-27 — Runs are manual: drop schedule wording from the desk (complete)

- **Feature/branch:** `FIX19-manual-runs-only`, off `main` at `a5d6253`.
- **Status:** Complete; merged into `main`.
- **User decision:** No weekly schedule is installed; a run happens only when the user presses
  Run now (or creates a topic). Roadmap M4 (F35 schedule install/status, F36 desk next-run
  display) is dropped. The PRD's "set a weekly run schedule" stays available but unused: topics
  keep their stored `scheduling` setting and `research-agent schedule generate` still works.
- **Summary:** The desk no longer suggests runs happen on their own: the "Run day" select is gone
  from the edit and new-topic forms, and the Topics page note now reads "Runs start only when you
  press Run now. Paused topics can't be run until enabled." `schedule generate` left the README's
  everyday commands.
- **Files affected:** `web/js/desk.js` (`DAYS` and the run-day select removed;
  `scheduleFromData` → `runSettingsFromData`, which no longer sends `scheduling`), `README.md`.
- **Decisions:** `PUT /api/topics/<id>` replaces the whole topic, so the edit form now sends the
  topic's stored `scheduling` back unchanged; dropping the field alone would have silently reset
  every edited topic's day to Sunday. New topics take the model default. The server still accepts
  `scheduling` in both routes.
- **Verification:** Browser with a topic stored on Wednesday: no run-day field on the edit or
  new-topic form, the new Topics note shown, saving an edit (lookback 6) kept `day: wednesday`,
  topic creation still succeeds, no page errors. `ruff format --check`, `ruff check`, `mypy`
  clean; `uv run pytest -q` → 555 passed, 3 deselected, coverage 91.43%.
- **Next step:** `F34` settings screen — scope (read-only vs editable) awaiting the user's
  choice; otherwise continue with roadmap M5 (`F37`, why papers were kept or dropped).

## 2026-10-27 — First-run setup page in the desk (complete)

- **Feature/branch:** `F33-setup-page`, off `main` at `05b3ac2`.
- **Status:** Complete; merged into `main`. Roadmap M3, second item.
- **Summary:** A new library opened on a bare "No topic" message, with no hint that a model server
  must be running or which keys help. Now:
  - With no topics, the desk opens on a welcome page with two steps: "1. Check setup" and
    "2. Create a topic".
  - `#/setup` ("Setup check", linked from the footer on every page) calls F32's `/api/health` and
    lists each check with an OK / Warning / Problem badge, its detail and its fix, under a summary
    line ("1 problem to fix before a run." / "Ready to run, with N warnings." / "All set …"). It
    explains the wait while checking (up to a minute), offers "Check again", and offers "Create
    your first topic" while the library has none.
- **Files affected:** `web/js/desk.js` (`viewSetup`, `checkHealth`, `healthSummary`, welcome
  state, footer link), `web/css/desk.css` (health list and badges; link-styled `.primary` reset),
  `tests/unit/test_reading_desk.py`, `README.md`.
- **Decisions:** Setup lives in the footer rather than the main nav, which stays about reading.
  Results are kept for the session and re-run only on "Check again", since a full check can take
  up to a minute. The page has no inputs, so redrawing it when results arrive is safe.
- **Verification:** Browser against the real `LocalDesk.health()` and real network in the cloud
  container (only keyword suggestion and the pipeline thread stubbed): welcome page with both
  steps and the footer link; pending message with Check again disabled; then "1 problem to fix
  before a run." with Library folder OK, Local model Problem (fix names the server URL), NIM /
  OpenAlex / Semantic Scholar Warning, arXiv OK; "Create your first topic" offered; Check again
  re-runs; no page errors; no horizontal overflow at 1280 px or 390 px. Fixed before commit: the
  link-styled primary button rendered underlined. `ruff format --check`, `ruff check`, `mypy`
  clean; `uv run pytest -q` → 555 passed, 3 deselected, coverage 91.43%.
- **Next step:** `F34` — settings screen (roadmap M3, third item). Per the ponytail review noted
  earlier, scope it to a read-only view of the effective settings with where to change each one,
  unless the user asks for editing.

## 2026-10-27 — First end-to-end cloud run since FIX11–F31 (recorded)

- **Feature/branch:** `DOC3-record-cloud-run` (records results only; no code).
- **Status:** Run finished `degraded` (by design: two sources rate-limited), with a full report.
- **Setup:** Cloud container, isolated data directory and settings in the session scratchpad
  (repository config untouched). Model: OpenRouter `nvidia/nemotron-3.5-super-vl:free` in the
  local-provider slot, paced at 0.3 requests/s for the free tier; NIM unconfigured. Keys came from
  the environment's network secrets (proxy-injected `Authorization` for openrouter.ai and
  `x-api-key` for api.semanticscholar.org), never stored in the app. Paid `qwen/qwen3-14b` was
  refused with HTTP 402 (OpenRouter account credit exhausted before this session: $20.21 of $20,
  $0 spent today); free Gemma 4 models were rate-limited upstream. Started from the real
  `research-agent desk` via `POST /api/topics/embodied_spatial_intelligence/run` (F28 path).
- **Outcome:** 34.1 min. 87 candidates (arXiv only) → 87 screened → 2 selected (1 deep read,
  1 summary) → 2 PDFs downloaded → 2 parsed by real Docling (models downloaded on first parse) →
  2 analyses → synthesis (2 developments) → 5 gaps and 5 ideas, each citing paper ids → 2,596-word
  Markdown report with every PRD section and run provenance. 10 recorded errors, all
  `RATE_LIMIT`: OpenAlex and Semantic Scholar on each of the 5 queries after 4 attempts.
- **Findings:**
  - Run row appeared 84 s after Run now while Docling loaded → fixed in FIX18.
  - No progress visible during a 15-minute discovery → fixed in F30/F31.
  - OpenAlex 429s every call from the shared cloud IP without a contact email; Semantic Scholar
    429s even with the key (new keys allow ~1 request/s, shared IP). Expect better on the
    development Mac; `research-agent doctor` (F32) now reports both with the fix to apply.
  - Screening kept 2 of 87: the default topic has no keywords, so the model read "Embodied Spatial
    Intelligence" narrowly (humanoid loco-manipulation and world-action-model papers scored
    0.2–0.3 and were dropped). Add keywords to the topic (now editable in the desk, F28/F29).
  - Not covered: the Mac's local Qwen3-14B with thinking mode (quality and timing differ); a
    Mac run remains the user's deferred timing check.
- **Next step:** `F33` — first-run setup page using `/api/health`.

## 2026-10-27 — Health check: `research-agent doctor` and `/api/health` (complete)

- **Feature/branch:** `F32-health-check`, off `main` at `0fe37ec`.
- **Status:** Complete; merged into `main`. Roadmap M3, first item.
- **Summary:** A user learned that the local model server was down, NIM was unconfigured or a
  source was rate-limited only from a failed or degraded run. `operations/health.py::run_checks`
  now checks, in the order a run meets them: the library folder (writable via a probe file that
  is removed; warns below 2 GB free), the local model (one tiny prompt straight to the provider),
  NVIDIA NIM (warn when no key — optional by design; fail when a configured key does not answer),
  and each of OpenAlex, Semantic Scholar and arXiv (one search for one result, retries off). Each
  result is `ok`/`warn`/`fail` with a detail and a concrete fix (start the server at `<url>`, set
  `RESEARCH_AGENT_SOURCES__SEMANTIC_SCHOLAR_API_KEY`, set `..._OPENALEX_MAILTO`, …). Exposed as
  `research-agent doctor` (exit 1 on any fail) and `GET /api/health` (the F33 setup page will
  render it).
- **Files affected:** `src/research_agent/operations/health.py` (new),
  `src/research_agent/models/chat.py` (`base_url` property), `src/research_agent/cli.py`
  (`doctor`), `src/research_agent/desk/server.py` (`DeskBackend.health`, `/api/health`),
  `tests/unit/test_operations_health.py` (new), `tests/unit/test_desk_server.py`, `README.md`.
- **Decisions:** A source counts as `warn` when rate-limited (runs continue without it) and `fail`
  only when unreachable; any unexpected exception from an adapter becomes a finding, never a
  crash. Checks share one client with a 30 s timeout so a dead endpoint cannot hang them. Docling
  is not checked: its models download on the first parse (FIX18) and there is no cheap probe.
- **Verification:** Tests with a mocked network: a healthy setup reports ok/warn exactly as
  expected and removes its probe file; an unwritable folder and a refused model connection both
  fail with a fix instead of raising; the desk route returns the checks as JSON. Live in the cloud
  container: with default settings, `doctor` reported `fail Local model … Start the model server
  at http://localhost:8080/v1`, NIM `warn`, OpenAlex `warn` (429), Semantic Scholar and arXiv `ok`,
  exit 1; with the cloud-run settings the OpenRouter model answered in 873 ms, exit 0. `ruff format
  --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 554 passed, 3 deselected, coverage
  91.43%.
- **Next step:** `F33` — a first-run setup page in the desk that shows these checks with their
  fixes and leads to creating the first topic.

## 2026-10-27 — Live run progress in the desk (complete)

- **Feature/branch:** `F31-live-run-progress`, off `main` at `1a7b96d`.
- **Status:** Complete; merged into `main`. Roadmap M2, second and last item.
- **Summary:** The desk now shows every running run in a banner under the header ("Topic ·
  Screening papers · 12 min so far", an `aria-live` region), polls the shelf every 5 s while a run
  is running or was just started, and announces when a run ends ("… finished: Degraded.", with a
  dismiss button). Runs and This week show the live stage for a running run and "Stopped while
  analysing papers" for a failed one (F30's stored stage). Run now and topic creation wait for the
  new run to appear ("Starting the run…").
- **Files affected:** `web/js/desk.js` (`STAGE_LABEL`, `runProgress`, `runningRuns`,
  `bannerHtml`/`updateBanner`, `schedulePoll`/`poll`, `awaitRun`, `onFormPage`), `web/css/desk.css`,
  `tests/unit/test_reading_desk.py`.
- **Decisions:** Polling reuses `/api/shelf` (no new endpoint). A poll only redraws the banner
  unless a run started or finished; even then the edit and new-topic forms are never redrawn, so
  typing is never wiped. Waiting for a new run is keyed on the topic's newest run id at the time of
  the request, so a run that starts and ends between two polls still clears the wait (caught in
  testing: keying on "any run running" left a stale "Starting the run…" for five minutes). The
  wait gives up after five minutes. No cancel button: stopping the pipeline thread cleanly is its
  own piece of work.
- **Verification:** Browser (real `LocalDesk`, server and page; a helper script changed the run's
  stage and status in SQLite mid-test): banner showed "Starting", then "Screening papers" after
  `mark_stage`; with unsaved text in the edit form, finishing the run showed "finished: Degraded"
  and the typed text survived; dismiss cleared it; a run failed during `analyze` showed "Stopped
  while analysing papers" on Runs; a harness opening the run row 7 s after Run now showed
  "Starting the run…" then live progress, and the Topics page redrew with Run now disabled; no
  page errors. `ruff format --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 552
  passed, 3 deselected, coverage 91.84%.
- **Known issues:** A run whose period starts and ends on the same day is labelled
  "27–27 Oct 2026" in the run switcher (pre-existing `formatPeriod` behaviour) — UI polish (F52).
- **Next step:** Record the cloud run's outcome; then roadmap M3 — `F32` health check
  (`research-agent doctor` and `/api/health`).

## 2026-10-27 — Record which stage a run is in (complete)

- **Feature/branch:** `F30-record-run-stage`, off `main` at `b1b5c34`.
- **Status:** Complete; merged into `main`. Roadmap M2, first item.
- **Summary:** A running run showed only "Running" for its whole length (the cloud run spent
  15 min in discovery with no outward sign). Each graph node now records itself as the run's
  stage, with the time it started, before it executes. The last stage stays after the run ends,
  so a failed run shows where it stopped. The shelf carries `stage`, `stageStartedAt` and
  `startedAt` per run for the desk (F31 renders and polls them).
- **Files affected:** `src/research_agent/storage/database.py` (migrations: `runs.stage`,
  `runs.stage_started_at`), `src/research_agent/domain/runs.py` (`RunRecord.stage`,
  `stage_started_at`), `src/research_agent/storage/runs.py` (`RunRepository.mark_stage`),
  `src/research_agent/workflow/graph.py` (`_tracked` wraps every node in `build_graph`),
  `src/research_agent/desk/shelf.py`, tests in `tests/unit/test_storage_runs.py`,
  `tests/unit/test_workflow_routes.py`, `tests/integration/test_workflow_graph.py`.
- **Decisions:** One wrapper in `build_graph` rather than a call in each of 13 nodes; it uses the
  `RunRepository` interface, so graph code stays free of SQL. `load_topic` opens the run and so
  records no stage itself; the run reads stage-less only until `plan_queries` starts. No separate
  status endpoint: the desk already fetches the shelf, and polling it is cheap for one user.
  Per-paper progress inside a long stage (e.g. "screening 120/250") and cancelling a run are not
  part of this item.
- **Verification:** Repository round trip (stage kept after a failed completion); wrapper marks a
  stage only once the run id exists; a full mocked run ends with stage `persist`. Migration tests
  pass on the extended list. `ruff format --check`, `ruff check`, `mypy` clean;
  `uv run pytest -q` → 551 passed, 3 deselected, coverage 91.84%.
- **Next step:** `F31` — the desk shows the live stage and elapsed time for a running run,
  polls the shelf while any run is running, and announces when it finishes.

## 2026-10-27 — Load Docling on the first parse, not when a run is wired (complete)

- **Feature/branch:** `FIX18-load-docling-on-first-parse`, off `main` at `9dc7766`.
- **Status:** Complete; merged into `main`.
- **Summary:** Found in the cloud run (see F29's entry): `DoclingParser()` built Docling's
  `DocumentConverter` in its constructor, and `build_services` constructs the parser before the
  workflow's first node opens the run row. Run now therefore showed nothing for 84 s in the cloud
  container while torch loaded, and every run paid that start-up even when no PDF was parsed. The
  converter is now built by `DoclingParser._ready_converter()` on the first `parse()` and reused.
- **Files affected:** `src/research_agent/documents/docling_parser.py`,
  `tests/unit/test_documents_docling_lazy.py` (new).
- **Decisions:** No lock: `ParsingService.parse_many` parses sequentially. A Docling load failure
  now happens inside `parse()`, where `ParsingService` already turns it into a recorded failure and
  the paper continues abstract-only — previously the same failure aborted the run before it
  opened. Ponytail note: after such a failure each later PDF retries the load; acceptable for a
  failure that should not happen, revisit only if it is seen.
- **Verification:** New unit test with a fake `docling.document_converter` (no construction on
  `DoclingParser()`, exactly one on first use) fails without the fix. With network access in the
  cloud container, the three `-m slow` Docling integration tests ran for the first time this
  session and passed against the real Docling stack (model download included): 3 passed in 77 s.
  `ruff format --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 549 passed,
  3 deselected, coverage 91.81%.
- **Known issues:** Run now still takes as long as the earlier stages (query planning, discovery)
  before the page shows progress; that is roadmap F30/F31.
- **Next step:** Record the cloud run's outcome when it finishes; then roadmap M2 — `F30` persist
  per-stage progress and expose run status.

## 2026-10-27 — New topic: editable keywords and advanced settings (complete)

- **Feature/branch:** `F29-new-topic-chips-and-settings`, off `main` at `b88e737`.
- **Status:** Complete; merged into `main`. Roadmap M1, third and last item.
- **Summary:** The new-topic "review" step showed the model's keywords as read-only chips and
  created every topic with default lookback, sources, limits and run day. Now the review step
  has removable keyword chips (×), an input that adds a keyword on Enter or "Add"
  (case-insensitive duplicates ignored), and a collapsible "Advanced settings" section with
  lookback, run day, sources and the four limits. `POST /api/topics` validates the body as a
  whole `TopicSettings`, exactly like F28's `PUT`, and answers a bad value with the same readable
  400 line. The shelf carries `defaults` (a `TopicSettings` dump without id/name) so the page
  never keeps its own copy of the defaults.
- **Files affected:** `src/research_agent/desk/server.py` (`TopicCreateRequest` removed;
  `DeskBackend.create_and_run(topic: TopicSettings)`), `src/research_agent/desk/shelf.py`,
  `web/js/desk.js` (`settingsFields()` shared by the edit and new-topic forms;
  `scheduleFromData()`; `keywordChips()`/`refreshChips()`/`addKeyword()`), `web/css/desk.css`,
  `tests/unit/test_desk_server.py`, `tests/unit/test_reading_desk.py`.
- **Decisions:** Adding or removing a chip re-renders only the chip list, so values typed under
  Advanced settings survive; on a failed create the entered settings are kept in state and the
  section stays open. Field ids are now generic (`topic-lookback`, `topic-day`, `limit-*`)
  because both forms share them; only one form is ever on the page. The success message now
  points to Runs: on a cold start the run row takes over a minute to appear (see the cloud-run
  finding below).
- **Verification:** Server tests: create with advanced settings stores them; invalid limits give
  `limits: max_deep_reads cannot exceed max_downloads`. Browser (real `LocalDesk`, server and
  page; only keyword suggestion and the pipeline thread stubbed): suggested chips shown, one
  removed, one added via Enter with focus kept, a duplicate ignored, advanced lookback 5 /
  Semantic Scholar off / deep reads 99 refused with the readable error while chips, lookback,
  checkbox and the open section all survived, then created with deep reads 5 and stored exactly
  as entered; the edit page shows the same values; no page errors. `ruff format --check`,
  `ruff check`, `mypy` clean; `uv run pytest -q` → 548 passed, 3 deselected, coverage 91.62%.
- **Finding from the in-progress cloud run (to fix next, separately):** `build_services`
  constructs `DoclingParser()` eagerly, which imports Docling's torch stack before the
  workflow's first node opens the run row. Measured in the cloud container: Run now at 20:26:38,
  run row visible at 20:28:02 (84 s of nothing on the page). It also costs every run the Docling
  start-up even when no PDF is parsed. Fix: construct the parser lazily on first parse.
- **Next step:** Finish and record the cloud pipeline run (OpenRouter, free
  `nvidia/nemotron-3.5-super-vl:free`, isolated data directory in the session scratchpad); then
  the lazy-Docling fix as the next `FIX` item; then roadmap M2 (F30 run progress).

## 2026-10-27 — Desk topics page: edit, pause, delete, run now (complete)

- **Feature/branch:** `F28-desk-topics-page`, off `main` at `677c68f`.
- **Status:** Complete; merged into `main`. Roadmap M1, second item.
- **Summary:** The desk could create topics but not manage them. New Topics page (`#/topics`,
  in the nav) lists every topic with its lookback, sources, run count and keywords, and offers
  Run now, Pause/Enable, Edit and Delete. `#/topics/<id>` is an edit form for every setting but
  the id (name, enabled, keywords one per line, lookback, run day, sources, the four limits).
  Server routes, all behind FIX15's Host/Origin check:
  - `PUT /api/topics/<id>` — body validated as a whole `TopicSettings` (unknown fields refused,
    limit ordering enforced); 400 carries one readable line such as
    `limits: max_deep_reads cannot exceed max_downloads`; 404 for an unknown topic.
  - `DELETE /api/topics/<id>` — deletes the topic and its runs; 409 while its run holds the lock.
  - `POST /api/topics/<id>/run` — starts the run on the existing background thread
    (`LocalDesk._start_run`, extracted from `create_and_run`); 409 when the topic is disabled or
    already has an open run, 404 when unknown.
  - The shelf now carries each topic's `settings` (the same shape `PUT` accepts).
- **Bug fixed on the way:** the server speaks HTTP/1.1 keep-alive, and a route that did not read
  its request body left those bytes in the socket, so the browser's next request on that
  connection was parsed as `{}GET /api/shelf` and failed with 501 — the page then kept a stale
  shelf. Routes that take no body now discard it (`_discard_body`, used by the run route and
  every DELETE), an oversized body that `_read_json` refuses now closes the connection, and the
  server sends `Connection: close` whenever it closes.
- **Files affected:** `src/research_agent/desk/server.py`, `src/research_agent/desk/shelf.py`,
  `web/js/desk.js`, `web/css/desk.css`, `tests/unit/test_desk_server.py`,
  `tests/unit/test_reading_desk.py`, `README.md`.
- **Decisions:** Keywords are edited one per line in a textarea (accessible, no new widget);
  editable chips stay with F29's new-topic flow. Delete still uses the native `confirm()`, which
  roadmap F51 replaces for every destructive action. Run now's button is disabled with a reason
  in its tooltip when the topic is paused or running. Native form validation catches empty and
  below-minimum numbers before the server does.
- **Verification:** HTTP tests for every new route and status code against the fake backend;
  `LocalDesk` tests against a real temporary database (update visible on the shelf, run refused
  when disabled, unknown or already open, delete refused under a held lock); a keep-alive test on
  one `http.client` connection that fails without the body-draining fix. Browser (Chromium, real
  `LocalDesk`, server and page; only the pipeline thread replaced by recording a running run):
  edit and save, server-side validation error shown on the form, pause disables Run now, Run now
  shows the run as Running and disables itself, delete with confirmation empties the list, no
  page errors; screenshots at 1280 px and 390 px with no horizontal overflow. `ruff format
  --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 547 passed, 3 deselected, coverage
  91.60%.
- **Known issues:** After Run now, the new run's row appears once the background thread opens it
  (about a second); the page does not poll yet — roadmap F30/F31 (live run progress).
- **Next step:** `F29` — new-topic flow with editable keyword chips and the advanced settings
  (lookback, sources, limits, run day) before creation.

## 2026-10-27 — Edit and delete topics from the CLI (complete)

- **Feature/branch:** `F27-topic-edit-delete`, off `main` at `fbfd81e`.
- **Status:** Complete; merged into `main`. Roadmap M1, first item.
- **Summary:** Topics could be added and enabled/disabled but never changed or removed, so a bad
  keyword or lookback meant living with it. New:
  - `TopicRepository.update(topic)` (replace all settings, keep id and `created_at`) and
    `TopicRepository.delete(topic_id)` (foreign keys cascade to the topic's runs and everything
    under them); both raise `TopicNotFoundError` for an unknown id.
  - `research-agent topic edit <id>` — only the options given change (name, lookback, keywords
    which replace the list, each source, each limit, schedule day); the merged result is
    validated as a whole, so limit ordering and "at least one source" still hold.
  - `research-agent topic delete <id>` — asks first (`--yes` skips), and refuses while a run of
    that topic holds its lock (reusing `run_lock`), since a live run would fail once its rows
    vanished. Files on disk are kept, matching FIX9's clear-runs decision.
- **Bug fixed on the way:** `bootstrap()` re-seeded from `config/topics.yaml` whenever the topics
  table was empty, so deleting the last topic would have revived the YAML topic on the next
  command or desk start. `_open_connection` now seeds only a brand-new library
  (`PRAGMA user_version` still 0 before migrating). `bootstrap()` itself is unchanged.
- **Files affected:** `src/research_agent/storage/topics.py`, `src/research_agent/cli.py`,
  `tests/unit/test_storage_topics.py`, `tests/integration/test_topic_cli.py`, `README.md`.
- **Decisions:** Editing the topic id is not supported (it keys every run, synthesis, gap, idea and
  artifact path); rename via a new topic if ever needed. No `--clear-keywords`; `--keyword`
  replaces the list. Validation errors print pydantic's message, as `topic add` already does.
- **Verification:** Repository tests for update and cascading delete; CLI tests for partial edit
  (checked against the stored topic), invalid limits, unknown topic, delete prompt declined,
  delete refused under a held lock, and a deleted last topic staying deleted. Mutation check:
  restoring "always bootstrap" fails `test_a_deleted_last_topic_stays_deleted`. Smoke run of the
  real binary on a temporary library: list → edit → invalid edit refused → delete declined →
  delete `--yes` → "No topics stored". `ruff format --check`, `ruff check`, `mypy` clean;
  `uv run pytest -q` → 543 passed, 3 deselected, coverage 91.72%.
- **Known issues:** A library whose first command ran with a missing or invalid
  `config/topics.yaml` is never seeded later; add topics with `topic add` or the desk.
- **Next step:** `F28` — desk topics page: list, enable/disable, edit, delete with confirmation,
  and a Run now button, on top of these repository methods.

## 2026-10-27 — Remove stale text and dead code (complete)

- **Feature/branch:** `FIX17-remove-stale-text-and-dead-code`, off `main` at `de09093`.
- **Status:** Complete; merged into `main`. This closes roadmap module M0 (stabilise).
- **Summary:**
  - `web/js/desk.js`: deleted `replyTo()` (about 50 lines of keyword-matched fake answers) and
    the `!state.live` branch in `ask()` that used it, plus the "can't reach" variant of the Ask
    page note. All were unreachable: a run only exists after `loadShelf()` sets
    `state.live = true`, and nothing sets it back. The header comment no longer claims sample
    data and "does not call NIM".
  - `README.md`: Python 3.12 (matches `pyproject.toml`; Docling's stubs need it), the real
    everyday commands instead of "the broader CLI will be exposed feature by feature", and no
    claim that opening `index.html` shows a sample week (FIX9 removed it).
- **Files affected:** `web/js/desk.js`, `README.md`.
- **Verification:** `node --check web/js/desk.js`; every README command checked against its
  `--help` (two were corrected before commit: `topic new` takes `--id/--name`, `report latest`
  takes a positional topic id). Browser check against a seeded run: asking from the Ask page
  goes through `/api/ask` and, with no model in the container, shows "The model did not answer."
  with no page errors. `ruff format --check`, `ruff check`, `mypy` clean; `uv run pytest -q` →
  537 passed, 3 deselected, coverage 91.57%.
- **Known issues:** None.
- **Next step:** Roadmap M1 — `F27`: topic update and delete in the repository and CLI
  (`topic edit`, `topic delete`), deleting a topic's runs with it.

## 2026-10-27 — Ask drops whole cards instead of cutting its JSON (complete)

- **Feature/branch:** `FIX16-ask-drops-whole-cards`, off `main` at `1e1272a`.
- **Status:** Complete; merged into `main`.
- **Summary:** `desk/ask.py::_context` serialized the run's cards to JSON and sliced the string at
  the budget, so an over-budget shelf reached the model as half an object — unparseable context
  and a card cut mid-sentence. It now drops the lowest-ranked whole cards until the JSON fits,
  always keeping the top card, so the model always gets valid JSON.
- **Files affected:** `src/research_agent/desk/ask.py`, `tests/unit/test_desk_ask.py`.
- **Decisions:** Cards are already in selection-rank order (`decisions_for` orders by rank), so
  popping from the end drops the least important first. A single card larger than the budget is
  still sent whole (slightly over a soft budget) rather than leaving "Ask about this paper" with
  nothing to read.
- **Verification:** Two new tests (over-budget shelf stays valid JSON, within budget, keeps a
  rank-ordered prefix; a lone over-budget card is kept) fail without the fix. `ruff format
  --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 537 passed, 3 deselected, coverage
  91.57%.
- **Known issues:** Ask borrows `reports.max_input_chars` (8000 characters). With 15 deep reads, a
  week-level question now sees only the top few cards — valid, but narrow. Giving Ask its own,
  larger budget belongs with the Ask roadmap item (F47) and is a user decision. The synthesis,
  ideation, report and analysis prompts also slice at their budgets, but they append a
  `[truncated]` marker to prose prompts, which is a different and lesser issue.
- **Next step:** `FIX17` — remove stale text and dead code (README sample week, `desk.js` header
  comment, the offline `replyTo` fake answers).

## 2026-10-27 — Desk refuses cross-site and DNS-rebinding requests (complete)

- **Feature/branch:** `FIX15-desk-reject-foreign-requests`, off `main` at `53a5818`.
- **Status:** Complete; merged into `main`.
- **Summary:** Binding to 127.0.0.1 did not protect the desk from the browser it serves. Any web
  page the user visited could POST to `/api/topics` (creating topics, starting pipelines, spending
  NIM quota) or DELETE runs, because the server parsed JSON regardless of `Content-Type` and
  checked neither `Host` nor `Origin`; a DNS-rebinding page could also read `/api/shelf`. Every
  request now must carry a local `Host` (`127.0.0.1:<port>` or `localhost:<port>`) and, when an
  `Origin` is present, a matching `http://` origin; anything else gets `403 Forbidden.` before
  any route runs.
- **Files affected:** `src/research_agent/desk/server.py` (`DeskHandler._foreign()`, called first
  in `do_GET`, `do_POST`, `do_DELETE`; the port comes from the accepted socket),
  `tests/unit/test_desk_server.py`.
- **Decisions:** Origin and Host checks only. A JSON `Content-Type` requirement was skipped as
  redundant once a foreign Origin is refused. Requests with no `Origin` (curl, scripts, the
  page's same-origin GETs) stay allowed: browsers send `Origin` on every cross-site POST/DELETE.
  No session token: Origin/Host checks close both holes for a single local user.
- **Verification:** New `test_the_server_refuses_foreign_hosts_and_origins` (foreign Host on a
  GET, cross-site `text/plain` POST, `Origin: null` DELETE all 403 with the backend untouched;
  the desk's own origin via `localhost` accepted) fails without the fix. Real Chromium attack:
  a page served from another local port fired a `no-cors` `text/plain` POST at the desk — the
  unfixed server created a `pwned` topic, the fixed one did not. The FIX12 browser flow (create a
  topic from the desk page) still passes. `ruff format --check`, `ruff check`, `mypy` clean;
  `uv run pytest -q` → 535 passed, 3 deselected, coverage 91.53%.
- **Known issues:** Opening the desk through any other host name (for example a custom
  `/etc/hosts` alias) is now refused by design.
- **Next step:** `FIX16` — Ask drops whole cards to fit the prompt budget instead of cutting the
  JSON string mid-object.

## 2026-10-27 — Reject duplicate YAML keys; NIM output budget back to 24000 (complete)

- **Feature/branch:** `FIX14-reject-duplicate-yaml-keys`, off `main` at `55df732`.
- **Status:** Complete; merged into `main`.
- **Summary:** `config/settings.yaml` set `models.nim.max_output_tokens` twice (24000, then 8192).
  YAML silently keeps the last value, so since F26 the NIM budget was 8192, not the 24000 F26
  chose as headroom for a thinking-mode reasoning trace plus a full answer — the truncation risk
  F26 meant to remove. Configuration loading now rejects any repeated key with an actionable
  error naming the key, file and line; the stray `8192` line is removed.
- **Files affected:** `src/research_agent/config.py` (`_UniqueKeyLoader`, a `yaml.SafeLoader`
  subclass used by `_load_yaml_mapping`, the only YAML loader), `config/settings.yaml`,
  `tests/unit/test_config.py`.
- **Decisions:** Kept 24000, the value F26 recorded choosing on purpose. The loader is still a
  `SafeLoader`, so no arbitrary object construction is enabled. The error is raised as a YAML
  `ConstructorError`, so the existing handler turns it into `ConfigurationError("invalid YAML in
  <path>: duplicate key ... line N")` with no new error path.
- **Verification:** New `test_a_repeated_key_is_rejected_not_silently_overwritten` fails without
  the loader change; `test_the_committed_configuration_loads` failed on the committed file until
  the duplicate was removed and now pins NIM at 24000. `research-agent config validate` passes.
  `ruff format --check`, `ruff check`, `mypy` clean; `uv run pytest -q` → 534 passed,
  3 deselected, coverage 91.49%.
- **Known issues:** A larger NIM budget lengthens worst-case calls; this is F26's chosen
  trade-off, still untimed live. A local `config/settings.yaml` on another machine with its own
  repeated key will now fail fast at startup — intended.
- **Next step:** `FIX15` — desk request hardening (require JSON, check Origin and Host).

## 2026-10-27 — Close runs a dead process left "running" (complete)

- **Feature/branch:** `FIX13-close-orphaned-runs`, off `main` at `ca26d31`.
- **Status:** Complete; merged into `main`.
- **Summary:** A run whose process died without unwinding (the desk's daemon run thread when the
  desk is stopped, a killed terminal, a crash) stayed `running` forever, and the desk showed a
  permanent "Running" stamp. `_interrupted` only covered in-process interruption. Now:
  - `execute_run` fails every open run of its topic right after taking the topic lock. Holding
    the lock proves no other run of that topic is live, so any open row is orphaned. This covers
    `run`, `run-all` and scheduled runs.
  - `research-agent desk` calls `close_orphaned_runs()` at startup: for each topic with an open
    run it tries the topic lock, reusing `run_lock`'s dead-PID stale detection, and skips topics
    whose run is live (`RunLocked`).
- **Files affected:** `src/research_agent/storage/runs.py` (`RunRepository.open_runs()` +
  SQLite implementation), `src/research_agent/operations/runner.py` (`close_orphaned_runs`,
  `_close_open_runs`, typed against the `RunRepository` protocol), `src/research_agent/cli.py`
  (desk startup), `tests/unit/test_operations_runner.py`, `tests/unit/test_storage_runs.py`.
- **Decisions:** No new error category or error row for an orphan, matching `_interrupted`; the
  close is logged as a structured warning with `status: "orphaned"`. The two existing
  interruption tests used to create their run row before `execute_run`; they now create it inside
  the fake workflow, where `load_topic` really does, so they still exercise `_interrupted` instead
  of passing via the new orphan cleanup.
- **Verification:** New tests for the run path, desk startup (orphan closed, live run with a held
  lock left alone) and `open_runs`. Mutation check: deleting the `execute_run` call makes
  `test_a_run_closes_runs_a_dead_process_left_open` fail. End to end: seeded a `running` row,
  started the real `research-agent desk` against a temporary data directory, `/api/shelf`
  reported it `failed`, and the structured warning was logged. `ruff format --check`,
  `ruff check`, `mypy` clean; `uv run pytest -q` → 532 passed, 3 deselected, coverage 91.47%.
- **Known issues:** A closed orphan's duration runs until it was noticed, not until the process
  died. Desk startup holds each affected topic's lock for milliseconds; a scheduled run starting
  in that instant would report `locked` and skip that week.
- **User decisions recorded:** `F23-multimodel-routing` is dropped (never pushed; deleted
  locally by the user). A Semantic Scholar API key has been requested; once it arrives, set
  `RESEARCH_AGENT_SOURCES__SEMANTIC_SCHOLAR_API_KEY` in `.env` and re-enable the source in
  `config/topics.yaml`. The live timed run with thinking mode on is deferred by the user.
- **Next step:** `FIX14` — reject duplicate YAML keys and resolve `models.nim.max_output_tokens`.

## 2026-10-27 — Desk shows topics created after startup (complete)

- **Feature/branch:** `FIX12-desk-reloads-topics`, off `main` at `27c2053`.
- **Status:** Complete; merged into `main`.
- **Summary:** A topic created from the desk's New topic flow never appeared in the desk until the
  server was restarted. Two causes, both fixed:
  1. `LocalDesk` took the topic list once at startup (`cli.py` passed `stored`) and built every
     shelf from that snapshot, while `create_and_run` wrote the new topic only to SQLite.
     `LocalDesk.shelf()` now reads `SqliteTopicRepository.list()` on each call; the constructor
     lost its `topics` argument.
  2. `desk.js` never refetched the shelf after `POST /api/topics` succeeded, so even a fixed server
     left the topic switcher stale until a page reload. `createTopic()` now reloads the shelf and
     selects the new topic. The three copies of the fetch-the-shelf code (boot, refresh, create)
     became one `loadShelf()`.
- **Files affected:** `src/research_agent/desk/server.py`, `src/research_agent/cli.py` (the desk
  command still migrates and seeds topics before serving, but no longer lists them),
  `web/js/desk.js`, `tests/unit/test_desk_server.py` (regression test against a real temporary
  SQLite database).
- **Decisions:** One extra `SELECT` per shelf request is negligible for a single-user desk and
  removes the stale-snapshot class of bug entirely, rather than appending to a cached list.
- **Verification:** New test `test_local_desk_shelf_shows_a_topic_added_after_startup` fails
  without the server fix and passes with it. Browser check with Playwright against the real
  `LocalDesk`, server and `desk.js` (only keyword suggestion and the pipeline thread stubbed, as
  no model is available in the cloud container): without the JS fix the topic switcher stayed
  `[existing_topic]`; with it, `[existing_topic, quantum_error_correction]` with the new topic
  selected and no page errors. `ruff format --check`, `ruff check`, `mypy` clean;
  `uv run pytest -q` → 529 passed, 3 deselected, coverage 91.46%.
- **Known issues:** The running desk process on the development Mac must be restarted to load
  the server change. The new topic's This week page still reads "No run is stored" until the
  background run creates its row; live run progress is roadmap item F30/F31.
- **Next step:** `FIX13` — mark runs left `running` by a dead process as failed at startup.

## 2026-10-27 — Vendor the ponytail coding skill (complete)

- **Feature/branch:** `CHORE3-vendor-ponytail-skill`, off `main` at `77b0fb5`.
- **Status:** Complete; merged into `main`.
- **Summary:** The user asked for all coding to follow the open-source "ponytail" skill (smallest
  complete change, no speculative abstraction, review before merge), committed to the repo so any
  agent session on a fresh clone has it.
- **Files added:** `.claude/skills/ponytail/SKILL.md`, `.claude/skills/ponytail/LICENSE` (MIT,
  required notice), `.claude/skills/ponytail-review/SKILL.md`. Copied unmodified from
  `github.com/DietrichGebert/ponytail` at commit `09c434ab73ca43761c5d8b0c5d341926c2fba710`.
- **Decisions:** Only the core skill and its review checklist were vendored; the audit, debt,
  gain and help sub-skills, hooks and installers were left out as unused. The skill now names
  shortcut comments `shortcut: <limit>, <when to upgrade>`; this repo keeps its existing
  `ponytail:` form, which the review skill accepts as equivalent.
- **Verification:** Markdown only; no code or tests affected.
- **Next step:** `FIX12` — the desk reloads topics from SQLite per shelf build.

## 2026-10-27 — Drop the stale `classifiers` entry from the import-boundary test (complete)

- **Feature/branch:** `FIX11-stale-classifiers-import-test`, off `main` at `b4f6e5c`.
- **Status:** Complete; merged into `main`.
- **Summary:** On a fresh clone the suite was 527 passed, 1 failed:
  `tests/unit/test_imports.py::test_architecture_boundary_imports[research_agent.classifiers]`.
  F22 (`4964ecf`) deleted the `classifiers` package when screening replaced the dual classifiers,
  but the boundary test still listed it. It kept passing on the development machine because a
  leftover `src/research_agent/classifiers/` directory (holding only `__pycache__`) imports as an
  empty namespace package. Reproduced here: such a directory imports with `__file__ = None`.
- **Files affected:** `tests/unit/test_imports.py` only — `classifiers` replaced by `screening`,
  and each boundary must now be a regular package (`module.__file__ is not None`), so a deleted
  package left behind as a bare directory fails instead of passing silently.
- **Decisions:** Kept the explicit boundary list rather than discovering packages dynamically; it
  documents the intended architecture, and the new assertion is what closes the stale-directory
  hole.
- **Verification:** `uv run ruff format --check .` clean; `uv run ruff check .` clean;
  `uv run mypy` no issues in 158 files; `uv run pytest -q` → 528 passed, 3 deselected, coverage
  91.26%. The 3 `-m slow` Docling tests were not run (they need a model download).
- **Known issues:** On the development Mac, delete the leftover `src/research_agent/classifiers/`
  directory so local results match a clean clone.
- **Next step:** Product-readiness roadmap M0 continues with `FIX12` — the desk reloads topics
  from SQLite per shelf build so topics created in the desk appear without a restart.

## 2026-10-27 — Commit the missing `reports` package and track AGENTS.md/CLAUDE.md (complete)

- **Feature/branch:** `FIX10-commit-missing-reports-package`, off `main`.
- **Status:** Complete on branch, ready to merge.
- **Summary:** A fresh clone was broken. `.gitignore`'s unanchored `reports/` line (added for the
  runtime `reports/` output directory) also matched `src/research_agent/reports/`, so that package
  was never tracked despite `cli.py`, `desk/shelf.py`, `operations/wiring.py`,
  `workflow/services.py`, and three test files importing from it — any fresh clone (including a
  cloud agent's) would fail with `ImportError` as soon as the CLI loaded. Separately, an earlier
  commit (`6b278c3`, "keep agent instructions local and untracked") had deliberately gitignored
  `AGENTS.md`/`CLAUDE.md`, which meant a cloud agent cloning this repo would have neither the
  governance doc nor the missing package — it could not have known the rules it was supposed to
  follow. The user asked to commit both so a cloud agent clone is self-contained.
- **Files affected:** `.gitignore` (anchored the runtime output dir as `/reports/` so it no longer
  shadows the package path; removed the `AGENTS.md`/`CLAUDE.md` ignore lines); added
  `src/research_agent/reports/{__init__,builder,naming,prompts,service}.py` (pre-existing,
  previously untracked code — `service.py` needed a `ruff format` pass before it would pass
  verification, no logic changed); added `AGENTS.md` and `CLAUDE.md` (the latter is a symlink to
  the former) as tracked files.
- **Decisions:** Reversed the earlier "keep agent instructions local" decision per explicit user
  instruction, since an untracked governance doc defeats the point of a cloud agent reading it.
  Kept the runtime `reports/` output directory ignored (now anchored to the repo root with a
  leading slash) rather than removing it from `.gitignore` entirely, since generated weekly reports
  still should not be committed.
- **Verification:** `ruff format --check` (failed once on `reports/service.py`'s pre-existing
  formatting drift, fixed with `ruff format`), `ruff check` clean, `mypy` clean on the new package,
  full suite `uv run pytest -q --no-cov` → 528 passed, 3 deselected.
- **Known issues / next step:** None outstanding for this fix. Merge to `main` and push so the
  cloud agent's next clone has both the package and the governance doc.

## 2026-09-30 — Capability-scoped thinking mode for deep analysis/synthesis (complete, on branch)

- **Feature/branch:** `F26-capability-scoped-thinking`, off `main` (which already carries FIX9).
- **Status:** Complete on branch, not yet merged.
- **Summary:** FIX5 and FIX9 turned thinking mode off everywhere (`disable_thinking: true`) to fix
  Qwen3/GLM's `content`-goes-null bug. The user asked why deep analysis, which could genuinely
  benefit from exposed reasoning, doesn't use the model's thinking capability. Explained the
  mechanism (thinking mode splits output across `reasoning_content` and `content`; disabling it
  doesn't reduce the model's reasoning, only the separate visible scratchpad) and offered to make
  it capability-scoped. Live-tested the cost first: a trivial prompt with thinking on took 113s and
  774 reasoning tokens versus a few seconds with it off. User chose to enable it for
  `deep_reasoning`/`synthesis` anyway, accepting the latency.
- **Files changed:**
  - `src/research_agent/config.py` — `ModelEndpointSettings.thinking_capabilities: list[str] = []`,
    capabilities exempted from `disable_thinking`.
  - `src/research_agent/models/base.py` — `ModelProvider.generate()` protocol gained a keyword-only
    `capability: str | None = None` parameter (mypy enforces exact structural match against
    `ModelProvider`-typed variables, so every fake test provider assigned to one needed the same
    signature — see below).
  - `src/research_agent/models/chat.py` — `ChatCompletionsProvider.generate()` takes `capability`
    and only sends `chat_template_kwargs.enable_thinking: false` when
    `disable_thinking and capability not in thinking_capabilities`.
  - `src/research_agent/models/router.py` — `ModelRouter.generate()`/`.generate_local()` now pass
    `capability=capability` through to every `provider.generate()` call (local-only path, strong
    provider retry loop, and the local fallback after retries are exhausted).
  - `config/settings.yaml` — both `models.local` and `models.nim` gained
    `thinking_capabilities: [deep_reasoning, synthesis]`; `local.max_output_tokens` raised
    8192→16000, `nim.max_output_tokens` raised 8192→24000 (headroom for a reasoning trace plus a
    full answer); `local.timeout_seconds` raised 120→600, `nim.timeout_seconds` raised 300→600
    (thinking-mode calls are dramatically slower — measured, not guessed).
  - `tests/unit/test_models_chat.py` — four new tests: `disable_thinking` sent by default; skipped
    for an exempted capability; still applied for a non-exempted one; and untouched entirely when
    `disable_thinking` is off. `tests/unit/test_models_router.py` — `FakeProvider` now records
    `last_capability`; a new test confirms it reaches the provider on the local-only path, the
    strong-provider path, the fallback-after-failure path, and `generate_local()`.
    `tests/unit/test_desk_ask.py` — `ScriptProvider.generate()` signature updated to match the
    widened protocol (mypy `[arg-type]` failure otherwise).
- **Decisions:** Screening, ideation, report_writing, cheap_text, and classification stay
  thinking-off — they need fast, reliable structured JSON and don't obviously benefit from an
  exposed reasoning trace the app doesn't store or display anywhere. Only `deep_reasoning` and
  `synthesis` were exempted, per explicit user choice after seeing the measured latency cost.
- **Verification:**
  - `uv run ruff format --check .`, `uv run ruff check .` → clean.
  - `uv run mypy` → Success: no issues found in 158 source files.
  - `uv run pytest -q` → 528 passed, 3 deselected, coverage 91.14% (gate 85%).
  - Live, against the real NIM endpoint via `ModelRouter.generate()`: `capability="screening"`
    returned plain `"OK"` quickly with thinking off; `capability="deep_reasoning"` returned a full
    reasoned answer (sky-is-blue explanation) with thinking on, `content` correctly populated in
    both cases — confirming the capability-scoped plumbing actually reaches the wire request.
  - Live, direct curl to NIM with thinking on and a 16000-token budget: `content` populated (782
    chars) after a 3932-char reasoning trace, `finish_reason: "stop"`, confirming a generous token
    budget reliably avoids the original null-content bug even with thinking on.
- **Known issues / next step:** Weekly runs that deep-read multiple papers will now take
  meaningfully longer per paper during analysis/synthesis — this is the accepted tradeoff, not a
  regression to fix. No live full-pipeline run has been timed end-to-end with this change; if
  runtime becomes a real problem the next lever is narrowing `thinking_capabilities` further, not
  raising timeouts again. Next: commit, push, merge into `main` per `AGENTS.md`.

## 2026-09-30 — Sample data removed, clear-data buttons added, NIM thinking-mode fixed (complete, on branch)

- **Feature/branch:** `FIX9-clear-data-nim-thinking-no-sample`, off `main` (which already carries
  FIX8).
- **Status:** Complete on branch, not yet merged.
- **Summary:** Four items from the user in one sitting:
  1. **Confusion:** the user saw error text ("Semantic Scholar answered 429", "No legal PDF",
     "The strong model failed one card") and asked whether a real run had happened. It hadn't —
     `web/js/data.js` was a sample fixture `desk.js` fell back to silently whenever `/api/shelf`
     was unreachable, with only a small footer line distinguishing it from real data. Per the
     user's explicit "remove the sample": deleted `web/js/data.js`, dropped its `<script>` tag
     from `web/index.html`. `desk.js` no longer has any fallback content — when the server can't
     be reached, `topics()` returns `[]` and the app shows a plain "Can't reach the desk server"
     message instead of fabricated data.
  2. **New feature — clear data:** `src/research_agent/storage/runs.py` gained
     `RunRepository.delete(run_id)` and `.delete_for_topic(topic_id)`, both one `DELETE` statement
     relying on the schema's existing `ON DELETE CASCADE` foreign keys (classifications, analyses,
     syntheses, gaps, ideas, errors, query plans, selections all cascade from `runs`; `papers`/
     `paper_sources` are deliberately untouched since they're deduplicated and shared across runs).
     `src/research_agent/desk/server.py` gained `LocalDesk.delete_run()`/`.clear_topic()` and two
     routes: `DELETE /api/runs/<id>` (weekly clear) and `DELETE /api/topics/<id>/runs` (topic-wise
     clear, keeps the topic definition). `web/js/desk.js`: a "Clear this run" button on the This
     week page, a per-row "Clear" button plus a page-level "Clear all runs" button on the Runs
     page, both behind a native `confirm()` dialog (destructive-action confirmation per the Web
     Interface Guidelines this desk redesign was already following), wired through new
     `deleteRun()`/`clearTopicRuns()`/`refreshShelf()` functions that refetch `/api/shelf` and
     re-render after the server confirms.
  3. **Fixed:** when a topic's runs are all cleared, the header's Run `<select>` now disappears
     entirely instead of rendering empty — `render()` only emits the Run switcher when
     `topic.runs.length` is nonzero.
  4. **Bug found and fixed while checking "connect NIM"** — the user's NIM answer (via `/api/ask`)
     was silently unusable. Live-tested `z-ai/glm-5.3-flash` (the model `.env` selects) directly:
     it is also a reasoning/thinking model, same failure shape as FIX5's local Qwen3 fix —
     `content` came back `null` with the answer in `reasoning_content`, and once `max_tokens` was
     small the reasoning trace alone exhausted it (`finish_reason: "length"`). Added
     `disable_thinking: true` to `config/settings.yaml`'s `models.nim` block (the
     `ChatCompletionsProvider.disable_thinking` wiring from FIX5 already supports any endpoint,
     this just turns it on for NIM too). Verified end-to-end through the actual `ModelRouter`
     against the real NIM endpoint: `provider: nvidia_nim, model: z-ai/glm-5.3-flash, text: "OK"`.
- **Files changed:** `config/settings.yaml`, `src/research_agent/desk/server.py`,
  `src/research_agent/storage/runs.py`, `web/css/desk.css`, `web/index.html`, `web/js/desk.js`
  (deleted `web/js/data.js`), `tests/unit/test_desk_server.py`, `tests/unit/test_reading_desk.py`,
  `tests/unit/test_storage_runs.py`.
- **Decisions:** Clearing is DB-only — generated files on disk (parsed Markdown, analysis cards,
  reports) are not deleted by these endpoints. `build_shelf()` reads only from SQLite, so the UI
  goes fully empty either way; leftover files are inert and just take up space. A full disk sweep
  was judged out of scope for a UI "clear" action versus the manual `data/` reset done earlier this
  session. Confirmation uses the browser's native `confirm()` rather than a custom modal — smallest
  correct implementation of the Web Interface Guidelines' "destructive actions require
  confirmation" rule.
- **Verification:**
  - `node --check web/js/desk.js` → no syntax errors.
  - `uv run ruff format --check .`, `uv run ruff check .` → clean.
  - `uv run mypy` → Success: no issues found in 158 source files.
  - `uv run pytest -q` → 523 passed, 3 deselected, coverage 91.10% (gate 85%).
  - Live, against the running desk server and a throwaway topic
    (`clear_data_smoke_check`): confirmed a real run's row existed, `DELETE /api/runs/<id>`
    removed exactly that row (`select count(*) from runs where id=...` → 0), then
    `DELETE /api/topics/<id>/runs` cleared the rest (`{"status": "cleared", "runs": 0}`). Smoke
    topic deleted afterward.
  - Live, against the real NIM endpoint via `ModelRouter.generate("deep_reasoning", ...)`:
    `provider: nvidia_nim, text: "OK"` — NIM is now genuinely answering, not silently failing over
    to local on every call.
- **Known issues / next step:** Disk artifacts (parsed text, analysis cards, reports) from a
  cleared run are not deleted — noted above as a deliberate scope decision, not a bug. Next:
  commit, push, merge into `main` per `AGENTS.md`.

## 2026-09-30 — New topic folded into the SPA; nav bug fixed; switcher restyled; topic id derived (complete, on branch)

- **Feature/branch:** `FIX8-new-topic-nav-and-switcher`, off `main` (which already carries FIX7).
- **Status:** Complete on branch, not yet merged.
- **Summary:** Three issues from the user, found while clicking through the redesigned desk:
  1. **Bug:** clicking "New topic" navigated to the standalone `web/new-topic.html` page, whose
     `<nav>` only had two hardcoded links ("This week", "New topic") — so every other nav item
     (Papers, Report, Runs, Ask) visibly disappeared. Root cause: "New topic" was a second static
     page duplicating the topbar markup instead of a route inside `desk.js`'s single-page app,
     which is the only place that actually builds the full nav.
  2. **Request:** "remove the old filters" — clarified via `AskUserQuestion` to mean the native
     `<select>` Topic/Run switchers in the top bar, not the Papers-page filter buttons.
  3. **Request:** make "New topic" a permanent, bold, brand-sized link (not a page-dependent nav
     pill), and drop the "Topic id" field from the form, deriving it from the name instead.
- **Fix — folded New topic into the SPA:** Deleted `web/new-topic.html` and `web/js/new-topic.js`.
  `web/js/desk.js` gained: a `state.newTopic` object (`step: "form"|"review"`, `name`,
  `description`, `keywords`, `pending`, `status`, `tone`); a `slugify(name)` helper; a
  `viewNewTopic()` render function producing the same `.panel`/`.topic-form`/`.keyword-review`
  markup the old static page used; a `"new"` branch in `render()`'s route dispatch (checked before
  the "no topic"/"no run" empty-state branches, since topic creation must work with zero topics);
  `suggestTopicKeywords()`/`createTopic()` async functions mirroring the existing `ask()`
  pattern (mutate `state.newTopic`, call `render()`, `fetch`, mutate again, `render()` again);
  `onSubmit`/`onClick`/`onInput` branches for the form's submit, the confirm/cancel buttons, and
  a live topic-id preview under the Name field. Because this reuses `render()`'s own topbar
  markup, the full nav is now structurally impossible to drop on the New topic route — the bug
  class this fixes cannot recur for any future route added the same way.
- **Fix — "New topic" is now a permanent, bold, brand-sized link:** Moved it out of the pill-style
  `.nav` list into a new `.brand-group` (flex wrapper occupying the topbar's `brand` grid area)
  alongside the "Desk" brand link, both `font-weight: 700` / `font-size: 1.2rem`. It renders
  unconditionally in every `render()` call regardless of route, so it can no longer disappear.
- **Fix — switcher restyled, not removed:** Kept the native `<select>` elements for Topic/Run
  (the only way to switch what the header is scoped to from any page; removing them outright would
  have been a functionality regression with no replacement) but stripped the bordered/boxed look
  the user called "old" — `appearance: none`, no border, transparent background, pill-radius hover
  highlight, chevron recolored to match the new muted palette. Reads as a text trigger now, not a
  form control.
- **Fix — topic id derived from name:** `new-topic-form` no longer has an id field. `slugify()`
  lowercases, collapses runs of non-`[a-z0-9]` to `_`, and trims leading/trailing `_`. A live
  preview under the Name field (`#new-topic-id-preview`, patched in `onInput` without a full
  `render()`, matching the existing `paper-search` pattern) shows what the id will be as the user
  types. The id is (re)computed once more at submit time from the same function.
- **Decisions:** `createTopic()` only sends `{id, name, keywords}` to `POST /api/topics` — the
  desk server's `TopicCreateRequest` in `src/research_agent/desk/server.py` already defaults
  `lookback_days` to 10 server-side, so nothing there needed to change. No Python changed at all
  in this branch.
- **Verification:**
  - `node --check web/js/desk.js` → no syntax errors.
  - `uv run pytest tests/unit/test_reading_desk.py tests/unit/test_desk_server.py
    tests/unit/test_desk_shelf.py tests/unit/test_desk_ask.py -q --no-cov` → 10 passed (these are
    the only tests that touch `web/`; none assert DOM structure beyond literal substrings, none of
    which moved).
  - Live, against the running desk server and `mlx_lm.server`: `POST /api/topics/suggest` returned
    real keywords for a throwaway topic; `POST /api/topics` with only `{id, name, keywords}`
    (matching the new client payload shape) returned `202` and a `runs` row appeared with
    `status="running"` within seconds. Smoke-test topic/run deleted afterward.
- **Known issues / next step:** None. Browser-visual confirmation of the nav/switcher/brand
  changes still needs the user to reload the page. Next: commit, push, merge into `main` per
  `AGENTS.md`.

## 2026-09-30 — Desk visual redesign: premium neutral system, drop the vintage stamp/serif look (complete, on branch)

- **Feature/branch:** `FIX7-premium-desk-redesign`, off `main` (which already carries FIX6).
- **Status:** Complete on branch, not yet merged.
- **Summary:** User flagged the desk UI (both `index.html`'s SPA views and `new-topic.html`) as
  "old and vintage and unpolished" and asked for a premium redesign across every page and click
  path. `web/css/desk.css`'s own header comment described the prior look as "cool paper, ink, one
  tide accent... the rubber stamp is the only playful mark" — a deliberate print/editorial
  aesthetic (serif Literata headings, a rotated passport-stamp status badge, flat hairline-divided
  rows) that read as dated rather than premium. Rewrote the whole stylesheet as a modern neutral
  design system; no HTML structure or JS template logic changed except wrapping the new-topic form
  in a `.panel` card, so every view `desk.js` renders (`week`/`papers`/`report`/`runs`/`ask`)
  picked up the new system automatically through shared class names.
- **What changed (all in `web/css/desk.css` unless noted):**
  - New tokens: `--surface`/`--surface-2` (card vs. canvas), `--shadow-sm/md/lg`, `--radius-sm/md/
    lg`, `--ease`/`--fast`/`--speed`. Palette kept the existing teal brand accent but refined it
    (`--tide: #0e7c72`) rather than replacing it.
  - Headings (`h1`/`h2`/`h3`), `.paper-row-title`, and `.run-period` moved from serif Literata to
    the sans (`Schibsted Grotesk`) — serif is now scoped only to long-form reading content
    (`.card-block`, `.lede`, `.turn p`, the paper-card body and ask answers), where it still reads
    as a deliberate editorial choice rather than as the whole app's chrome.
  - `.stamp` (run status) replaced the rotated, bordered "rubber stamp" with a plain rounded pill +
    dot indicator, tinted by status (`--wash`/`--carmine-wash`).
  - `.paper-row`, `.run-row`, `.finding`/`.idea`/`.gap`, `.turn` changed from hairline-divided list
    rows to individual cards (`--surface` background, border, `--radius-md`, hover elevation via
    `box-shadow` + `translateY(-1px)`).
  - `.filters` became a segmented control (pill container, active filter gets a white chip with
    `--shadow-sm`) instead of individually bordered pill buttons.
  - `.topbar` gained a translucent `backdrop-filter` blur; `.nav` active/hover states became pill
    chips instead of an underline `box-shadow`.
  - `.search`, `.switcher`, `.field input`/`.field textarea` unified to the same bordered
    `--radius-sm` style with a focus ring (`box-shadow: 0 0 0 3px var(--wash)`) instead of
    `outline: none` with no visible replacement (Web Interface Guidelines: focus indicators
    required, no bare `outline-none`).
  - `.composer` (the ask box) became a floating card with `--shadow-lg`, borderless textarea inside
    it, sticky above the bottom of the viewport.
  - Added a broad `@media (prefers-reduced-motion: reduce)` rule collapsing all transition/
    animation durations to near-zero, replacing the narrower rule that only covered `.stamp-land`
    (the new hover-elevation transitions on cards needed the same treatment).
  - `web/new-topic.html` — wrapped the form and the keyword-review step in a new `.panel` card
    (padding, border, `--radius-lg`, `--shadow-sm`) so the page reads as one coherent surface
    instead of loose fields on the bare canvas.
- **Decisions:**
  - Did not touch `web/js/desk.js`'s template strings — every class it emits already existed in
    the old stylesheet, so a CSS-only rewrite reaches every page (`week`, `papers`, `report`,
    `runs`, `ask`) without risking the DOM-structure assumptions `tests/unit/test_reading_desk.py`
    and `tests/unit/test_desk_server.py` make (both only check for literal substrings — route
    names, `/api/shelf`, `/api/ask`, sample topic ids — none of which moved).
  - Checked all internal links across both pages (`grep -n 'href=' web/index.html web/new-topic.html`):
    `new-topic.html` ↔ `index.html` cross-links both directions, `index.html`'s hash router covers
    all five views, no dead links found. Did not add a "New topic" affordance beyond the existing
    nav link — no other entry point into topic creation exists in the app to redesign.
  - Ran this against the Web Interface Guidelines (vercel-labs/web-interface-guidelines) via the
    `/web-design-guidelines` skill: labels-for-inputs, focus-visible rings, reduced-motion support,
    and `tabular-nums` on numeric columns were already present or were added; did not add
    `Intl.NumberFormat`/list virtualization/line-clamp truncation since nothing in this single-user
    local tool's data volume needs them and no existing content overflows its containers.
- **Verification:** `uv run pytest tests/unit/test_reading_desk.py tests/unit/test_desk_server.py
  tests/unit/test_desk_shelf.py tests/unit/test_desk_ask.py -q --no-cov` → 10 passed. Verified live
  against the running desk server (`curl http://127.0.0.1:8765/css/desk.css` and `/new-topic.html`)
  that the new stylesheet and the `.panel`-wrapped form are actually served. No Python changed, so
  the full ruff/mypy/pytest gate was not re-run (nothing it covers changed); confirmed no HTML tag
  imbalance in `new-topic.html` with a small parse check.
- **Known issues / next step:** This was a CSS/HTML-only pass; browser-visual confirmation still
  needs the user to reload the page (I cannot render a browser here). Next: commit, push, merge
  into `main` per `AGENTS.md`.

## 2026-09-30 — New-topic form styled and cleaned up (complete, on branch)

- **Feature/branch:** `FIX6-new-topic-form-styling`, off `main` (which already carries F25).
- **Status:** Complete on branch, not yet merged.
- **Summary:** Two problems the user flagged from a screenshot of `web/new-topic.html`: (1) the
  page looked unstyled/unprofessional — plain browser-default inputs, no visual hierarchy between
  the two action states; (2) the id/name fields' placeholder text literally read
  `embodied_spatial_intelligence` / `Embodied Spatial Intelligence`, which read as if an old topic
  were still selected in a filter rather than as example placeholder text. Restyled the form to
  match the reading desk's existing visual language and swapped the placeholders for a generic,
  unrelated example (`quantum_error_correction`).
- **Files changed:**
  - `web/css/desk.css` — added a `.topic-form`/`.field`/`.form-actions`/`.keyword-review`/
    `.keyword-chips`/`.status-line` block reusing existing tokens (`--tide`, `--wash`, `--line`,
    etc.); no existing selector was modified, so `index.html`'s pages are unaffected.
  - `web/new-topic.html` — restructured into labeled `.field` groups, generic placeholders, the
    existing `.primary` (filled) button for the two forward actions and `.button` (outline) for
    "Back", matching the styling `desk.js` already uses elsewhere (e.g. the ask composer).
  - `web/js/new-topic.js` — suggested keywords now render as a `<ul>` of pill-styled
    `.keyword-chip` items instead of a plain comma-joined string; `setStatus()` takes an optional
    tone (`error`/`success`) so failures show in the same carmine used elsewhere in the app.
- **Decisions:** No Python changed, so the full pytest/mypy/ruff suite was not re-run (nothing it
  covers changed); verified instead by curling the served HTML/JS/CSS from the running desk server
  and re-exercising `POST /api/topics/suggest` live against `mlx_lm.server` to confirm the redesign
  didn't break the request flow.
- **Verification:** `curl http://127.0.0.1:8765/new-topic.html` — new placeholders present, old
  topic names gone. `curl -X POST .../api/topics/suggest` — real keyword suggestions returned
  unchanged.
- **Known issues / next step:** None. Next: commit, push, merge into `main` per `AGENTS.md`.

## 2026-09-30 — Local data reset; add-topic suggests keywords then triggers the pipeline (complete, on branch)

- **Feature/branch:** `F25-topic-suggest-and-trigger`, off `main` (which already carries FIX5).
- **Status:** Complete on branch, not yet merged.
- **Summary:**
  1. Wiped all run-derived local data at the user's request: `runs`, `papers`, `paper_sources`,
     `classifications`, `paper_files`, `paper_analyses`, `weekly_syntheses`, `research_gaps`,
     `research_ideas`, `errors`, `selections`, `query_plans` rows, and the generated PDFs/parsed
     text/analyses/reports under `data/topics/*/{papers,analyses,runs,reports,parsed}`. The
     `topics` table and `config/topics.yaml` were left untouched, as were the directory shells.
     Not part of this branch's diff — `data/` is gitignored, nothing to commit.
  2. New feature: creating a topic can now ask the local model for candidate keywords, show them
     for confirmation, and on yes immediately run the pipeline — both from the CLI and from the
     reading desk website, per explicit user request ("if we add a new topic, local llm finds the
     relevant keywords confirms with user then starts pipeline").
- **Files changed:**
  - `src/research_agent/topics/` (new package) — `prompts.py` (`PROMPT_VERSION =
    "topic_keywords.v1"`, asks for 5-8 short keyword phrases as JSON), `suggest.py`
    (`suggest_keywords(router, name, description) -> list[str]`, always routed to the
    `cheap_text` capability so it never needs NIM; a `ModelProviderError` degrades to `[]` rather
    than raising, matching the query-planner's existing fallback style).
  - `src/research_agent/cli.py` — new `topic new` command: suggests keywords, prints them,
    `typer.confirm`s once ("Create topic '<id>' with these keywords and run the pipeline now?"),
    and on yes adds the topic then calls the existing `_run_one` synchronously (same path `run`
    uses), so the terminal blocks until the run finishes and prints the same outcome line.
  - `src/research_agent/desk/server.py` — new `TopicSuggestRequest`/`TopicCreateRequest` request
    models, `LocalDesk.suggest()` and `LocalDesk.create_and_run()`, and two routes:
    `POST /api/topics/suggest` (returns `{"keywords": [...]}`) and `POST /api/topics` (stores the
    topic, returns `202 {"status": "started", "topicId": ...}` immediately, and runs the pipeline
    on a background `threading.Thread` with its own SQLite connection — the request must not
    block on a multi-minute run). A `TopicStoreError` (duplicate id) returns `409`.
  - `web/new-topic.html`, `web/js/new-topic.js` (new) — a small standalone form (not integrated
    into `desk.js`'s hash-router, to keep the diff small): name/description → suggest → review →
    confirm → started. `web/js/desk.js` — added a "New topic" link in the top nav.
  - `tests/unit/test_topics_suggest.py`, `tests/unit/test_desk_server.py` (extended),
    `tests/integration/test_topic_new_cli.py` (new).
- **Decisions:**
  - The desk endpoint runs the pipeline in a background thread rather than blocking the HTTP
    response, since a real run can take minutes; the existing `run_lock` in `execute_run` already
    prevents two concurrent runs of the same topic, so a second `POST /api/topics` (or a CLI
    `run`) for the same id while one is in flight reports `locked` rather than corrupting state.
  - Kept the CLI's confirm a single yes/no covering both topic creation and the run start, per the
    user's literal ask ("confirms with user than starts pipeline") rather than two separate
    prompts.
  - The website form is a standalone page rather than a new route inside `desk.js`'s SPA, to avoid
    a large diff in a 758-line file for a form with no shared state with the reading views.
- **Verification:**
  - `uv run ruff format --check .`, `uv run ruff check .` → clean.
  - `uv run mypy` → Success: no issues found in 158 source files.
  - `uv run pytest -q` → 520 passed, 3 deselected, coverage 91.21% (gate 85%).
  - Live, against the running `mlx_lm.server` (Qwen3-14B): `research-agent topic new` printed real
    suggested keywords and correctly aborted on "n". Live also surfaced and fixed an unrelated
    `.env` problem (see below).
  - Live, against the running desk server: `POST /api/topics/suggest` returned real keywords;
    `POST /api/topics` returned `202` and a `runs` row appeared with `status="running"` within
    seconds, confirming the background trigger actually starts `execute_run`. The smoke-test
    topic/run were deleted afterward; `runs`/`papers` are back to 0 rows, matching the reset above.
- **Found and fixed while verifying live:** `.env` still had four `RESEARCH_AGENT_MODELS__LOCAL__*`
  overrides from an earlier session's "NIM standing in for the local runtime" validation setup,
  which silently pointed the `local` provider at Ollama/`qwen3:8b` (and NIM's API key) regardless
  of `config/settings.yaml`. This made `topic new`'s keyword suggestion silently degrade to
  `(none suggested)` on the first live run. Removed the four override lines; `.env` now defers to
  `config/settings.yaml`'s `models.local` block (`mlx_lm.server`, `Qwen3-14B-4bit`) unmodified.
  `.env` is gitignored, so this fix is local-only and not part of the branch diff.
- **Known issues / next step:** `topic new`'s pipeline run is synchronous in the CLI (matches
  `run`'s existing behavior) but fire-and-forget in the desk endpoint (necessary for an HTTP
  response); the desk UI has no polling/progress indicator yet, the user must reload "This week"
  to see when a background run finishes. Not built, since it wasn't requested. Next: commit, push,
  merge into `main` per `AGENTS.md`.

## 2026-09-30 — Local model switched to Qwen3-14B via mlx_lm.server (complete, on branch)

- **Feature/branch:** `FIX5-local-model-qwen3-14b-thinking`.
- **Status:** Complete on branch, not yet merged.
- **Summary:** User moved local inference off Ollama onto `mlx_lm.server` running
  `mlx-community/Qwen3-14B-4bit` (already resolved in the HF cache from earlier session setup).
  Live testing against the running server (`curl .../v1/chat/completions`) surfaced a real
  correctness bug: Qwen3's default "thinking" mode returns its answer in a `reasoning` message
  field and, once `max_tokens` is spent on the thinking trace, omits `content` entirely — but
  `ChatCompletionsProvider._content()` in `src/research_agent/models/chat.py` requires `content`
  to be a string, so every local-provider call would have raised `ModelProviderError`. Confirmed
  the fix by curling with `chat_template_kwargs: {"enable_thinking": false}`, which restores a
  normal `content` field and `finish_reason: "stop"`.
- **Files changed:**
  - `config/settings.yaml` — `models.local.base_url` → `http://localhost:8080/v1` (mlx_lm.server's
    port, not Ollama's 11434), `models.local.model` → `mlx-community/Qwen3-14B-4bit`, added
    `models.local.disable_thinking: true`.
  - `src/research_agent/config.py` — added `ModelEndpointSettings.disable_thinking: bool = False`
    (opt-in, so NIM and any Ollama-style endpoint without thinking-mode quirks are unaffected).
  - `src/research_agent/models/chat.py` — `ChatCompletionsProvider.generate()` now sends
    `chat_template_kwargs: {"enable_thinking": false}` when `disable_thinking` is set. Top-level
    `enable_thinking` in the request body is silently ignored by `mlx_lm.server`; only the
    `chat_template_kwargs`-nested form works, confirmed by direct curl comparison.
- **Decisions:** Kept `disable_thinking` a settings flag rather than hardcoding the behavior, since
  NIM and non-thinking local models must not receive this field. Did not change the JSON-fence
  stripping in `models/router.py:_parse_json` — Qwen3 still wraps JSON replies in ```` ```json ````
  fences even with `response_format: json_object`, and that stripping already exists and was
  verified working via the same curl test.
- **Verification:**
  - Live: `curl http://localhost:8080/v1/chat/completions ... enable_thinking:false` → normal
    `content` field, `finish_reason: "stop"`.
  - Live: same request with `response_format: json_object` → fenced JSON, confirmed parseable by
    existing `_parse_json` fence-stripping logic.
  - `uv run ruff format --check .` → 149 files already formatted.
  - `uv run ruff check .` → All checks passed.
  - `uv run mypy` → Success: no issues found in 153 source files.
  - `uv run pytest -q` → 515 passed, 3 deselected, coverage 91.63% (gate 85%).
- **Known issues / next step:** No unit test added for `disable_thinking`'s wire-level effect since
  it's a pure pass-through of a config flag into the request body, exercised live above; the
  existing `test_models_chat.py` fixtures don't hit a real Qwen3 thinking-mode response shape. If
  this becomes a recurring pain point, consider a unit test asserting the request body when the
  flag is set. Next: commit, push, merge into `main` per `AGENTS.md`.

## 2026-09-30 — F24 reading desk merged to main (complete, merged)

- **Feature/branch:** `F24-reading-desk`, merged onto `main` after `FIX4-screening-status-and-stale-test`.
- **Status:** Complete, merged.
- **Summary:** Folds in the branch's prior two entries below (implementation, then the server-backed
  shelf/ask read path) unchanged. Merged onto a `main` already carrying FIX4's screening-error fix,
  so this entry only records the merge itself; no code changed during the merge beyond a conflict
  resolution in this file.
- **Verification:** Re-ran `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`, and
  `uv run pytest` on `main` after the merge; see the result recorded just below this entry.
- **Commit/merge:** merged to `main` as `merge: F24-reading-desk read the local library`.
- **Next:** None outstanding for F24. `F23-multimodel-routing` remains a separate, unmerged branch.

## 2026-09-30 — FIX4 screening failures now surface as run errors (complete, merged)

- **Feature/branch:** `FIX4-screening-status-and-stale-test`, branched from `main` at `6e5317f`.
- **Status:** Complete, merged.
- **Summary:** Two regressions from the F22 merge, found while verifying `main` before merging
  `F24-reading-desk`. Neither is caused by F24, which touches none of the affected files.
  1. `PaperScreener.screen_many` swallowed every screening failure into a log line and dropped the
     paper, so a dead model provider produced zero `ErrorRecord`s and the run reported
     `status="completed"` instead of `"degraded"`, even though papers were silently unscreened.
     `screen_many` now returns `(accepted, failures)`, where each `ScreeningFailure` carries the
     paper id and the `ErrorCategory` raised (`MODEL_API_ERROR`, `MODEL_TIMEOUT`,
     `INVALID_CLASSIFIER_OUTPUT`, or `CLASSIFIER_ERROR`). The graph's `classify` node appends one
     `ErrorRecord` per failure, matching the acquire/parse/analyze nodes' existing pattern, so
     `persist` now correctly marks the run `degraded`. The standalone `research-agent classify` CLI
     command was updated for the new return shape and now echoes screening errors alongside source
     errors.
  2. `tests/unit/test_storage_topics.py::test_add_round_trips_every_field` built a `TopicSettings`
     with `classifier={"active": "B", "shadow": None}`, a field F22 removed when it replaced
     Classifier A/B with semantic screening; the test raised `ValidationError: extra_forbidden` on
     every run. Removed at the user's direction (no remaining use once the classifier field is
     gone); the `_topic()` helper and its other non-default-field coverage stay, used by the
     surrounding tests.
- **Files:** `src/research_agent/screening/service.py` (new `ScreeningFailure`, `screen_many`
  return type), `src/research_agent/workflow/nodes.py` (`classify` node records errors),
  `src/research_agent/cli.py` (`_classify` return type, `classify` command echoes failures),
  `tests/unit/test_screening_service.py` (updated existing test, new
  `test_a_dead_provider_is_reported_as_a_screening_failure` regression test),
  `tests/integration/test_workflow_graph.py` (`test_a_dead_model_provider_still_produces_a_report`
  now asserts `MODEL_TIMEOUT`, not `MODEL_API_ERROR` — the mocked provider returns HTTP 503, which
  `discovery/http.py`'s `_RETRYABLE_STATUS` retries and then reports under the transient category
  by design; the old assertion was stale, not a real bug), `tests/unit/test_storage_topics.py`
  (removed the stale test).
- **Decisions:** No schema/migration change — `ScreeningFailure` is a transient in-process model,
  not persisted directly; it only feeds the existing `ErrorRecord` path. Left the CLI's standalone
  `_save_classifications` run-summary status logic (based only on discovery errors) as-is; that
  command is a separate ad-hoc path from the graph and was out of scope for this fix.
- **Verification:** `uv run ruff format --check .` — passed. `uv run ruff check .` — passed.
  `uv run mypy` — passed, 145 files. `uv run pytest` — 505 passed, 3 deselected, 93.39% coverage.
  `uv run pytest -m slow` — 3 passed. `uv run research-agent config validate` — valid.
- **Commit/merge:** commit `fix(screening): surface screening failures as run errors`; merged to
  `main` as `merge: FIX4-screening-status-and-stale-test surface screening failures as run errors`.
- **Next:** Merge `F24-reading-desk` onto this now-green `main`.

## 2026-09-30 — F24 reading desk reads the local library (committed, ready to push)

- **Feature/branch:** `F24-reading-desk`, continuing the static desk. Not a new feature number. `F23-multimodel-routing` is untouched.
- **Status:** Implemented, verified, and committed on the branch. Push requested next. Not merged.
- **Behavior:** `research-agent desk` serves `web/` and two loopback routes on `127.0.0.1:8765`. `GET /api/shelf` builds the page's shelf from SQLite and the stored weekly report. `POST /api/ask` sends the question and the cards on that run (or one paper) through the existing model router on `deep_reasoning`, so NVIDIA NIM is used when configured and the local model is used after NIM call failures or one invalid JSON reply. Cited paper ids that were not on the shelf are dropped. Opening the page without the desk command still shows the sample week. An empty library shows the empty state.
- **Files:** `src/research_agent/desk/` (`shelf.py`, `ask.py`, `server.py`), `src/research_agent/cli.py` (`desk` command), `src/research_agent/storage/results.py` (`synthesis_for`, `classifications_for(..., active_only=True)`), `web/js/desk.js`, `tests/unit/test_desk_shelf.py`, `tests/unit/test_desk_ask.py`, `tests/unit/test_desk_server.py`, plus the existing desk and results tests, `README.md`.
- **Decisions:** Stdlib `ThreadingHTTPServer`, no new dependency. The process binds to loopback only. Ask is not stored on the server. The prompt gets card fields, not PDF text. The public paper id is the stored canonical id. Executive summary is parsed from the report artifact; a missing report falls back to the first development or a short count sentence.
- **Verification:** `uv run ruff check src/research_agent/desk src/research_agent/cli.py src/research_agent/storage/results.py tests/unit/test_desk_shelf.py tests/unit/test_desk_ask.py tests/unit/test_desk_server.py tests/unit/test_storage_results.py tests/unit/test_reading_desk.py` passed. `node --check web/js/desk.js` passed. `uv run pytest tests/unit/test_desk_shelf.py tests/unit/test_desk_ask.py tests/unit/test_desk_server.py tests/unit/test_storage_results.py tests/unit/test_reading_desk.py --no-cov -q` passed (18). Earlier branch verification also included `uv run ruff format --check` on touched Python files and `uv run mypy` passing. The full pytest suite was not run. No live NIM call was made.
- **Commit:** This branch commit, `feat(desk): serve the local reading library`. Final hash is available from `git log` after amendment/push.
- **Next:** Push `F24-reading-desk`, then merge it to `main` when requested. Do not start F23 from this branch.

## 2026-09-29 — F24 reading desk (implemented, not committed)

- **Feature/branch:** `F24-reading-desk`, branched from `main` at `6e5317f`.
- **Commit:** `ee6bad5` feat(desk): add a static reading desk for weekly runs.
- **Status:** Committed on `F24-reading-desk`. Not merged. `F23-multimodel-routing` is a separate branch and is not included here.
- **Behavior:** `web/` is a single-user reading desk: this week, papers and paper cards, the weekly report, run history, and Ask. Topic and run switchers change the shelf. Ask answers from the sample cards and states that NVIDIA NIM is not connected.
- **Files:** `web/index.html`, `web/css/desk.css`, `web/js/data.js`, `web/js/desk.js`, `tests/unit/test_reading_desk.py`, `README.md`.
- **Decisions:** Plain HTML, CSS, and JavaScript, so the same files can sit on S3 later and call a small read API. No new runtime and no NIM call in this slice. Sample papers are fictional layout data, not a live run.
- **Verification:** `node --check` on `web/js/data.js` and `web/js/desk.js` passed. `uv run pytest tests/unit/test_reading_desk.py --no-cov -q` passed (3). Headless Chrome screenshots of This week, Papers, a paper card, Report, Runs, Ask, and a 390px week. The page is not wired to SQLite or NIM.
- **Next:** Merge `F24-reading-desk` when asked. Then a read API over the local repositories, then send Ask through the existing NIM router with local fallback.

## 2026-09-28 — F22 semantic paper screening (in progress)

- **Feature/branch:** `F22-semantic-paper-screening`.
- **Status:** Implementation in progress; not merged.

**Behavior changed**

- Replaced executable Classifier A/B, lexical matching, embeddings, shadow execution, classifier
  switching, and comparison commands with one semantic screening service. It sends structured
  screening to the strong NIM capability and uses the configured local model when NIM fails.
- Screening now requires the paper's central contribution to match the topic. Its structured audit
  result records provider, model, fallback, repair status, and prompt version.
- Candidate capacity is divided across the executed query plan, avoiding the previous first-query
  monopoly. Source balancing from F21 remains in place.
- Existing SQLite columns and historical classifier rows remain readable. New runs write the legacy
  active-classifier column as `semantic_screening`; topic configuration no longer contains A/B
  settings. The obsolete test suites and comparison script were removed.

**Files and interfaces**

- New `research_agent.screening.PaperScreener`; `WorkflowServices.screener` replaces
  `WorkflowServices.classifiers`.
- New model capability `screening`, routed through NIM with the existing local fallback.
- Removed the `research_agent.classifiers` package and `research-agent classifier` / comparison CLI.
- Updated sample config, topic configuration, manifests, PRD/TRD, README, and operations guidance.

**Verification so far**

- `.venv/bin/ruff check .` — passed.
- `.venv/bin/mypy` — passed, 146 files.
- `.venv/bin/python -m pytest tests/unit/test_screening_service.py --no-cov -q` — 1 passed.
- `.venv/bin/research-agent config validate` — valid.
- `.venv/bin/python -m pytest tests/unit/test_models_router.py tests/unit/test_screening_service.py --no-cov -q` — 20 passed after the NIM structured-output repair.

**Known issue / next step**

- The broad legacy suite still contains A/B-specific acceptance and CLI assertions and needs a
  final replacement pass. The first full run also exposed an unchanged-rerun assertion failure in
  the acceptance fixture after changing screening semantics; investigate before merge. Do not
  merge until the updated full suite passes.
- **2026-09-29 repair:** NIM replies that contain a JSON object wrapped in Markdown/prose are now
  parsed safely. A schema failure reaches the screener, which sends one explicit repair prompt to
  NIM and uses local inference only if repair fails. This replaces the previous immediate fallback
  that produced the `strong provider returned invalid structured output` warnings.

## 2026-09-28 — F21 quality-aware paper ranking (complete, merged)

- **Feature/branch:** `F21-quality-paper-ranking` (allocated after F20).
- **Commits:** `91fa8c5` feat(ranking): prioritize relevant recent quality papers; merged as `94c1613`.
- **Status:** Complete, merged, and re-verified on `main`.

**Behavior added**

- Classifier A lexical scoring is now `classifier_a.v2`: an exact topic phrase in an abstract is
  scored on the evidence that matched instead of being diluted by every optional keyword. This
  fixes the observed Computer Vision run where 50 classified papers all scored `low/ignore`.
- Selection now ranks eligible papers with deterministic recency, preferred-venue, citation, and
  source-metadata signals. Relevance remains the eligibility gate; quality ordering only decides
  which papers fit download/deep-read limits. Defaults include CVPR, ICCV, ECCV, NeurIPS, ICML,
  ICLR, AAAI, IJCAI, SIGGRAPH, TPAMI, JMLR, Nature, and Science, all configurable in settings.
- Discovery shares each query's candidate budget across enabled sources so one provider cannot fill
  the entire candidate set and starve the others.
- Full workflow runs now persist their resolved query plan and include the queries in the run
  manifest for auditability.

**Files and interfaces**

- New: `src/research_agent/selection/quality.py`, `tests/unit/test_selection_quality.py`.
- Modified: Classifier A lexical scoring, selection ordering/configuration, discovery source quotas,
  workflow query-plan persistence, manifests, README, and local operations documentation.
- No schema migration or new dependency.

**Verification**

- `.venv/bin/ruff check src/research_agent tests` → clean.
- `.venv/bin/mypy` → success, no issues in 160 source files.
- `.venv/bin/python -m pytest` → **603 passed, 3 deselected**, coverage 94.10%.

**Known issues and next step**

- The live Computer Vision run should be rerun after merge; this branch does not mutate the user's
  existing database or report artifacts.
- Venue metadata is best-effort from providers; papers without a venue remain eligible when topical
  relevance is sufficient but rank below recent papers with known preferred venues.
- Next step: rerun `research-agent run computer_vision` and inspect the selected papers/report.

## 2026-09-27 — F20 AWS portability validation (complete, merged)

- **Feature/branch:** `F20-aws-portability-validation`.
- **Commits:** `ca1cad5` feat(portability): validate AWS-compatible boundaries; merged as `7cddfdf`.
- **Status:** Complete, merged, and re-verified on `main`. **This is the last feature on the roadmap: F1-F20 are all merged.**

**Behavior added**

- `DeploymentProfile` names one backend per replaceable boundary — artifacts, metadata, scheduler, logs, secrets, worker — and validates the combination. A local profile cannot quietly point at S3; an AWS profile cannot quietly keep cron and must replace at least one backend; `LOCAL_PROFILE` is what `DeploymentProfile()` gives you.
- **Cost guardrails are code, not prose.** `free_plan_only` defaults true and the profile refuses EKS/Kubernetes, NAT Gateway, OpenSearch/Elasticsearch, SageMaker, Fargate, RDS/Aurora, MSK and GPU endpoints. Waiving it takes an explicit `free_plan_only=False`.
- **`worker="lambda"` is refused for an AWS target**, encoding TRD section 51: a weekly run is long and holds a per-topic lock, so Lambda serves the trigger and the API, never the whole graph.
- `SecretResolver` with `EnvironmentSecrets` (local) and `ParameterStoreSecrets` (Parameter Store / Secrets Manager shaped, over an **injected fetcher**, so no dependency and nothing untestable). A remote backend without a fetcher raises rather than falling back to the environment — a silent fallback is how a deployment reads the wrong secrets. `SecretMapping` names the only three secrets the application uses, which is what a least-privilege policy grants.
- `EventBridgeScheduler` joins launchd and cron behind the same `Scheduler` Protocol and renders a deterministic schedule JSON for the same `research-agent run <topic_id>` command, with `MaximumRetryAttempts: 0` because a retry would collide with the per-topic lock. `research-agent schedule generate --backend eventbridge` prints it and the `aws scheduler create-schedule` line.
- `docs/AWS_PORTABILITY.md`: the boundary map, the execution design, what the conformance tests prove, a least-privilege IAM policy, secret handling, the cost guardrails and a six-step runbook with a rollback that needs no code change.

**Files and interfaces**

- New: `src/research_agent/portability/{__init__,profiles,secrets}.py`, `docs/AWS_PORTABILITY.md`, `tests/unit/test_portability_{conformance,boundaries}.py`.
- Modified: `src/research_agent/operations/scheduling.py` (`EventBridgeScheduler`, the backend Literal, EventBridge day names); `src/research_agent/cli.py` (accepts the new backend).
- **No new dependency.** A test asserts `pyproject.toml` declares no `boto3`/`botocore`/`aws`, and another asserts the portability package imports none.

**What the conformance suite proves (58 new tests, all in the default suite)**

- Substituting an object store for the filesystem needs no application change: a card is written and a parsed paper is read back through the real `load_parsed` over S3-shaped flat keys, and `ReportService.latest`'s lookup works from an object listing. The fake still refuses a key that escapes its topic prefix.
- `PaperCandidate` and `PaperAnalysis` round-trip through a partition/sort-keyed document table via the same Pydantic models the SQLite repositories use — the domain model is the contract, not the SQL.
- The EventBridge schedule is deterministic, targets the same command, and carries no credential.
- Remote secret resolution maps the same logical names to `/research-agent/<env>/<name>` and never falls back to the environment; a missing secret names the secret, never a value.
- Logs are one JSON object per line with a timezone-aware timestamp, which is the whole CloudWatch contract — no adapter needed.
- **Statically:** no module under `workflow/` names `sqlite3`, `pathlib`, `boto3`, a `Sqlite*` repository, `LocalArtifactStore`, `DoclingParser`, `PdfDownloader` or a model provider; the AST check also rejects importing `models.chat` or the Docling adapter; no domain model mentions a provider or a backend; and a topic's serialized form contains no bucket, ARN, path or backend name.

**Decisions and why**

- **No thin AWS adapters were shipped.** The roadmap allows them "only when they can be tested safely and do not become required locally". A real S3 or DynamoDB adapter needs credentials and a live account to test honestly; the in-memory stand-ins prove the boundary is sufficient, which is what F20 is actually for. The injected-fetcher seam is where a `boto3` adapter would attach.
- **The guards are static tests, not documentation.** "No local paths in workflow nodes" is a property of the source, so a test that reads the source is the only thing that can keep it true.
- **`EventBridgeScheduler` lives beside launchd and cron** rather than in `portability/`, because it is an implementation of an existing Protocol and the CLI already resolves backends there.

**Verification**

- `uv run ruff format --check .` → 155 files already formatted; `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 158 source files, exit status 0.
- `uv run pytest` → **598 passed, 3 deselected**; coverage 94.05% (gate 85%).
- `uv run research-agent config validate` → valid.
- `uv run research-agent schedule generate --topic embodied_spatial_intelligence --backend eventbridge` → a valid weekly schedule (`cron(0 7 ? * SUN *)`, UTC) invoking `research-agent run embodied_spatial_intelligence`, with the create-schedule command.
- The local regression suite is unchanged in behaviour: same commands, same defaults, no new required configuration.

**Known issues and next step**

- The AWS path is validated, not deployed: no resources exist, and nothing has run on AWS. That is deliberate and in the roadmap's out-of-scope list.
- **Roadmap complete.** The remaining known items are all recorded above and none belong to a roadmap feature: a shadow-classifier ceiling, one repair retry for analysis (a TRD deviation that would need recording), the arXiv HTTP 406 (server-side), Semantic Scholar's 429s without a key, Classifier A's thresholds producing `summarize` rather than `deep_read` on a real corpus, moving `discovery/http.py` to `utils/http.py` now that it has three consumers, and the F2-era `ResourceWarning: unclosed database` in tests.

## 2026-09-27 — FIX3 acceptance test typing (complete, merged)

- **Feature/branch:** `FIX3-acceptance-test-typing`.
- **Commits:** `9e4e3dd` fix(tests): type the acceptance suite's transport; merged as `092fdb9`.
- **Status:** Complete, merged, and re-verified on `main`.

**What happened**

F19 was merged with `mypy` failing: 16 `arg-type` errors in `tests/integration/test_acceptance.py`, because `counted()` was annotated `tuple[object, ...]` while `services()` wants a `Handler`. The merge went ahead because the verification command piped mypy into `tail`, and a pipeline reports the exit status of its last stage — so a red type check looked green. That is a process defect as much as a typing one.

**The fix**

- `counted()` returns `tuple[Handler, dict[str, int]]`, reusing the alias the graph tests already define.
- The resource-limit test now builds its bounded services with `dataclasses.replace` instead of reconstructing the frozen dataclass from `__dict__` behind a `type: ignore`.
- **Verification habit corrected:** run `uv run mypy` on its own and check its exit status. Never `uv run mypy | tail`.

**Verification**

- `uv run ruff format --check .` → 150 files already formatted; `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 153 source files, **exit status 0** (checked explicitly).
- `uv run pytest` → 540 passed, 3 deselected; coverage 93.87%.

## 2026-09-27 — F19 MVP reliability hardening (complete, merged)

- **Feature/branch:** `F19-mvp-reliability-hardening`.
- **Commits:** `44aa7d0` feat(reliability): harden end-to-end MVP execution; merged as `263231d`.
- **Status:** Complete, merged, and re-verified on `main`. A full live `run` completed end to end for the first time: 994s, 471 candidates, 250 classified, 11 selected, 9 PDFs, 0 parse failures, 8 analyses, 5 gaps, 5 ideas, one report, status `degraded` with 10 isolated errors.

**Behavior added**

- **Reproducibility manifest.** Every completed run writes `<run_id>-manifest.json` under the topic's `runs` artifacts: period and status, the resolved topic configuration and limits, enabled sources, active/shadow classifier, provider and model names, prompt versions, the relevant settings blocks, and the run's counts. Names only — a manifest is safe to attach to a bug report.
- **Log redaction.** `SecretRedactingFilter` removes credentials before a record is formatted: known vendor key shapes, `Authorization: Bearer …`, `?api_key=…` parameters, and the literal value of any `RESEARCH_AGENT_*` variable whose name mentions `API_KEY`, `TOKEN`, `SECRET` or `PASSWORD`. Exception tracebacks go through it too, which is where a request URL most often leaks.
- **Structured logging is actually on.** `_open_connection` calls `configure_logging` with the settings file's own `log_level`, closing a gap that had been open since F1: the CLI emitted no structured logs at all. `httpx`/`httpcore`/`urllib3` are pinned to `WARNING`, because their INFO lines print full request URLs.
- **The run summary is complete.** `persist` now records `models_used` from the run's analyses alongside the existing counts, so a run row carries counts, models, classifiers, timing and final status.
- `docs/OPERATIONS.md` gained a Logs section, a Reproducibility section, and seven more troubleshooting rows covering the slow-shadow-classifier case, arXiv 406, Semantic Scholar 429, Docling's first-run download, empty-week reruns and post-interrupt recovery.

**Files and interfaces**

- New: `src/research_agent/observability/manifest.py`, `tests/unit/test_logging_redaction.py`, `tests/integration/test_acceptance.py`, `tests/integration/conftest.py`.
- Modified: `src/research_agent/observability/logging.py` (redaction, third-party levels); `src/research_agent/workflow/{nodes,services}.py` (`store` on the services, manifest written by `persist`, `models_used`); `src/research_agent/operations/wiring.py` (supplies the store); `src/research_agent/cli.py` (configures logging); `docs/OPERATIONS.md`; `tests/integration/test_{workflow_graph,run_cli}.py`.
- No schema change: the manifest is an artifact and `models_used` already existed on `RunSummary`.
- Also carried here: `config/topics.yaml` now has `semantic_scholar: false` for the live topic, with the reason inline — without an API key that source answers 429 on every query.

**The acceptance sweep**

`tests/integration/test_acceptance.py` drives one fully mocked stack and asserts the PRD's promises directly: a complete run produces a report with every required section; an unchanged rerun performs **zero** analyses and **zero** downloads; the run summary carries counts, models, timing and classifiers; the manifest records the inputs and contains no credential; the four resource limits are respected; every recorded error category is a member of the documented `ErrorCategory`; a corrupt parsed artifact degrades to abstract-only instead of ending the run; an abandoned run does not block the next one and is kept for diagnosis; **no file a run writes contains the configured key**; the same run renders identical references whenever the report is rebuilt; and the reporting period matches the run.

**Decisions and why**

- **The fixture corpus is the mock transport, not a new directory of files.** The graph tests already drive every stage from one switchable transport plus a committed sample PDF; adding a parallel fixture corpus would have duplicated it without testing anything more.
- **Redaction reads the environment at log time** rather than caching values at import, so a key set after start-up is still redacted, and a short placeholder such as `none` is not treated as a secret.
- **The manifest is an artifact, not a table.** It is write-once, read-by-a-human, and belongs beside the report it explains.
- **An unchanged rerun reporting an empty week is correct, not a bug**, and is now asserted as such: caching means nothing was selected, so there is nothing new to report. `classify --reanalyze` is the escape hatch.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 151 source files.
- `uv run pytest` → 540 passed, 3 deselected; coverage 93.87% (gate 85%).

**What the first complete live run showed**

- `degraded  embodied_spatial_intelligence  8 paper(s)  10 error(s)` in 994s, with a report on disk. The ten errors were all isolated and all recorded with the documented taxonomy: 5 `DISCOVERY_ERROR` (arXiv HTTP 406, one per query), 2 `PDF_DOWNLOAD_ERROR` (no open-access PDF), 3 `MODEL_API_ERROR` in analysis. Every other stage completed. This is exactly the degraded-but-useful behaviour the PRD asks for.
- The three analysis failures had two distinct causes, both worth recording: one reply omitted the required `topic_relevance` field, and one was truncated mid-string. The truncation was a token ceiling, so `models.*.max_output_tokens` moved 4096 → 8192 in `config/settings.yaml` with the reason inline. The missing field is the model, not the code: analysis deliberately has no repair retry (the TRD gives that to Classifier B alone), so the paper is skipped and recorded. If it recurs often, granting analysis one repair retry is the change to make, and it is a TRD deviation that needs recording.
- `deep_reads` was 0 while 11 papers were selected: the lexical Classifier A scored them all `summarize` rather than `deep_read`. Worth a threshold review, not a defect.
- That run began before this branch's own changes were saved, so its summary shows `models_used: []` and it wrote no manifest. **Confirmed on the next live run** (after F20 merged, 213s, `degraded`, 7 isolated errors): `models_used: ["openai/gpt-oss-20b"]` in the summary and `43c1474b…-manifest.json` on disk carrying the period, sources, classifier, models, prompt versions and counts — with no `nvapi` string and no `api_key` anywhere in it. The run took 213s rather than 994s because caching skipped the papers already analysed.

**Known issues and next step**

- Shadow-mode cost is still unbounded: with `shadow=B` a run sends up to `max_classified` papers to an LLM whose verdicts never route, which is what made the first live `run` appear to hang. The operator workaround is documented; a dedicated shadow ceiling would be the real fix and is not in any roadmap feature.
- **Next recommended step:** F20 AWS portability validation — interface conformance for filesystem→S3, SQLite→DynamoDB-style repositories, launchd/cron→EventBridge, local logs→CloudWatch and env secrets→Parameter Store, plus the profile schema and the runbook, with local execution staying the default.

## 2026-09-27 — FIX2 arXiv pagination bound (complete, merged)

- **Feature/branch:** `FIX2-arxiv-pagination`.
- **Commits:** `5cb5b54` fix(discovery): bound source pagination; merged as `4819e64`.
- **Status:** Complete, merged, and re-verified on `main`.

**The defect**

`ArxivSource.search` requests results `sortBy=submittedDate&sortOrder=descending` but applies the date window in `_translate`, client-side. It paged until it had `limit` candidates, so for a 10-day window against `max_candidates=500` it walked the entire arXiv result set at one request every three seconds, discarding almost everything. A live `run` sat in discovery for 88 minutes with 3.4s of CPU.

**The fix**

- arXiv stops as soon as a whole page predates the window. The results are newest-first, so every later page is older too — this is exact, not a heuristic.
- `SourceSettings.max_pages` (default 10) caps pages per query for every source. OpenAlex honours it as well, so a cursor that keeps returning itself cannot loop for ever.
- Three regression tests: the early stop (asserting the third request is never made), the arXiv ceiling when every page is in-window, and the OpenAlex ceiling against a never-ending cursor.

**Two diagnoses this branch settled, neither a defect in it**

- **The 31-minute stall after the fix was the shadow classifier**, not discovery. The live topic has `active=A, shadow=B`, so every run sent up to `max_classified=250` papers to the LLM at `concurrency.analysis=2` purely to store non-routing verdicts. Shadow mode is working as specified — the TRD only requires that it never fail the run — but it makes a live run impractical, so the shadow was switched off for the live topic. **Recommendation for F19:** give shadow classification its own, much smaller ceiling; the point of shadow mode is comparison, which a sample satisfies.
- **The arXiv HTTP 406 is server-side and not fixable here.** Probed directly: `all:electron` returns 200, while `ti:electron`, `cat:cs.AI`, and *any* multi-word query return 406 with zero bytes, with or without `User-Agent`/`Accept`, over HTTP or HTTPS, on `export.arxiv.org` and `arxiv.org`, with the space encoded as `+` or `%20`. No client change fixes it. The behaviour is already correct: 406 is not retried, the source error is recorded, and the run continues on OpenAlex alone. OpenAlex returns 474 candidates for the live topic in 4.3s.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 149 source files.
- `uv run pytest` → 519 passed, 3 deselected; coverage 93.77% (gate 85%).

**Next step**

- A live end-to-end `run` with the shadow classifier off, then F19 MVP reliability hardening.

## 2026-09-27 — F18 run operations and scheduling (complete, merged)

- **Feature/branch:** `F18-run-operations-scheduling`.
- **Commits:** `192a1b1` feat(operations): add run commands and local scheduling; merged as `f9fa0c1`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline in full; the live end-to-end `run` is blocked by an F5 discovery defect this branch's first live run exposed (see below), fixed next on `FIX2-arxiv-pagination`.

**Behavior added**

- `research-agent run <topic_id>` executes the whole F17 graph for one topic, and `research-agent run-all` does it for every enabled topic in turn, printing one line per topic plus a count summary.
- **One lock per topic** (`data/locks/<topic_id>.lock`, created with `O_EXCL`), so a scheduled run and a manual one cannot collide. A lock whose process no longer exists is reclaimed; an unreadable one is treated as held, which fails safe.
- **Exit codes an operator can script against:** `completed` and `degraded` exit 0 — a degraded run still delivered a report — while `failed` (no report), `skipped` (disabled topic) and `locked` exit 1.
- Ctrl-C closes the open run as `failed`, releases the lock and keeps every artifact already written, so an interrupted run never reads as still running.
- `research-agent schedule generate --topic <id> [--backend launchd|cron] [--at HH:MM] [--output path]` renders a launchd agent or a crontab line for the topic's configured day, ending with the one command that installs it. The rendering is deterministic and contains a command and paths only — `ScheduleRequest` rejects an executable carrying shell syntax or an inline environment assignment, so a credential cannot be smuggled into a schedule.
- `operations/wiring.py` is now the single place that knows how each service is constructed, with a `parser` injection point so a test never loads Docling.
- `docs/OPERATIONS.md` documents the per-stage commands, whole runs, exit codes, where artifacts land, scheduling, and a troubleshooting table.

**Files and interfaces**

- New: `src/research_agent/operations/{__init__,wiring,locks,runner,scheduling}.py`, `docs/OPERATIONS.md`, `tests/unit/test_operations_{locks,runner,scheduling}.py`, `tests/integration/test_run_cli.py`.
- Modified: `src/research_agent/cli.py` (`run`, `run-all`, `schedule generate`).
- No new dependency, no schema change: locks are files and schedules are text.

**Decisions and why**

- **A lock file, not a database row.** The run's own artifacts are files, the tool is single-user, and a file lock survives a crashed process in a way a row does not.
- **`Scheduler` is a Protocol with two implementations**, so the AWS EventBridge equivalent in F20 slots in without touching the workflow, and scheduling stays outside LangGraph as the TRD requires.
- **The scheduled command is the operator command.** A schedule runs `research-agent run <topic_id>` verbatim: anything an operator can debug by hand is exactly what runs weekly.
- **Degraded is a success.** Exiting non-zero on a degraded run would make a paywalled PDF look like a broken installation to cron.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 148 source files.
- `uv run pytest` → 513 passed, 3 deselected; coverage 93.71% (gate 85%).
- Tests cover: a single run completing and reporting; the lock released afterwards; an overlapping invocation refused without starting a run; a partial failure exiting 0 as degraded; a disabled topic skipped; an unknown topic; `run-all` over mixed enabled states; deterministic and secret-free launchd and cron rendering; a schedule written to a file; an invalid time; an unsupported backend; interruption closing the run as failed; and a stale lock reclaimed.
- `uv run research-agent schedule generate --topic embodied_spatial_intelligence` → a valid launchd plist with the topic's weekly day and install/removal commands.
- **Interruption verified live, twice.** Ctrl-C on a real `run` printed `failed  embodied_spatial_intelligence  0 paper(s)  0 error(s)  interrupted: CancelledError`, exited non-zero, closed the run row as `failed` and left no lock behind.

**Three defects the live runs exposed, two fixed here**

- **Fixed:** the run used one HTTP client with the NIM timeout (300s) for everything, so a stalled search could block for five minutes. `services_for` now opens one client per timeout class — searches, downloads and inference — and `build_services` takes all three.
- **Fixed:** `queries.max_per_run` (default 5) now bounds how many of a plan's queries one run actually searches. A plan holds up to twenty for reproducibility, but the slowest source is paced at one request every few seconds, so searching all of them made a run take an hour.
- **Fixed:** the `discover` node keyed its cross-query deduplication on the `canonical_id` *field*, which an adapter may not have set, so candidates could collapse to one. It now keys through `canonical_id()`, the same function persistence uses.
- **Not fixed here — the blocker:** `ArxivSource.search` sorts by `submittedDate descending` but applies the date window client-side, and pages until it has `limit` candidates. For a 10-day window against `max_candidates=500` that means paging through the whole arXiv result set at 0.33 requests/second: the live run sat in discovery for 88 minutes with zero classifications and 3.4s of CPU. It belongs to F5, not to this branch, so it goes to `FIX2-arxiv-pagination` rather than being smuggled into a feature merge.

**Known issues and next step**

- Semantic Scholar was disabled for the live topic (`source_semantic_scholar = 0`) because without an API key it answers 429 with `Retry-After` up to 60s on every query, and its limiter serializes at 0.2 requests/second. That is the previously recorded discovery defect, not a new one.
- **Next recommended step:** `FIX2-arxiv-pagination` — stop paging once a page is entirely older than the window (the results are date-sorted, so everything after it is older too) plus a hard page ceiling, with a regression test. Then the live end-to-end `run`, then F19 MVP reliability hardening — the acceptance sweep over this now-complete pipeline: idempotency, cache reuse, the error taxonomy, a reproducibility manifest, the resource-limit audit and the log-redaction audit.

## 2026-09-27 — F17 LangGraph workflow (complete, merged)

- **Feature/branch:** `F17-langgraph-workflow`.
- **Commits:** `1eea57f` feat(workflow): orchestrate the complete research graph; merged as `8ae5fc5`.
- **Status:** Complete, merged, and re-verified on `main`. Verified by a fully mocked end-to-end graph run plus one test per failure branch. No live run yet: the operator entry point is F18's.

**Behavior added**

- `ResearchState` is the graph's validated state and carries identifiers, paths and counts only. A `model_validator` rejects a value in `pdf_paths`/`parsed_paths` that is document content rather than a path, so the graph cannot start carrying papers between nodes.
- `WorkflowServices` is a frozen dataclass of already-constructed collaborators. Nodes hold no provider, endpoint, URL or SQL knowledge; the whole graph runs against fakes in tests because of it.
- Thirteen nodes — `load_topic`, `plan_queries`, `discover`, `broaden`, `classify`, `select`, `acquire`, `parse`, `analyze`, `synthesize`, `ideate`, `report`, `persist` — each a coroutine returning only the fields it changed, and none of them raising: a failed stage appends an `ErrorRecord` and the run continues with less.
- Conditional routes, all pure functions of state and unit-tested on their own: empty discovery broadens **exactly once** and then reports an empty week; nothing selected goes straight to the report; no acquired PDF skips parsing entirely and analysis runs abstract-only; no analysis skips synthesis; no synthesis skips ideation.
- `persist` records every tolerated error, then closes the run with its summary and a status of `completed`, `degraded` (any error) or `failed` (no report produced).

**Files and interfaces**

- New: `src/research_agent/workflow/{__init__,state,services,nodes,graph}.py`, `tests/unit/test_workflow_{state,routes}.py`, `tests/integration/test_workflow_graph.py`.
- Modified: `pyproject.toml` (`langgraph>=1.0,<2`, resolving 1.2.12, and a mypy override for it).
- No migration and no schema change: the graph reuses the repositories and services the earlier branches built.

**Decisions and why**

- **Dependency:** `langgraph>=1.0,<2` (1.2.12, with `langchain-core`, `langgraph-checkpoint`, `langgraph-prebuilt`, `langgraph-sdk` and their transitive packages). The PRD/TRD name LangGraph for orchestration, and it is used for orchestration only — state propagation, conditional routing and failure branching. No LangChain chain, agent, tool or provider abstraction is used anywhere.
- **mypy deviation, documented:** `follow_imports = "skip"` for `langgraph.*`. `StateGraph.add_node`'s overloads do not accept a plainly typed async node function, and its generics are not resolvable against a Pydantic state here. Our nodes, state and routes stay strictly typed; only the builder call is opaque. Recorded in `pyproject.toml` with that reason.
- **Normalization and deduplication are inside `DiscoveryAggregator`** (since F5) rather than separate nodes. Splitting them out would have meant reimplementing them; the flow the TRD describes is preserved, one node deep.
- **Checkpoints are not enabled.** The TRD allows them "only where justified", and a single-user weekly run that is cheap to repeat does not justify the extra state store. The state is checkpoint-shaped (small, path-only) if that changes.
- **No CLI in this branch.** `research-agent run` is F18's deliverable; adding it here would have split that feature across two branches.

**Two real defects the graph found**

- The `acquire` node was matching download statuses `("downloaded", "cached")`, but `DownloadStatus` is `("stored", "cached", "unavailable", "failed")`. Every download was being discarded silently. Now matched correctly.
- `DiscoveryAggregator` stamps its error records with `run_id="unscheduled"` because it does not know the run. Persisting one violated the `errors.run_id` foreign key and failed the whole `persist` step. The `discover` node now re-stamps them with the real run id.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 139 source files.
- `uv run pytest` → 484 passed, 3 deselected; coverage 93.78% (gate 85%).
- The graph integration test runs the real services over mock transports and covers: a complete run producing a report and a closed run; the report containing the findings; empty discovery broadening once then reporting an empty week; a failed download leaving papers abstract-only; a parse failure isolated and recorded; a dead model provider still producing a report; a failing source not ending the run; a planner-driven plan reaching the state; and a second run reusing stored analyses and therefore selecting nothing.
- Retry ceilings are set to zero in that test's settings deliberately — the ceilings and their backoff are covered by the F5/F6 tests, and here they only made the failure branches slow (43s → 8.5s).

**Known issues and next step**

- The graph has never run against live providers; every live stage so far has been exercised through its own CLI command. F18's `run` command is what will do that.
- **Next recommended step:** F18 run operations and scheduling — `research-agent run <topic_id>` and `run-all` over this graph, with overlap protection and launchd/cron generation.

## 2026-09-27 — F16 report generation (complete, merged)

- **Feature/branch:** `F16-report-generation`.
- **Commits:** `1ae6cf7` feat(reports): generate weekly research reports; merged as `0f57c73`.
- **Status:** Complete, merged, and re-verified on `main`. The first end-to-end weekly deliverable exists on disk, produced from real papers.

**Behavior added**

- `build_report` assembles every PRD section 13 section as a pure function of stored records, so the same run always renders byte-identical Markdown: topic, period, executive summary, developments, directions, methods, datasets/benchmarks, contradictions, changes from previous weeks, open problems, papers, reading order, gaps, ideas, sources and run provenance.
- **Only the executive summary is model-written**, through the `report_writing` capability. A provider failure, or `--no-prose`, degrades that one paragraph to an assembled sentence; the report itself is never lost.
- The reading order tiers come from the classifier's own action (`deep_read` → Essential, `summarize` → Useful, otherwise Peripheral), so the order is reproducible rather than a second judgement.
- Degradation is stated in the document: a run with errors or a non-clean status carries a degraded banner and lists its recorded errors, and an abstract-only analysis is counted in a banner and marked on its own entry.
- Empty weeks render a short honest report — the run record and provenance, with no invented sections and no model call at all.
- Reports are stored as `YYYY-MM-DD_weekly_report.md` under the topic's `reports` artifacts, written atomically by `LocalArtifactStore`, one per period, so regenerating replaces in place.
- `research-agent report generate --topic <id> [--run] [--days] [--no-prose]` and `research-agent report latest <topic_id>`; `latest` picks by filename, which is why the name starts with the date.

**Files and interfaces**

- New: `src/research_agent/reports/{__init__,naming,prompts,builder,service}.py`, `src/research_agent/utils/markdown.py`, `tests/unit/test_reports_{builder,service}.py`, `tests/integration/test_report_cli.py`.
- Modified: `src/research_agent/storage/artifacts.py` (`ArtifactStore.names`, needed for a deterministic latest-report lookup); `src/research_agent/config.py` (`ReportSettings`); `src/research_agent/cli.py` (`report generate`, `report latest`); `analysis/cards.py` and `ideation/cards.py` now import the shared escaping helpers instead of keeping their own copies.
- No migration: the report is derived from existing records and stored as an artifact.

**Decisions and why**

- **Deterministic assembly, not a model-written report.** The PRD wants a reproducible deliverable with provenance; a model writing the whole document could not guarantee that. Prose is confined to one paragraph, and the report reads correctly without it.
- **`ArtifactStore.names` rather than a database table of reports.** The filesystem already is the artifact index, and the date-first filename makes "newest" a sort, not a query.
- **A third copy of the escaping helpers was not written.** `utils/markdown.py` now holds `inline` and `block`, and both existing card renderers use it. This is reuse of what the feature needed, not an opportunistic refactor.
- Untrusted content is escaped everywhere it enters the document, including the model-written summary, which is treated exactly like any other model output.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 131 source files.
- `uv run pytest` → 465 passed, 3 deselected; coverage 93.77% (gate 85%).
- `uv run research-agent report generate --topic embodied_spatial_intelligence` → a 156-line report for the live run, all 16 sections present, with the model-written summary, the degraded banner (2 recorded errors), the abstract-only banner (2 of 4), DOI links in Sources, and the reading order populated from the stored verdicts.
- `uv run research-agent report latest embodied_spatial_intelligence` → returns that same path.
- The integration test drives classify → acquire → parse → analyze → synthesize → ideate → report over mock transports, including the provider-failure path still producing a report.

**Known issues and next step**

- The live report is marked degraded because two of four selected papers had no acquirable PDF (arXiv 406 and a paywalled DOI). That is the acquisition defect already recorded below, not a report defect.
- **Next recommended step:** F17 LangGraph workflow — every stage now exists as an injectable service with a CLI entry point, which is exactly the set of nodes the graph has to wire together.

## 2026-09-27 — F15 research ideation (complete, merged)

- **Feature/branch:** `F15-research-ideation`.
- **Commits:** `1a5293e` feat(ideation): generate supported research directions; merged as `dc96d68`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline and live against the strong provider over the stored synthesis.

**Behavior added**

- `IdeationService` makes two bounded calls: gaps from the week's stored synthesis, then ideas from the gaps that survived validation. Both stages route through the `ideation` capability, so the router's retry-then-fallback applies unchanged.
- **Traceability is enforced, not requested.** A gap or idea citing a paper outside the run's corpus is dropped; surviving references are pruned, deduplicated and sorted. An idea whose `identified_gap` does not match a gap actually offered is dropped, so no idea can invent the problem it claims to solve.
- Duplicate ideas are collapsed on the normalized title, reusing the F3 `normalize_title` rather than a second notion of sameness.
- `max_gaps` and `max_ideas` are enforced in code as well as stated in the prompt; anything past the ceiling counts as dropped.
- A failure in ideation after gaps were stored keeps the gaps and reports the partial outcome, rather than discarding work that was already validated and persisted.
- `research-agent ideate --topic <id> [--run]` prints each gap and idea with its supporting papers and the dropped counts, writes `<run_id>-ideation.md` under the topic's `runs` artifacts, and exits non-zero with a `MODEL_API_ERROR` when nothing was supported.

**Files and interfaces**

- New: `src/research_agent/ideation/{__init__,prompts,generator,cards}.py`, `tests/unit/test_ideation_{generator,cards}.py`, `tests/integration/test_ideate_cli.py`.
- Modified: `src/research_agent/domain/analysis.py` (`GapDraft`/`IdeaDraft`, with `ResearchGap`/`ResearchIdea` extending them with provider, model and prompt version); `src/research_agent/config.py` (`IdeationSettings`); `src/research_agent/cli.py` (`ideate`).
- No migration: `research_gaps` and `research_ideas` store their models as `payload_json`, and both tables were empty before this branch.

**Decisions and why**

- **Two calls, not one.** Gaps must be validated against the corpus before ideas are built on them; a single call would let an idea rest on a gap that was about to be dropped.
- **The reply is an envelope (`{"gaps": [...]}`)**, because JSON mode requires a top-level object and a bare list is not one.
- **Prompt ceilings are filled in with `str.replace`, not `str.format`.** The prompts contain literal JSON braces, which `format` reads as fields — it raised `KeyError: '"gaps"'` on the first run. A one-line comment on `gap_system_prompt` records why.
- **Confidence stays optional but bounded** by the schema (0-1). A reply with an out-of-range confidence fails validation outright rather than being silently clamped, which is the F6 contract.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 122 source files.
- `uv run pytest` → 438 passed, 3 deselected; coverage 93.53% (gate 85%).
- `uv run research-agent ideate --topic embodied_spatial_intelligence` → 5 gaps and 1 idea from the live synthesis, none dropped, every one citing a real paper of the run; artifact written under `data/topics/embodied_spatial_intelligence/runs/`.
- The integration test drives classify → acquire → parse → analyze → synthesize → ideate over mock transports, including a gap citing a non-existent paper being dropped and kept out of the artifact.

**Known issues and next step**

- The live model produced five gaps but only one idea. The prompt allows up to five; whether that is the model or the prompt is worth a look once F16 shows the ideas in a report.
- **Next recommended step:** F16 report generation — every input it needs (analyses, synthesis, gaps, ideas, run summaries) is now persisted.

## 2026-09-27 — F14 weekly synthesis (complete, merged)

- **Feature/branch:** `F14-weekly-synthesis`.
- **Commits:** `caef913` feat(synthesis): add historical weekly synthesis; merged as `c84bf86`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline and against the real strong provider over four live analyses.

**Behavior added**

- `WeeklySynthesizer` compares a run's analyses with each other and with the topic's recent syntheses, then persists one `WeeklySynthesis` per run. It never raises: a provider failure or malformed output returns a `SynthesisOutcome` carrying the reason and stores nothing.
- `SupportedFinding` makes evidence mandatory rather than optional. `major_developments`, `emerging_directions`, `methods_gaining_attention`, `contradictions` and `common_limitations` are lists of findings, each with the paper ids that support it; `new_datasets`, `new_benchmarks` and `changes_from_history` stay plain strings because they are not per-paper claims.
- **References are validated against the run's own corpus.** An id the run did not analyse is removed; a finding left with no valid id is dropped and counted in `SynthesisOutcome.dropped_findings`. Surviving references are deduplicated and sorted, so the same inputs store byte-identical output.
- History is the previous `synthesis.history_window` syntheses (default four, matching the PRD). With no history the prompt says so explicitly and `changes_from_history` is expected to stay empty; `history_periods` records how many periods were actually compared.
- `research-agent synthesize --topic <id> [--run] [--days]` prints each finding with its supporting ids, plus how many were dropped, and records a `MODEL_API_ERROR` and exits non-zero when no synthesis could be produced.

**Files and interfaces**

- New: `src/research_agent/synthesis/{__init__,prompts,synthesizer}.py`, `tests/unit/test_synthesis_synthesizer.py`, `tests/integration/test_synthesize_cli.py`.
- Modified: `src/research_agent/domain/analysis.py` (`SupportedFinding`, `SynthesisDraft`, and `WeeklySynthesis` now extending the draft with `paper_ids`, provider/model, `prompt_version` and `history_periods`); `src/research_agent/config.py` (`SynthesisSettings`); `src/research_agent/cli.py` (`synthesize`); `src/research_agent/queries/prompts.py` (history bullets now read `finding.text`).
- No migration: `weekly_syntheses` stores the model as `payload_json`, and the table was empty before this branch.

**Decisions and why**

- **`WeeklySynthesis` extends `SynthesisDraft`** rather than duplicating its fields, mirroring the F13 split: the model supplies the draft, the synthesizer adds everything a reader has to be able to trust.
- **An unsupported finding is dropped, not stored with a warning.** The acceptance criterion is that every substantive finding references known supporting papers, and a finding that survives with no reference would quietly break that guarantee in the F16 report.
- **The prompt carries paper ids, not indices**, so a citation can be checked literally against the corpus, and each paper's `abstract_only` depth is stated so the model can hedge on the shallow ones.
- The one consumer of the old `list[str]` history — the F7 query-expansion prompt — was updated in place; it is the only caller, so no compatibility shim was needed.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 115 source files.
- `uv run pytest` → 417 passed, 3 deselected; coverage 93.41% (gate 85%).
- `uv run research-agent synthesize --topic embodied_spatial_intelligence` → one synthesis over the four live analyses, served by `nvidia_nim/openai/gpt-oss-20b`: 3 developments, 5 directions, 4 methods, 4 contradictions, 5 limitations, 1 dataset, 4 benchmarks, 0 history periods, every finding citing real paper ids from the run.
- The integration test drives the whole local pipeline — classify, acquire, parse, analyze, synthesize — over mock transports, including a finding citing a non-existent paper being dropped.

**Known issues and next step**

- `changes_from_history` has only ever been exercised with synthetic history (the live topic has one period so far). A second live weekly run is what will show whether the model uses it well.
- **Next recommended step:** F15 research ideation — `ResearchGap` and `ResearchIdea` have existed since F4 with no producer, and the supported findings this branch stores are their input.

## 2026-09-27 — F13 paper analysis (complete, merged)

- **Feature/branch:** `F13-paper-analysis`.
- **Commits:** `40629ba` feat(analysis): add evidence-backed paper analysis; merged as `515a32d`.
- **Status:** Complete, merged, and re-verified on `main`. This is the first feature whose strong/local provider split ran against a real endpoint.

**Behavior added**

- `PaperAnalyzer` turns each selected paper into a validated `PaperAnalysis` and a Markdown paper card. The model supplies only an `AnalysisDraft`; the analyzer adds `paper_id`, `model_provider`, `model_name`, `prompt_version` and `abstract_only`, so nothing a reader has to trust comes from the model.
- Parsed full text is preferred; without it the prompt falls back to title plus abstract and the stored analysis records `abstract_only=True`, which the card states in a banner.
- Claim provenance is validated, not trusted: a claim naming a section the parsed paper does not contain keeps its text and loses `source_section` and `page` rather than persisting a fabricated citation. TRD section 28 makes page/section provenance best-effort.
- `mark_analyzed` is now called on success, closing the gap F10 left open: the next run skips an unchanged paper unless `--force` or `classify --reanalyze` is used.
- `research-agent analyze --topic <id> [--run] [--limit] [--force]` analyses a run's selected papers under `concurrency.analysis`, prints status and depth per paper, and records a `MODEL_API_ERROR` per failure. A stored analysis short-circuits; `--force` re-runs it.
- `analysis/cards.py` renders the PRD section 12 card with a deterministic field order, omitting sections the analysis has nothing to say about. Every value is model- or provider-supplied, so all of it is collapsed to one line and stripped of backticks before rendering.

**Files and interfaces**

- New: `src/research_agent/analysis/{__init__,prompts,analyzer,cards}.py`, `tests/unit/test_analysis_{analyzer,cards}.py`, `tests/integration/test_analyze_cli.py`.
- Modified: `src/research_agent/domain/analysis.py` (`AnalysisDraft`; `prompt_version` and `abstract_only` on `PaperAnalysis`); `src/research_agent/config.py` (`AnalysisSettings`, and the NIM model default); `src/research_agent/cli.py` (`analyze`); `src/research_agent/documents/parser.py` (`load_parsed`); `config/settings.yaml`.
- No migration: `paper_analyses` stores the model as `payload_json`, so the two new fields need no schema change. `prompt_version` is required, which is safe because no analysis row existed before this branch.
- `ParsingService.load` now delegates to a module-level `load_parsed(store, paper_id, topic_id)`, so `analyze` reads stored parses without constructing a parser it would never use — and therefore without importing Docling.

**Decisions and why**

- **The NIM slot is configured properly, not stubbed.** `strong_model_provider: nvidia_nim` in `config/settings.yaml`. Analysis requests `deep_reasoning`, which TRD section 26 fixes to the strong provider, so this finally exercises the real split rather than a mock, and a card now records `nvidia_nim/openai/gpt-oss-20b` as its author.
- **Which model, and why it took four tries.** The strong model had to answer and honour JSON mode. Probed on this account: `meta/llama-3.1-70b-instruct` → HTTP 410 Gone (the old baked-in default, now dead); `deepseek-ai/deepseek-v4.1-flash` → no response within 180s on even a trivial prompt; `nvidia/nemotron-3.5-lightning-30b-a3b` → answers in 8s but writes its chain of thought into `content` and ignores `response_format`, so its reply is never valid JSON; `z-ai/glm-5.3-flash` → valid JSON but ~95s on a trivial prompt and it failed the real analysis prompt. `openai/gpt-oss-20b` answers, honours JSON mode, and keeps its reasoning in the separate `reasoning_content` field the adapter already ignores, so it is configured in both slots for now. `NimEndpointSettings.model` was corrected from the 410 default to the same model; a dead default is not behavior, so it did not warrant its own branch.
- **`max_output_tokens` raised to 4096 in both slots.** A full paper analysis does not fit in the 2048-token default, and a truncated reply is invalid JSON, so the run failed validation rather than producing a short analysis. This is a correctness setting, not tuning, and it is recorded in `config/settings.yaml` with that comment.
- **Repair is not retried here.** The TRD gives the single repair retry to Classifier B alone; analysis uses the F6 contract, so malformed output raises `ModelValidationError` on the first call and becomes a failed outcome without a second request. Verified by asserting exactly one request was sent.
- **Every failure is an outcome, never an exception**, matching F11 acquisition and F12 parsing: one paper's provider failure leaves the rest analyzed and records one error row.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 110 source files.
- `uv run pytest` → 400 passed, 3 deselected; coverage 93.50% (gate 85%).
- `uv run research-agent config validate` → valid.
- `uv run research-agent model check` → local `openai/gpt-oss-20b` ready; `nvidia_nim` reports its key as configured (presence only, never the value).
- `uv run research-agent analyze --topic embodied_spatial_intelligence` → 4 of 4 papers analyzed: 2 from parsed full text, 2 abstract-only (no PDF was acquired for those), with cards on disk and four `paper_analyses` rows. Cards run 2.7-4.3 KB.
- **The fallback path ran for real, not against a mock.** During the first live pass the strong provider timed out, the router retried it twice per paper and then degraded to local inference, and all four analyses still completed. That is the first genuine exercise of the NIM-retry-then-local-fallback branch.
- After the strong slot was pointed at a JSON-capable model, `analyze --force --limit 1` produced an analysis served by the strong provider itself: `paper_analyses.model_provider = nvidia_nim`.

**Known issues and next step**

- NIM currently fills both the local and the strong slot, because no local runtime is installed. The fallback branch did run for real (see above), but only because the strong model was temporarily unreachable; installing Ollama and reverting the four `MODELS__LOCAL__*` lines in `.env` is what would make the split genuine rather than incidental.
- `.env` holds the only copy of the API key; it is gitignored and no key material reached the repository, the log, this file, or any card.
- **Next recommended step:** F14 cross-paper synthesis — `WeeklySynthesis` has existed since F4 with no producer, `recent_syntheses` supplies the four-period history window the PRD asks to compare against, and the stored analyses this branch writes are its input.

## 2026-09-24 — F12 PDF parsing (complete, merged)

- **Feature/branch:** `F12-pdf-parsing`.
- **Commits:** `3675650` feat(documents): add structured PDF parsing; merged as `ec86cc5`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline, under `-m slow`, and against both real arXiv papers.

**Behavior added**

- `ParsedPaper` and its `ParsedSection` / `ParsedTable` / `ParsedFigure` / `ParsedReference` parts (TRD §22), with a `text` property that renders body text as Markdown headings for F13's prompt.
- `DoclingParser` is the only module that imports Docling, and it imports lazily inside the constructor so the rest of the suite never loads torch. It folds body text under the heading that precedes it, routes anything under a references heading into `ParsedReference` instead of body text, and records `parser_name`/`parser_version`.
- `ParsingService` owns everything backend-independent: caching, storage, and failure isolation. A parse failure becomes a `ParseOutcome` with status `failed` and never raises, leaving the paper eligible for abstract-only analysis in F13.
- Each parse writes two artifacts through `LocalArtifactStore`: `<paper_id>.md` for a human and `<paper_id>.json` for the analyzer, and records the Markdown in `paper_files` as `FileKind="parsed"`. `ParsingService.load` reads the JSON back.
- `research-agent parse --topic <id> [--run] [--limit] [--force]` parses the run's acquired PDFs, prints status, section count and path per paper, and records a `PDF_PARSE_ERROR` per failure.

**Files and interfaces**

- New: `src/research_agent/domain/documents.py`, `src/research_agent/documents/{parser,docling_parser}.py`, `tests/unit/test_documents_parser.py`, `tests/integration/test_{docling_parser,parse_cli}.py`, `tests/fixtures/documents/sample.pdf`.
- Modified: `pyproject.toml` (Docling, the Python floor, the `slow` marker); `src/research_agent/cli.py` (`parse`).
- Modified: `.gitignore` — one negation, `!tests/fixtures/documents/*.pdf`, so the deliberately approved sanitized fixture is committed while `*.pdf` stays ignored everywhere else.
- No migration: `paper_files` and `FileKind="parsed"` have existed since F4.

**Decisions and why**

- **Dependency:** `docling>=2.130,<3`, resolving 2.130.0 plus 80 packages including `torch` 2.14 (~2.5 GB). Accepted deliberately: the roadmap names Docling, and the structure it recovers (sections, tables, figures, references) is what F13's claim provenance and the PRD's paper cards need. `docling-slim` (25 packages, no torch) and `pypdf` (1 package, no structure) were the alternatives considered.
- **Deviation, documented:** `requires-python` moved from `>=3.11` to `>=3.12`, and mypy's target with it. Docling's transitive numpy stubs use 3.12-only `type` syntax and cannot be parsed at a 3.11 target; `follow_imports = "skip"` did not suppress it. AGENTS.md allows deviating from the 3.11 baseline with a documented constraint, and this is that constraint. The 3.11 floor was never exercised here anyway — the venv has been 3.14 since F1.
- Docling's `typer` downgrade (0.27.2 → 0.26.8) was verified harmless before any parser code was written: the full suite passed on it.
- Real Docling tests are **deselected, not skipped**: `addopts` carries `-m 'not slow'` and the marker is registered, so `uv run pytest -m slow` runs them explicitly and the default suite never pretends they ran.
- Two defects were found by running a real paper and fixed: `export_to_dataframe()` was called without the document (a deprecation warning per table), and the title fell back to `None` because Docling labels a paper's title as the first `section_header` rather than a `title` item.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 103 source files.
- `uv run pytest` → 378 passed, 3 deselected; coverage 93.33% (gate 85%).
- `uv run pytest -m slow` → 3 passed (the real Docling adapter over the committed fixture).
- `uv run research-agent parse --topic embodied_spatial_intelligence` → both real arXiv papers parsed: 61 and 36 sections, 94 KB and 60 KB of Markdown, 175 KB and 91 KB of JSON. An earlier direct run of the larger paper also recovered 28 tables, 6 figures and 72 references.

**Known issues, risks, and unavailable validation**

- **Docling downloads model weights on first use** (~20 MB of RapidOCR models) into the virtualenv. `pytest -m slow` therefore needs network the first time it runs on a fresh checkout. Nothing is committed; the weights live under `.venv`.
- Parsing is slow: roughly 60–90 seconds per full paper on this machine, single-threaded. `ParsingService` is deliberately synchronous and sequential; if that becomes a bottleneck, bounding it with `concurrency.analysis` is the obvious next step.
- The committed fixture PDF is minimal and has no real font hierarchy, so Docling flattens it into one section. It exercises the adapter's plumbing, not its structure recovery; structure was verified by hand against the real papers instead.
- `record_file` stores an empty sha256 for parsed artifacts. The PDF's hash is what caching keys on, so this is unused today, but it is a placeholder rather than a real value.
- Only 2 of 4 selected papers have PDFs at all (F11's open-access reality), so F13 will analyze two full texts and two abstracts.

**Next recommended step:** F13 (`F13-paper-analysis`) as planned: versioned analysis prompt, full-text input from `ParsingService.load` with abstract-only fallback, claim provenance validated against real sections, `mark_analyzed` finally called, and the Markdown paper card. Configure the NIM slot properly first (`strong_model_provider: nvidia_nim` with `deepseek-ai/deepseek-v4.1-flash` or `nvidia/nemotron-3.5-lightning-30b-a3b`) so analysis exercises the real strong/local split.


## 2026-09-24 — FIX1 test environment isolation (complete, merged)

- **Feature/branch:** `FIX1-test-env-isolation`.
- **Commits:** `383bf36` fix(tests): isolate the suite from ambient settings; merged as `610f8ff`.
- **Status:** Complete, merged, and re-verified on `main`.

**The defect**

`ApplicationSettings` reads `.env` and the process environment ahead of any YAML a caller supplies (`settings_customise_sources`, F1). Correct for the application, wrong for the suite: creating the first real `.env` in this repository redirected 27 tests at the developer's own `data/` directory, endpoints, and credentials. Latent since F1; it surfaced only because no `.env` had ever existed here. Any contributor with one would have seen the same failures.

Found while starting `F12-pdf-parsing`: the Docling install was initially suspected, but with `.env` moved aside all 359 tests passed, which isolated the real cause. F12 was parked and this fix taken on its own branch per the AGENTS.md workflow.

**The fix**

- New `tests/conftest.py` with an autouse fixture that deletes every `RESEARCH_AGENT_*` variable for the duration of a test and sets `ApplicationSettings.model_config["env_file"] = None`, disabling the dotenv source. Test-side only; no production code changed.
- `tests/unit/test_environment_isolation.py` asserts the contract directly: no prefixed variables visible, the dotenv source disabled, a supplied `data_directory` not overridden, and `models.local.api_key` unset despite a real key sitting in `.env`.
- `tests/{,unit/,integration/}__init__.py` added, because two `conftest.py` files collided on the module name under strict mypy. Imports changed from `from conftest import ...` to `from tests.unit.conftest import ...` across 18 modules — mechanical, no behavior change.

**Decisions and why**

- Neutralizing the env sources beats `monkeypatch.chdir`: two tests legitimately read the repository's own `config/settings.yaml`, and changing the working directory would have broken them.
- `explicit_package_bases`/`mypy_path` were tried first for the conftest collision and rejected — they broke `src`-layout resolution and produced 311 spurious errors. Package markers are the standard answer.
- The fixture is autouse and unconditional. An opt-in fixture would leave the next new test file exposed to the same failure.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 97 source files.
- `uv run pytest` → 363 passed (4 new), coverage 96.79% (gate 85%) — **with the real `.env` present**, which is the condition that failed before.
- Confirmed the same suite passes with `.env` moved aside, so the fix is not merely masking the ordering.

**Known issues, risks, and unavailable validation**

- The fixture reaches into `ApplicationSettings.model_config`, which is pydantic-settings internal structure. It is asserted directly by a regression test, so a library change that breaks it fails loudly rather than silently restoring the leak.
- `.env` itself remains uncommitted and gitignored; no key material reached the repository, the log, or this file.

**Next recommended step:** resume `F12-pdf-parsing` from clean `main`, re-adding `docling>=2.130,<3`. The earlier install was verified harmless: with `.env` aside, the full suite passed on Docling's `typer` 0.26.8 downgrade, so that dependency is not blocked. Note the venv currently holds no Docling (it was reverted with `uv sync`).


## 2026-09-24 — Live inference validation (no code change)

- **Task:** first real end-to-end validation of F6, F7, and F9 against a hosted OpenAI-compatible endpoint. No branch, no commit; this entry records verification and the defects it surfaced.
- **Setup:** NVIDIA NIM standing in for the local runtime. Because TRD §26 routes `cheap_text` and `classification` to the *local* provider, `models.local.base_url` was pointed at `https://integrate.api.nvidia.com/v1` in the uncommitted `.env`. Model: `openai/gpt-oss-20b`, 1 request/second.

**What was validated for the first time**

- **F6 router:** `model check` → `local openai/gpt-oss-20b 668ms`, reply "ready". The `/chat/completions` wire format, bearer auth, latency capture, and token parsing all work against a real endpoint.
- **F6 structured output:** `response_format={"type":"json_object"}` is honoured and returns clean JSON in `message.content`. The model's reasoning trace arrives in a separate `reasoning_content` field, which `_content()` ignores, so no thinking text leaks into validation. This was the single biggest unverified assumption.
- **F7 query expansion:** produced 12 distinct queries with no fallback, base query first, sorted and deduplicated. Previously only the degraded path had ever run.
- **F9 Classifier B:** 5 real verdicts in shadow mode, no repair retries needed, all schema-valid on the first reply. Average latency 7331 ms per paper against 0 ms for lexical Classifier A.
- **F9 comparison:** first run over genuine paired verdicts — **agreement rate 1.00 across 5 papers** (identical action and relevance on every one). Classifier B's `reason_short` values are specific and correct, e.g. rejecting an organisational-transformation paper as "not spatial intelligence".

**Defects and findings**

- **`NimEndpointSettings.model` default is dead.** `meta/llama-3.1-70b-instruct` returns HTTP 410 Gone; the platform retired it. Worth a `FIX` branch to change the default and document that model ids must be checked against the account.
- Most ids returned by `/v1/models` are not entitled to a given account and return 404 with a "Function ... not found for account" body. Four of the twelve ids probed answered: `openai/gpt-oss-20b`, `z-ai/glm-5.3-flash`, `deepseek-ai/deepseek-v4.1-flash`, and `nvidia/nemotron-3.5-lightning-30b-a3b`. The listing is not a capability list, so any model id must be probed before it is configured. The latter two are candidates for the strong-capability slot in F13.
- Classifier A's confidence is visibly cruder than B's: A gave 0.1 confidence to a paper it scored 0.625 (near its own threshold) where B gave 0.92. The F8 note about uncalibrated confidence is confirmed by real data.
- Classifier A's reported average latency is 0 ms because lexical scoring times a whole batch in under a millisecond. Accurate, but it makes the latency column in `compare-classifiers` uninformative for A.

**Still not validated**

- **The local fallback branch.** With NIM in both the local and strong slots, "fall back to local" means falling back to NIM. That route remains mock-only.
- **A genuinely small model.** `gpt-oss-20b` is far stronger than the `qwen3:8b`-class model the TRD specifies for Classifier B. Prompts that succeeded first-try here may still need the repair retry, or tuning, on a small local model.
- The repair retry, provider-failure, and cancellation paths remain mock-only; nothing failed during this sweep.
- Classifier A's embedding half is still unexercised; no embedding model is configured.

**Next recommended step:** unchanged — F12 (`F12-pdf-parsing`), gated on locking a Docling version compatible with this machine's Python 3.14.6. Note that NIM also exposes `nvidia/nemotron-parse` and `nvidia/nemotron-parse-2.0`, which may be worth comparing against Docling before committing to a heavy local dependency. A `FIX` branch for the dead NIM default model is small and can be done at any time.


## 2026-09-24 — F11 PDF acquisition (complete, merged)

- **Feature/branch:** `F11-pdf-acquisition`.
- **Commits:** `507e122` feat(documents): add legal PDF acquisition; merged as `f964d99`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline and against live arXiv: two real PDFs downloaded and stored.

**Behavior added**

- `PdfDownloader` implements the `DocumentAcquirer` protocol, so F12 and the graph depend on an interface rather than on httpx.
- `pdf_candidates(paper)` is pure and ordered: arXiv derived from `arxiv_id` first, then each source's reported `pdf_url` in a fixed source order (`openalex`, `semantic_scholar`, `arxiv`), deduplicated, `http` upgraded to `https`, and every other scheme dropped. Two runs over the same paper request the same URL first.
- Only open-access locations the sources themselves reported, plus arXiv's public PDF endpoint, are ever requested. There is no publisher-page scraping, no paywall probing, and no bypass fallback of any kind.
- Every response is validated before it can reach disk: status, content type (`application/pdf` or an octet-stream), the `%PDF-` signature, and a size cap. The body is streamed in 64 KiB chunks and abandoned the moment `documents.max_pdf_bytes` is exceeded, so an oversize or mislabeled file is never fully buffered.
- Four outcomes, and nothing raises into the caller: `stored`, `cached` (a file already exists, no request made), `unavailable` (no legal URL — not a failure), `failed` (every candidate exhausted). A failing paper keeps its metadata and stays in the run.
- Retries follow `retries.pdf_download` (2) with exponential backoff, applied only to 429/5xx and transport errors; 4xx is never retried. Downloads run under `concurrency.downloads` with a shared `RateLimiter`.
- Storage is deterministic: `<canonical_id>.pdf` under `data/topics/<topic>/papers/`, written atomically by `LocalArtifactStore`, recorded in `paper_files` with size and sha256.
- `research-agent acquire --topic <id> [--run <id>] [--limit]` reads the selected set from the run's `selections` rows (defaulting to the most recent run), prints a per-paper line plus a status summary, and records one `ErrorRecord` per failure so failures stay visible in the run.

**Files and interfaces**

- New: `src/research_agent/documents/{urls,downloader}.py`, `tests/unit/test_documents_{urls,downloader}.py`, `tests/integration/test_acquire_cli.py`.
- Modified: `src/research_agent/config.py` (`DocumentSettings`); `src/research_agent/cli.py` (`acquire`, `_acquire`, `_latest_run`); `config/settings.yaml`; `tests/unit/test_config.py`.
- No migration: `paper_files` and `FileKind = "pdf"` have existed since F4.

**Decisions and why**

- The downloader is new code under `documents/` rather than an extension of `discovery/http.py`: PDFs need streamed bytes with an early abort, which a text helper capped at 8 MiB cannot express. `RateLimiter` is reused by import. That module is now a fourth consumer, which is exactly the trigger its own `ponytail:` note names for moving it to `utils/http.py` — still deliberately deferred to a `REFACTOR` branch, because AGENTS.md forbids mixing a refactor into a feature.
- `unavailable` and `failed` are distinct statuses. A paper with no open-access URL is a legal outcome, not an error, and should not pollute the run's error count.
- Acquisition is its own command rather than a fourth stage of `classify`: a triage preview should not hit publisher sites, and a rate-limited attempt can be re-run without re-discovering.
- The cached check is a filesystem check, so a re-run after a partial pass costs nothing.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 92 source files.
- `uv run pytest` → 359 passed; total coverage 96.79% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent acquire --topic embodied_spatial_intelligence` → "4 paper(s) for run 13cc5d33562643c5bed348aad70483da: stored 2, unavailable 2". Both arXiv papers downloaded (4.4 MB and 6.5 MB), verified to start with `%PDF-1.7`, and recorded in `paper_files` with their byte sizes. The two publisher DOIs reported no open-access URL and were correctly marked `unavailable`.

**Known issues, risks, and unavailable validation**

- No live download has yet exercised the retry, redirect, or oversize paths; those are covered only by `httpx.MockTransport`. The arXiv downloads succeeded on the first attempt.
- `documents.max_pdf_bytes` is 25 MiB. The two real PDFs were well under it, so the cap has not been hit in practice.
- OpenAlex reports no `pdf_url` for the two publisher papers in this topic, so roughly half a real selection currently yields no document. That is the expected open-access reality, not a defect, but it means F12 will parse fewer papers than are selected.
- Downloaded PDFs live under `data/`, which is gitignored; nothing was committed.
- Classifier B remains unproven against a real model (F9), and nothing calls `mark_analyzed` until F13 (F10).
- The CLI still never calls `observability.logging.configure_logging`, so the downloader's per-candidate warnings print as plain text. Still a `CHORE` candidate.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests remains unowned.

**Next recommended step:** F12 (`F12-pdf-parsing`): a document-parser interface with a Docling adapter, `ParsedPaper`/section/table/figure/reference schemas, parser name and version provenance, normalized Markdown written through the artifact store as `FileKind = "parsed"`, cache lookup keyed on the unchanged source PDF, and an explicit abstract-only fallback marker when parsing fails. Note that Docling is a new, heavy dependency — confirm it is acceptable before that branch begins, and keep any large or platform-specific tests marked rather than silently skipped.


## 2026-09-24 — F10 paper selection (complete, merged)

- **Feature/branch:** `F10-paper-selection`.
- **Commits:** `2cbc90b` feat(selection): add bounded paper selection; merged as `8edcfcd`.
- **Status:** Complete, merged, and re-verified on `main`. Verified offline and against live OpenAlex.

**Behavior added**

- `select(verdicts, limits, settings, analyzed, reanalyze) -> SelectionPlan` is pure: no clock, no database, no network, so the same verdicts and limits always produce the same reading set.
- Ranking is a total order: action (`deep_read` > `summarize` > `ignore`), then relevance, then `relevance_score` descending, then `confidence` descending, then `paper_id` ascending. The final key is an identifier, so ties can never reorder between runs.
- Every classified paper gets exactly one `SelectionDecision` with a rank, a selected flag, its action, and a `SelectionReason` value (`selected_deep_read`, `selected_summarize`, `action_ignore`, `below_threshold`, `already_analyzed`, `limit_reached`). Skipped papers stay auditable.
- Limits are enforced: `max_deep_reads` bounds deep reads and `max_downloads` bounds the whole selection. A deep-read paper past the deep-read cap is downgraded to `selected_summarize` rather than dropped, and the decision keeps both its action and its reason so the downgrade is visible.
- Seen-paper policy (TRD §20): `papers` gained `content_hash`, `analyzed_hash`, `first_analyzed_at`, and `last_analyzed_at`. `mark_analyzed` freezes the hash that was analyzed; `analyzed_unchanged` returns papers already analyzed whose content still matches. A revision or an edited abstract changes `content_hash`, which makes the paper eligible again, as does `classify --reanalyze`.
- `classify` now prints `selected N of M: D deep read, S summarize.` plus a rank/decision/reason line per paper, persists the plan to `selections`, and records `papers_selected` and `deep_reads` on the run.

**Files and interfaces**

- New: `src/research_agent/domain/selection.py`, `src/research_agent/selection/{__init__,selector}.py`, `src/research_agent/storage/selections.py`, `tests/unit/test_selection_selector.py`, `tests/unit/test_storage_selections.py`.
- Modified: `src/research_agent/storage/database.py` (schema 18 → 22: four `papers` columns and the `selections` table, one statement per `MIGRATIONS` entry); `src/research_agent/discovery/normalize.py` (`content_hash`); `src/research_agent/storage/papers.py` (`content_hash` stored on upsert, `mark_analyzed`, `analyzed_unchanged`); `src/research_agent/config.py` (`SelectionSettings`); `src/research_agent/cli.py` (`classify --reanalyze`, selection output, plan persistence); `config/settings.yaml`; `tests/unit/test_storage_{papers,migrations}.py`, `tests/unit/test_config.py`, `tests/integration/test_classify_cli.py`.

**Decisions and why**

- A `selections` table rather than run-summary JSON: a threshold change must not silently rewrite what a past run did, and "why was this paper dropped" has to be answerable per paper. F11 reads its input from `selected_for(run_id)`.
- **Deviation from the approved plan:** the plan listed three new `papers` columns; a fourth, `analyzed_hash`, was needed. Comparing `content_hash` to itself can never detect a change, so the hash at analysis time is frozen separately and compared against the current one. Schema is 22 rather than the planned 21.
- Selection folds into `classify` rather than getting its own command: a run is already closed when it is written, so a separate `select --run` would mean either mutating a finished run or inventing a second one.
- Thresholds are configuration (`selection.min_relevance_score`, `selection.require_action`) while the caps stay per topic in `ResourceLimits`, which is where the PRD puts them.
- Only active-classifier verdicts reach `select`; shadow rows are persisted but never passed in.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 87 source files.
- `uv run pytest` → 332 passed; total coverage 96.91% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent classify --topic embodied_spatial_intelligence --limit 5` → 5 live OpenAlex papers classified, "selected 4 of 5: 1 deep read, 3 summarize", the fifth skipped as `action_ignore`, run `13cc5d33562643c5bed348aad70483da` saved with the plan.

**Known issues, risks, and unavailable validation**

- The seen-paper path has been exercised only through the integration test and unit tests; no real run has yet called `mark_analyzed`, because nothing analyzes papers until F13. Until then `analyzed_unchanged` always returns empty in practice.
- `min_relevance_score` (0.3) interacts with Classifier A's untuned thresholds from F8. On the live run every non-ignored paper cleared it, so the gate has not actually excluded anything yet.
- Classifier B remains unproven against a real model, unchanged from F9; shadow verdicts are still never produced locally.
- Semantic Scholar 429 and arXiv 406 persist from F5; OpenAlex answered.
- The CLI still never calls `observability.logging.configure_logging`; the "classification failed; the paper is skipped" line in the live run is a plain-text warning for exactly this reason. Still a `CHORE` candidate.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests remains unowned.

**Next recommended step:** F11 (`F11-pdf-acquisition`): an async downloader behind a document-acquisition interface, reading its input from `SqliteSelectionRepository.selected_for(run_id)`, with open-access URL policy, content-type and signature validation, a configurable size cap, deterministic filenames, atomic writes through the F4 artifact store, two download retries, and per-paper failure isolation that keeps metadata-only papers in the run.


## 2026-09-23 — F9 classifier B and shadow mode (complete, merged)

- **Feature/branch:** `F9-classifier-b-shadow-mode`.
- **Commits:** `2d5cf41` feat(classifiers): add classifier B and shadow execution; merged as `d6758af`.
- **Status:** Complete, merged, and re-verified on `main`. Classifier B has not run against a real model; see known issues.

**Behavior added**

- `ClassifierB` classifies through `ModelRouter.generate("classification", ..., ClassifierVerdict)` and never touches a provider. Malformed structured output is repaired exactly once with `REPAIR_INSTRUCTION`; a second failure raises `ClassifierError` with `INVALID_CLASSIFIER_OUTPUT` and costs no further calls.
- `ClassifierVerdict` is the six-field schema a model may produce. `paper_id`, `classifier_name`, and `latency_ms` are filled in by the adapter, so a model can never supply its own provenance.
- Batches run with bounded concurrency (`concurrency.analysis`); a paper that fails is logged and skipped rather than ending the batch.
- Prompts are versioned (`classification.v1`) and the abstract is truncated at `classifier_b.max_abstract_chars` (default 2000) with the truncation stated in the prompt.
- `build_classifier(name, client, settings)` (TRD §13) is the only place either implementation is constructed; `"A"`/`"B"` are case-insensitive and anything else raises.
- `ClassifierRunner` runs the active classifier, then the shadow inside a catch-all. A shadow failure is logged, recorded on `ClassifierOutcome.shadow_error`, and never reaches routing. Shadow verdicts persist with `is_active = 0`.
- `research-agent classifier set A|B --topic <id> [--shadow A|B|none]` switches a topic's classifiers; validation reuses `ClassifierSettings`, so a shadow equal to the active one is rejected before the write.
- `research-agent compare-classifiers <topic_id> [--runs N]` and `python scripts/compare_classifiers.py <topic_id> [runs]` report agreement rate, disagreement count, average latency and confidence, and action/relevance distributions from stored verdicts. Both call the same pure `compare`/`render`.

**Files and interfaces**

- New: `src/research_agent/classifiers/{prompts,classifier_b,factory,runner,comparison}.py`, `scripts/compare_classifiers.py`, `tests/unit/test_classifiers_{b,factory,runner,comparison}.py`, `tests/integration/test_classifier_cli.py`.
- Modified: `src/research_agent/classifiers/base.py` (`Provenance`, `explain_many` promoted into the protocol); `src/research_agent/domain/analysis.py` (`ClassifierVerdict`); `src/research_agent/config.py` (`ClassifierBSettings`); `src/research_agent/storage/results.py` (`classification_pairs`); `src/research_agent/storage/topics.py` (`set_classifier`); `src/research_agent/cli.py` (`classify` now runs through the factory and runner and saves shadow rows; two new commands); `config/settings.yaml`; the three affected test modules.
- No migration: `classifications.is_active` and the topics classifier columns have existed since F2/F4.

**Decisions and why**

- The repair retry lives in Classifier B, not the router. `ModelRouter._validated` raises `ModelValidationError` and deliberately never retries (F6), which is exactly what lets the classifier own the one repair the TRD allows.
- `compare-classifiers` reads stored verdicts rather than re-classifying: the numbers were already recorded by shadow mode, so the report needs no model and is reproducible. Agreement is measured on `action`, because that is what controls the run.
- Agreement is computed only over papers both classifiers judged; comparing different sets would not be a comparison.
- `explain_many` was promoted into the protocol so the runner and the CLI persist provenance without knowing which implementation they hold.
- Shadow isolation lives in the runner alone, so no call site can forget it.
- `classifier set` is per topic and requires `--topic`, because that is where the setting already lives; no application-level duplicate was introduced.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 81 source files.
- `uv run pytest` → 302 passed; total coverage 96.74% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent classifier set A --topic embodied_spatial_intelligence --shadow B` → "active A, shadow B", persisted.
- `uv run research-agent classify --topic embodied_spatial_intelligence --limit 3` → **3 real OpenAlex papers classified by Classifier A** (`high/deep_read` for one, `medium/summarize` for two), run `8b97ab13d9a14aedb1a55c0ffc0c7a7a` saved. This closes F8's open item: Classifier A has now scored live discovery results.
- `compare-classifiers` and `scripts/compare_classifiers.py` both exit 1 with "No shadow verdicts stored", which is correct: Classifier B produced nothing without a local model.

**Known issues, risks, and unavailable validation**

- **Classifier B has never run against a real model.** Every path is covered by `httpx.MockTransport`, but no local runtime is installed here, so prompt wording, repair behavior, and verdict quality are unproven. Install one (`ollama serve` plus a `qwen3:8b`-class model) and re-run `classify` with a shadow before trusting B.
- Because per-paper failures are isolated inside `ClassifierB`, a completely unavailable model yields "shadow classifier B: 0 verdict(s)" rather than a single loud error; the reason appears in the per-paper warnings. `ClassifierOutcome.shadow_error` only fires for a batch-level failure.
- The comparison has therefore never been produced from real paired verdicts — only from mocked ones in tests.
- Semantic Scholar 429 and arXiv 406 persist from F5. OpenAlex answered this time.
- The CLI still never calls `observability.logging.configure_logging`, so classifier warnings print as plain text. Unchanged since F6; still a `CHORE` candidate, and it matters more now that shadow failures are only visible in logs.
- `discovery/http.py` still holds the shared retry helper with its `ponytail:` note; moving it to `utils/http.py` remains a `REFACTOR` branch.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests remains unowned.

**Next recommended step:** F10 (`F10-paper-selection`): deterministic ranking and tie-breaking over active-classifier verdicts, configurable relevance/action thresholds, enforcement of the candidate/classification/download/deep-read limits, seen-paper lookup with first/last seen and analyzed timestamps, and auditable selection reasons. It depends only on F4 and F9, both of which are now merged.


## 2026-09-22 — F8 classifier A integration (complete, merged)

- **Feature/branch:** `F8-classifier-a-integration`.
- **Commits:** `63731c6` feat(classifiers): integrate classifier A; merged as `a43fede`.
- **Status:** Complete, merged, and re-verified on `main`. Live discovery was rate-limited during the manual check; see known issues.

**Behavior added**

- `PaperClassifier` protocol (TRD §10) with `classify` / `classify_many`, plus `ClassifierError` carrying the `CLASSIFIER_ERROR` / model error categories.
- `ClassifierA` produces only the normalized `ClassificationResult`: relevance, relevance score, paper type, action, confidence, reason, and latency. It is deterministic and offline by default.
- Scoring is lexical: topic name (weight 2) and each keyword (weight 1) matched against the normalized title and abstract, exact title > fuzzy title > exact abstract > fuzzy abstract, with individual name tokens contributing to the numerator only so a long topic name does not raise the bar for matching it. RapidFuzz supplies the near-match floor; no new dependency.
- When `classifier_a.embedding_model` is set, `EmbeddingClient` embeds the topic and the whole batch in one `/embeddings` request and the score becomes `(1 - w) * lexical + w * cosine`. Any embedding failure logs one structured warning and falls back to the lexical verdict — it never fails a paper or a run.
- `paper_type` comes from an ordered cue table (`survey` → `benchmark` → `dataset` → `application` → `method`, else `other`); first match wins, so it is reproducible.
- `explain_many` returns each verdict with the audit payload (`version`, `lexical_score`, `embedding_score`, `embedding_weight`, `matched_terms`) that is stored in the existing `classifications.raw_response_json`.
- `research-agent classify --topic <id> [--query] [--days] [--limit] [--no-save]` discovers and triages in one command. With `--save` it starts a run, upserts each paper, stores every verdict, and completes the run as `degraded` when any source failed.

**Files and interfaces**

- New: `src/research_agent/classifiers/{base,lexical,embeddings,classifier_a}.py`, `tests/unit/test_classifiers_{lexical,embeddings,a}.py`, `tests/integration/test_classify_cli.py`.
- Modified: `src/research_agent/config.py` (`ClassifierASettings` and the `classifier_a` field); `src/research_agent/cli.py` (`classify`, `_classify`, `_embedder`, `_save_classifications`); `config/settings.yaml`; `tests/unit/test_config.py`; `tests/unit/test_storage_results.py`.
- No migration: `classifications` has existed since F4 and `SqliteResultRepository.save_classification` was already the right seam.

**Decisions and why**

- **Deviation from the roadmap prerequisite, recorded deliberately.** `docs/FEATURE_ROADMAP.md` F8 requires obtaining the pre-existing Jev-style Classifier A before the branch begins and forbids inventing one. It is not available in this repository, and the user directed me to implement it instead. Nothing here is trained or fine-tuned, which the product guardrails forbid; it is a deterministic decision classifier. Per TRD §11, swapping in a real implementation should change only `classifier_a.py`.
- **The protocol is async**, unlike the synchronous sketch in TRD §10. Classifier B must await `ModelRouter` in F9 and Classifier A awaits embeddings; one async contract serves both, and a sync protocol serves neither.
- **Relevance and action share two thresholds** (`summarize_at`, `deep_read_at`). Two independent knob sets can contradict each other and there is no evidence yet to separate them.
- **Confidence is the distance to the nearest decision boundary**, saturating at 0.25. It is honest about certainty near a threshold; a calibrated probability would need labelled data that v1 does not collect. Marked with a `ponytail:` comment.
- **Provenance goes in `raw_response`, not `classifier_name`**, so a stored verdict can be re-read and re-tuned without parsing a name string.
- **Batch embeddings, not per-paper.** One request per batch keeps the optional path cheap and preserves the TRD's batch-support requirement.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean (72 files).
- `uv run mypy` → Success: no issues found in 71 source files.
- `uv run pytest` → 257 passed; total coverage 96.66% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent classify --topic embodied_spatial_intelligence --limit 5 --days 30` → exit 0, run `12176160b9f1464ea8f3163399602d93` persisted with status `degraded`, `models_used: ["lexical"]`, `errors: 3`. All three sources were rate-limited at the time (OpenAlex 429, Semantic Scholar 429, arXiv 406), so zero candidates reached the classifier.

**Known issues, risks, and unavailable validation**

- **Classifier A has never scored a live discovery result.** Every source returned 429/406 during the manual check, so real-paper triage is covered only by the mocked integration test. Re-run `research-agent classify` when OpenAlex is not rate-limiting this machine before trusting the thresholds.
- The embedding path has never run against a real embedding server; only `httpx.MockTransport` has exercised it. `classifier_a.embedding_model` is unset by default, so the shipped behavior is purely lexical.
- The default thresholds (0.3 / 0.6) are untuned guesses. They are configuration, so tuning needs no code change, but they should be revisited against real verdicts in F10.
- OpenAlex now also returns 429 for this machine's usage pattern, which is new since F7; the arXiv 406 and Semantic Scholar 429 are unchanged from F5.
- The CLI still never calls `observability.logging.configure_logging`, so the classifier's degradation warning prints as plain text rather than JSON. Unchanged since F6 and still worth a `CHORE` branch.
- `discovery/http.py` now has its third consumer, which is the trigger its own `ponytail:` note names for moving it to `utils/http.py`. That is a `REFACTOR` branch, deliberately not mixed into this feature.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests remains unowned.

**Next recommended step:** F9 (`F9-classifier-b-shadow-mode`): the Qwen-style classifier over `ModelRouter.generate("classification", ...)` with a versioned structured prompt, Pydantic validation and the one repair retry the TRD allows, the A/B factory, shadow execution persisted with `is_active=false`, and `compare-classifiers`. It needs a local runtime to be exercised, so install one (`ollama serve` plus a `qwen3:8b`-class model) first. Alternatively, F10 (`F10-paper-selection`) is unblocked by Classifier A alone.


## 2026-09-22 — F7 search query planning (complete, merged)

- **Feature/branch:** `F7-search-query-planning`.
- **Commits:** `53a6cd4` feat(queries): add semantic search planning; merged as `8c2b6d2`.
- **Status:** Complete, merged, and re-verified on `main`. Verified end to end offline and against live OpenAlex.

**Behavior added**

- `QueryPlanner.plan(topic, history)` expands a topic through `ModelRouter.generate("cheap_text", ..., ExpandedQueries)` and never touches a provider directly. Any `ModelProviderError`, including `ModelValidationError`, degrades to the deterministic plan with `fell_back=True` and one structured warning; the planner cannot fail a run.
- `base_query(topic)` is pure: normalized topic name plus its first two keywords, always the first entry of a plan, with the topic id as a last resort so a plan is never empty.
- Determinism lives in the planner, not the model: expansions are normalized with `normalize_text`, stripped of anything shorter than three characters, deduplicated case-insensitively, sorted, padded from topic keywords up to `min_queries`, and truncated at `max_queries`. Two runs with the same inputs produce identical plans regardless of the order the model answered in.
- `QueryPlan` records `prompt_version`, provider, model, and `fell_back`, and `SqliteQueryPlanRepository.save(plan, run_id=None)` persists it; `run_id` is nullable so a CLI preview is auditable before F14 exists.
- Topics now carry `keywords`, settable with `research-agent topic add --keyword` (repeatable).
- `research-agent queries plan --topic <id> [--no-save]` prints the plan header and one query per line.

**Files and interfaces**

- New: `src/research_agent/domain/queries.py` (`ExpandedQueries`, `QueryPlan`), `src/research_agent/queries/{__init__,prompts,planner}.py`, `src/research_agent/storage/queries.py`, `tests/unit/test_queries_planner.py`, `tests/unit/test_storage_queries.py`, `tests/integration/test_queries_cli.py`.
- Modified: `src/research_agent/storage/database.py` (schema 15 → 18: `topics.keywords_json`, the `query_plans` table, and `query_plans_topic_idx`, one statement per `MIGRATIONS` entry as before); `src/research_agent/config.py` (`TopicSettings.keywords`, `QuerySettings`, `queries` on `ApplicationSettings`); `src/research_agent/storage/topics.py` (keywords round-trip); `src/research_agent/cli.py` (`_open_connection` split out of `_open_repository`, `topic add --keyword`, the `queries` sub-app).

**Decisions and why**

- A `query_plans` table rather than deferring persistence to F14: the acceptance criterion is that the resolved plan can be audited later, and a nullable `run_id` lets that hold today without inventing a run.
- Keywords were added to the topic schema now because TRD §17 names them as planner input; deferring would have meant reopening the topics table, repository, and CLI in a later branch.
- The prompt is a module constant with `PROMPT_VERSION = "query_expansion.v1"`. A wording change means a new version string, and every persisted plan names the prompt that produced it.
- Padding from keywords applies in the fallback path too, so an offline run still issues more than one search when the topic defines keywords.

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean.
- `uv run mypy` → Success: no issues found in 63 source files.
- `uv run pytest` → 205 passed; total coverage 96.86% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent queries plan --topic embodied_spatial_intelligence` → fell back (nothing serving localhost:11434) and printed the base query, exit 0.
- Feeding that query into `research-agent discover --limit 3` returned 3 real OpenAlex candidates, with Semantic Scholar 429 and arXiv 406 tolerated as source errors.

**Known issues, risks, and unavailable validation**

- Semantic expansion has still never run against a real model; only the fallback path has been exercised end to end. Install a local OpenAI-compatible runtime and re-run `queries plan` before trusting the expansion quality or the prompt wording.
- The CLI never calls `observability.logging.configure_logging`, so planner and router warnings print as plain text rather than structured JSON. Pre-existing since F6; worth a `CHORE` branch when the graph starts emitting real run logs.
- The arXiv HTTP 406 and Semantic Scholar 429 from F5 are unchanged and still visible in live runs.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests remains unowned.

**Next recommended step:** F8 (`F8-classifier-a-integration`) is blocked on a prerequisite the roadmap states explicitly: locate or obtain the actual Classifier A implementation, weights, and usage terms before creating the branch. Do not invent or substitute a classifier. If Classifier A is not available, the next unblocked work is `F13-report-generation` or a `CHORE` branch for the structured-logging gap above.

## 2026-09-22 — F6 model provider routing (complete, merged)

- **Feature/branch:** `F6-model-provider-routing`.
- **Commits:** `a3be3c9` feat(models): add capability-based provider routing; merged as `9e4e398`.
- **Status:** Complete, merged, and re-verified on `main`. Live inference was not exercised (no local runtime is installed on this machine and no NIM key is configured); see known issues.

**Behavior added**

- `ModelProvider` protocol (TRD §23) with `ModelMessage`, `ModelResult` (provider, model, text, token counts, latency, `fell_back`, validated `parsed`), `ModelProviderError` carrying `MODEL_API_ERROR` / `MODEL_TIMEOUT`, and `ModelValidationError` for schema failures.
- `ChatCompletionsProvider` speaking the OpenAI-compatible `/chat/completions` shape, with `LocalModelProvider` (any local server: Ollama, LM Studio, llama.cpp) and `NvidiaNIMProvider` (`configured` only with an API key) as configured subclasses.
- `ModelRouter.generate(capability, messages, response_schema=None)` per TRD §26: `cheap_text` and `classification` run locally; `deep_reasoning`, `synthesis`, `ideation`, `report_writing` run on the strong provider with `retries.nim` retries (default 2) then a local fallback marked `fell_back=True`. An unknown capability raises `ValueError`; a local failure propagates.
- Structured output is parsed and validated against the caller's Pydantic model. Validation failures raise `ModelValidationError` and are never retried or fallen back on, because the TRD gives the single repair retry to Classifier B (F9).
- `research-agent model check [--capability] [--prompt]` prints the configured endpoints (key presence only, never the value), routes one small prompt, and prints `provider model latency`, exiting 1 on failure.

**Files and interfaces**

- New: `src/research_agent/models/{base,chat,router}.py`, `tests/unit/test_models_{chat,router}.py`, `tests/integration/test_model_cli.py`.
- Modified: `src/research_agent/config.py` (`ModelEndpointSettings`, `NimEndpointSettings`, `ModelSettings`, and the `models` field on `ApplicationSettings`); `src/research_agent/discovery/http.py` (POST/JSON-body support plus `error_category` / `transient_category` overrides — existing call sites unchanged); `src/research_agent/cli.py` (`model check`); `config/settings.yaml` and `.env.example` (endpoints only; the NIM key is env-only and redacted).

**Decisions and why**

- One OpenAI-compatible adapter for both providers: NIM speaks the same wire format, so a second adapter would have been duplicate code, and no new dependency was needed (`httpx` arrived in F5).
- The capability table is code, not configuration: TRD §26 fixes it, and a settings table for a value with one correct answer buys nothing.
- The F5 retry loop was extended in place rather than copied. It still lives under `discovery/` with a `ponytail:` comment; it should move to `utils/http.py` once a third consumer appears, which would be a refactor branch of its own rather than part of this feature.
- NIM defaults live on `NimEndpointSettings` rather than a field default. A test caught that with the previous shape, setting only `RESEARCH_AGENT_MODELS__NIM__API_KEY` silently reset the NIM base URL and model to the local defaults.
- Model calls are not persisted; no table exists for them and `RunSummary.models_used` covers provenance in F14.

**Verification**

- `uv run ruff format --check .` → 55 files already formatted.
- `uv run ruff check .` → All checks passed.
- `uv run mypy` → Success: no issues found in 55 source files.
- `uv run pytest` → 181 passed; total coverage 96.75% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- `uv run research-agent model check` → reported both endpoints, then exited 1 with "transport error: All connection attempts failed" because nothing is serving `localhost:11434` here. That is the correct degraded behavior, but it is not a successful inference.

**Known issues, risks, and unavailable validation**

- No real completion has been produced end to end. Install a local OpenAI-compatible runtime (`ollama serve` plus a `qwen3:8b`-class model) and re-run `research-agent model check` before relying on F7 or F9.
- `max_tokens` is the legacy OpenAI field name; some newer endpoints prefer `max_completion_tokens`. Ollama and NIM both accept `max_tokens` today.
- HTTP 5xx from a model endpoint is categorized `MODEL_TIMEOUT` because the shared helper treats every retryable status as transient. It is accurate about recoverability, coarse about cause.
- The pre-existing `ResourceWarning: unclosed database` from the F2-era tests is still present and still unowned.

**Next recommended step:** Create `F7-search-query-planning` and add the query planner: a versioned prompt, local semantic expansion over topic name, keywords, and the available historical summary, validation and stable deduplication down to roughly 5–20 queries, a deterministic base query used when inference is unavailable, and persisted plan provenance. It should call `ModelRouter.generate("cheap_text", ...)` with a Pydantic response schema rather than any provider directly.

## 2026-09-22 — F5 academic discovery (complete, merged)

- **Feature/branch:** `F5-academic-discovery`.
- **Commits:** `2a212cd` feat(discovery): add academic source adapters; merged as `2f9c7a1`.
- **Status:** Complete, merged, and re-verified on `main`; one live-API limitation documented below.

**Behavior added**

- `ResearchSource` protocol (TRD §15) plus `OpenAlexSource`, `SemanticScholarSource`, and
  `ArxivSource`, each translating provider payloads into `PaperCandidate` through the F3
  normalizers. Malformed records are skipped individually and logged; they never fail a page.
- Shared resilience layer `discovery/http.py`: per-provider `RateLimiter`, `request_text` /
  `request_json` with the configured retry ceiling (default 3), exponential backoff, `Retry-After`
  honored on 429/503, no retry on non-429 4xx, and an 8 MiB response cap before parsing.
- `DiscoveryAggregator`: bounded concurrency (`concurrency.discovery`), `asyncio.gather` with
  failure isolation into `ErrorRecord`s, a per-run cache keyed on
  `(source, query, start, end, limit)`, and a final `deduplicate(...)` so callers get one merged
  set with per-source counts.
- `research-agent discover --topic <id> --query <text> [--days] [--limit]` prints per-source
  counts, tolerated source errors, and the candidate table.

**Files and interfaces**

- New: `src/research_agent/discovery/{http,sources,openalex,semantic_scholar,arxiv,aggregator}.py`.
- Modified: `src/research_agent/config.py` (`SourceSettings`, `DiscoveryClientSettings`, and the
  `sources` field on `ApplicationSettings`), `src/research_agent/cli.py` (`discover` plus the
  `_http_client` factory tests replace), `pyproject.toml` (`httpx>=0.27,<1`), `.env.example`
  (commented, redacted `RESEARCH_AGENT_SOURCES__*` lines).
- New tests: `tests/unit/test_discovery_{http,sources,aggregator}.py`,
  `tests/integration/test_discovery_cli.py`, static fixtures in `tests/fixtures/discovery/`.

**Decisions**

- **httpx** is the second runtime dependency (user decision): real async I/O and
  `httpx.MockTransport`, so every test runs offline with no extra test dependency.
- **No `pytest-asyncio`** — tests drive coroutines with `asyncio.run`, so no new dev dependency.
- **Discovery never writes to SQLite** (user decision). The aggregator returns candidates; the F14
  graph node will call `SqlitePaperRepository.upsert`. This **corrects** the F4 entry below, which
  said F5 would persist via `upsert`.
- Semantic Scholar filters by year only, so the exact date window is applied client-side; arXiv is
  filtered client-side on `published` for the same reason.
- arXiv Atom is parsed with stdlib `ElementTree` under the response cap, with a `ponytail:` note
  naming `defusedxml` as the upgrade path if hardening is ever needed.
- Default pacing after live testing: OpenAlex 5/s (polite pool), Semantic Scholar 0.2/s (the
  unauthenticated pool 429s at 1/s), arXiv 0.33/s (their published one-request-per-three-seconds
  guidance).

**Verification**

- `uv run ruff format --check .` / `uv run ruff check .` → clean; `uv run mypy` → no issues in 49
  source files; `uv run pytest` → 145 passed, coverage 96.47% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- **Live smoke test** (`discover --topic embodied_spatial_intelligence --days 30 --limit 6`):
  returned 6 real OpenAlex candidates while Semantic Scholar 429'd and arXiv failed — exactly the
  designed degraded behavior, with both failures reported as source errors and exit code 0. This
  is how the arXiv and pacing issues below were found.

**Known issues / assumptions**

- **arXiv returned HTTP 406 to httpx while `curl` and stdlib `urllib` got 200 for the same URL**,
  and began answering 429 under repeated probing from this machine. A descriptive `User-Agent`,
  an `application/atom+xml` accept header, HTTPS, and 0.33 req/s are now sent, but the 406 was not
  fully root-caused before the rate limit made further isolation unproductive. Adapter logic is
  covered by fixtures; worth a `FIX1-arxiv-406` branch that retests from a cold IP and, if it
  persists, compares the exact wire headers httpx and curl send.
- Semantic Scholar without an API key is heavily throttled; set
  `RESEARCH_AGENT_SOURCES__SEMANTIC_SCHOLAR_API_KEY` in `.env` for reliable use. Never committed.
- Live smoke tests are deliberately absent from the default suite, per the roadmap.
- Pre-existing `ResourceWarning: unclosed database` from the F2 tests remains (13 warnings).

**Next recommended step:** Create `F6-model-provider-routing` and add the capability-based model
router with the local provider first, the optional NVIDIA NIM provider behind it, two-retry NIM
handling then local fallback, and no hardcoded model names or endpoints in workflow logic. Git:
`feat(models): add capability-based model routing` / `merge: F6-model-provider-routing route model
work by capability`.

## 2026-09-22 — F4 metadata and artifact persistence (complete, merged)

- **Feature/branch:** `F4-metadata-artifact-persistence`.
- **Commits:** `c36f9b7` feat(storage): add metadata and artifact persistence; merged as `2aded5b`.
- **Status:** Complete, merged, and re-verified on `main`.

**Behavior added**

- Schema version 1 → 15. New tables: `runs`, `papers`, `paper_sources`, `paper_files`,
  `classifications`, `paper_analyses`, `weekly_syntheses`, `research_gaps`, `research_ideas`,
  `errors`, plus indexes on `papers(doi)`, `papers(arxiv_id)`, `runs(topic_id, started_at)`, and
  `weekly_syntheses(topic_id, created_at)`. Every migration entry is a single statement, so the
  existing `apply_migrations` transaction and `PRAGMA user_version` logic are unchanged.
- `SqlitePaperRepository`: idempotent `upsert` (one `INSERT ... ON CONFLICT` that refreshes
  `last_seen_at`, fills previously-missing metadata via `COALESCE`, and keeps the larger citation
  count), `get` rebuilding a full `PaperCandidate` with its sources, `seen` for cache lookups, and
  `record_file` / `files_for` for stored artifacts.
- `SqliteRunRepository`: `start` / `complete` (duration derived from the stored start time),
  `get`, `recent`, `record_error`, `errors_for`. Error rows accept a `paper_id` that has no paper
  row, so a failure is never lost because its paper was not persisted.
- `SqliteResultRepository`: save/read pairs for classifications (active and shadow), analyses,
  syntheses, gaps, and ideas, plus `recent_syntheses(topic_id, limit=4)` — the TRD §44 history
  window — and `analysis_for(paper_id)` as the re-read cache lookup.
- `LocalArtifactStore`: the TRD §35 layout `data/topics/<topic_id>/{papers,parsed,analyses,
  reports,runs}/`, deterministic `safe_name` filenames, containment-checked paths, and atomic
  writes (temp file in the destination directory then `os.replace`).

**Files and interfaces**

- New: `src/research_agent/domain/runs.py` (`RunStatus`, `ErrorCategory` per TRD §39, `RunRecord`,
  `RunSummary`, `ErrorRecord`), `src/research_agent/domain/analysis.py` (`ClassificationResult`
  per TRD §10, `Claim`, `PaperAnalysis`, `WeeklySynthesis`, `ResearchGap`, `ResearchIdea` per
  TRD §27–31).
- New: `src/research_agent/storage/papers.py`, `runs.py`, `results.py`, `artifacts.py`, each
  exposing a `Protocol` plus its SQLite/local implementation, mirroring `storage/topics.py`.
- Modified: `src/research_agent/storage/database.py` (10 tables + 4 indexes appended to
  `MIGRATIONS`; new `now_iso()` helper shared by the new repositories).
- New tests: `tests/unit/conftest.py` (migrated database seeded with one topic, closed on
  teardown) and `test_storage_{migrations,papers,runs,results,artifacts}.py`.
- No configuration change; `ApplicationSettings.data_directory` is the `LocalArtifactStore` root.

**Decisions**

- **Indexed columns + `payload_json`** for the five model-produced entities (user decision).
  Repositories still take and return validated Pydantic models, so the interface is unchanged, but
  F11/F12 can extend a schema without a migration and F4 avoids ~60 columns of hand mapping. The
  cost is that those fields are not directly queryable in SQL; nothing in the PRD/TRD requires it.
- **All 10 TRD §33 entities implemented now** (user decision), so F8–F12 need no storage work.
- **`papers.id` is the F3 `canonical_id`**, which makes upserts naturally idempotent and lets
  artifact filenames derive from the same stable value.
- **Four storage modules, not ten repositories**, grouped by write path rather than by table.
- Timestamps are UTC ISO-8601 strings in every column, matching the F2 `topics` convention.
- `safe_name` sanitizes rather than rejects most hostile names (`../../x.pdf` → `x.pdf`); genuinely
  unusable names (`..`, empty, `///`) raise `ArtifactPathError`, and the resolved path is still
  containment-checked against the topic directory. Tested both ways.

**Verification**

- `uv run ruff format .` → 39 files left unchanged; `uv run ruff check .` → All checks passed.
- `uv run mypy` → Success: no issues found in 39 source files.
- `uv run pytest` → 117 passed, 13 warnings; total coverage 97.12% (gate 85%).
- `uv run research-agent config validate` → Configuration valid: 1 topic(s), 1 enabled.
- A genuine schema-version-1 database (only `topics`, `user_version = 1`) upgrades in place with
  its rows intact — covered by `test_a_version_one_database_upgrades_in_place`.

**Known issues / assumptions**

- Pre-existing `ResourceWarning: unclosed database` from the F2 tests remains (13 warnings); the
  new `connection` fixture closes its handle, so no new warnings were added. Still worth a chore.
- No CLI surface for the new repositories yet; they are wired up by F5 and later features.
- `paper_files` enforces one file per `(paper_id, kind)`; a second PDF for the same paper replaces
  the first. That matches the deterministic-filename rule and can be relaxed if F10 needs versions.

**Next recommended step:** Create `F5-academic-discovery` and add the `ResearchSource` protocol
with the OpenAlex, Semantic Scholar, and arXiv adapters, translating provider payloads into
`PaperCandidate` and persisting via `SqlitePaperRepository.upsert`, with per-source pacing,
429/`Retry-After` handling, three-retry backoff, bounded concurrency, and partial-source failure
isolation. Git: `feat(discovery): add academic source adapters` / `merge: F5-academic-discovery
search required academic sources`.

## 2026-09-22 — F3 paper normalization and deduplication (complete, merged)

- **Feature/branch:** `F3-paper-normalization-deduplication`.
- **Commits:** `81edc66` feat(papers): add normalization and deduplication; merged as `53dda16`.
- **Status:** Complete and verified.

**Behavior added**

- Provider-neutral paper schema: `PaperCandidate` plus `SourceReference`, with no network or LLM
  involvement anywhere in this feature.
- Deterministic normalization of Unicode, whitespace, DOI, arXiv identifiers, dates, URLs, titles,
  and author names.
- Stable canonical-ID policy: DOI first (`doi_10_1234_abcd`), then arXiv (`arxiv_2401_12345`), then
  a 12-hex SHA-256 of the normalized title plus first author (`title_<hash>`). Filename-safe and
  stable across runs.
- Deduplication in the TRD order — exact DOI, exact arXiv ID, exact normalized title, then a
  RapidFuzz `token_sort_ratio` fuzzy pass requiring author overlap. Merged output is sorted by
  canonical id, so a shuffled input produces an identical result.

**Files and interfaces**

- `src/research_agent/domain/papers.py` (new): `SourceReference`, `PaperCandidate`, `SourceName`.
- `src/research_agent/discovery/normalize.py` (new): `normalize_text`, `normalize_title`,
  `normalize_doi`, `normalize_arxiv_id`, `normalize_author(s)`, `normalize_url`, `normalize_date`,
  `canonical_id`, `normalize_candidate`. All pure.
- `src/research_agent/discovery/deduplicate.py` (new): `deduplicate(candidates, settings)` and
  `merge(existing, incoming)`.
- `src/research_agent/config.py`: added `DeduplicationSettings` (`title_similarity` 95.0,
  `require_author_overlap` true) and `ApplicationSettings.deduplication`.
- `pyproject.toml`: added `rapidfuzz>=3.9,<4` (resolved to 3.14.6).

**Decisions**

- **New dependency: RapidFuzz.** TRD section 19 names it and it ships typed stubs. `difflib` was
  considered and rejected: it cannot match titles whose words are reordered, which is the common
  cross-source duplicate shape.
- **TRD deviation:** `PaperCandidate` carries `sources: list[SourceReference]` instead of the flat
  `source` / `source_id` pair in TRD section 16. The F3 deliverable requires merge rules that
  preserve *all* source identifiers, which a single pair cannot express. Everything else in the
  schema matches the TRD.
- Dedup threshold lives on `ApplicationSettings`, not `TopicSettings`: it is a global matching
  policy, and per-topic placement would have forced a schema migration and four more CLI flags for
  a value that does not vary by topic.
- Merge rules are deterministic: first non-null identifier, earliest publication date, longest
  abstract, longest author list, larger citation count, union of sources sorted by
  `(source, source_id)`.
- The fuzzy pass is an O(n^2) scan over accepted candidates. Acceptable at the 500-candidate limit;
  the code carries a comment naming the upgrade path (bucket titles by prefix or token).

**Verification**

- `uv run ruff check .` — All checks passed.
- `uv run ruff format .` — 27 files unchanged.
- `uv run mypy` — Success: no issues found in 27 source files.
- `uv run pytest` — 80 passed, coverage 96.69% (threshold 85%).
- `uv run research-agent config validate` — "Configuration valid: 1 topic(s), 1 enabled."

**Known issues / risks**

- Pre-existing `ResourceWarning: unclosed database` from the F2 SQLite tests still appears under
  `-W error`. Not introduced here; a future chore can close connections in the test helpers.
- `normalize_date` accepts partial date strings, but `PaperCandidate.publication_date` is typed
  `date | None`, so adapters must call `normalize_date` on raw provider strings before building a
  candidate. That is the intended F5 usage.
- Nothing persists papers yet; F4 adds the tables.

**Next recommended step:** Create `F4-metadata-artifact-persistence` and add the papers, paper
sources, runs, and errors tables plus the artifact storage boundary, reusing the migration
foundation in `src/research_agent/storage/database.py`.

## 2026-09-22 — F2 topic management (complete, merged)

- **Feature/branch:** `F2-topic-management` (merged into `main`).
- **Commits:** `52c62d2` feat(topics): add persistent topic management; merged as `95e578e`.
- **Status:** Complete and verified.

**Behavior added**

- Topics are now persisted in SQLite instead of living only in `config/topics.yaml`.
- New CLI group `research-agent topic` with `add`, `list`, `enable`, and `disable`.
- `topic add` exposes every topic field as a flag (id, name, lookback, active/shadow classifier,
  each discovery source toggle, all four limits, enabled state, schedule frequency/day).
- Opening the store runs migrations and, when the `topics` table is empty, auto-seeds from the
  topics YAML. Seeding is idempotent; a missing or invalid YAML leaves the store empty rather than
  failing, so `topic add` still works on a bare machine.

**Files and interfaces**

- `src/research_agent/storage/database.py` (new): `MIGRATIONS`, `connect()`, `apply_migrations()`.
  Schema version is tracked with `PRAGMA user_version`; migration 1 creates `topics`.
- `src/research_agent/storage/topics.py` (new): `TopicRepository` Protocol,
  `SqliteTopicRepository`, `bootstrap()`, and `TopicStoreError` / `DuplicateTopicError` /
  `TopicNotFoundError`.
- `src/research_agent/config.py`: added `SchedulingSettings` (frequency `weekly`, day `sunday`) and
  `TopicSettings.scheduling`, matching TRD section 9.
- `src/research_agent/cli.py`: `topic` sub-typer plus the private `_open_repository()` helper.
- Database path: `ApplicationSettings.data_directory / "research_agent.db"` (`data/` is gitignored).

**Decisions**

- stdlib `sqlite3` and hand-rolled migrations; no Alembic and no new dependency.
- `TopicSettings` remains the single validated topic model — the repository returns it directly, so
  the acceptance criterion "reconstructed as the existing validated topic model" holds without a
  parallel record type.
- Flat explicit columns rather than JSON blobs, so rows are queryable and readable in any client.
- `created_at`/`updated_at` are written but not yet read; no accessor was added (YAGNI).
- Auto-bootstrap was chosen over an explicit `topic import` command at the user's request.

**Verification**

- `uv run ruff format --check .` — 22 files already formatted.
- `uv run ruff check .` — All checks passed.
- `uv run mypy` — no issues in 22 source files.
- `uv run pytest` — 39 passed, total coverage 94.86% (threshold 85%).
- Manual: `topic list` seeded the committed topic, `topic add`/`disable` persisted, and a new
  process saw the same rows.

**Known issues / assumptions**

- `topic` commands import `_load_yaml_mapping` from `config.py`; if more modules need it, promote it
  to a public helper.
- There is no `topic remove` or `topic edit` yet; editing means YAML plus a fresh database, or a
  future feature.
- `UPDATES.md` is untracked, so this entry is local only and never appears in a commit.

**Next recommended step:** Create `F3-paper-normalization-deduplication` and implement the
`PaperCandidate` schema, normalization, and the required deduplication priority order.


## 2026-09-22 — Handoff log kept local

- **Status:** Completed, merged into `main`.
- **Task:** Stop distributing the handoff log and remove the README references to the local-only agent files.
- **Branch:** `CHORE2-untrack-handoff-log` (second chore allocation).
- **Summary:** Added `UPDATES.md` to `.gitignore` and untracked it with `git rm --cached`; the file stays on disk and remains the required append-at-top handoff log for local work. Removed the closing README paragraph that pointed at `AGENTS.md` and `UPDATES.md`, since neither is in the repository any more.
- **Decision:** Agent conventions and engineering handoff notes are working-copy context, not published artifacts. The README now describes only what a clone actually contains.
- **Files affected:** `.gitignore`, `README.md`, `UPDATES.md`; `UPDATES.md` removed from version control while remaining present locally.
- **Verification:** `git check-ignore -v` confirms the path is ignored and `git ls-files` lists no agent/handoff file; `README.md` contains no reference to either file. Ruff format/lint, strict mypy, and the 21-test suite pass unchanged. No source code was touched.
- **Git references:** Chore commit on `CHORE2-untrack-handoff-log`; merge commit on `main`. Both use `Debesh Biswas <mail2debesh@gmail.com>` with no agent attribution or commit trailers.
- **Known issues/risks:** The published repository no longer carries conventions or engineering history, so a fresh clone has neither; both files exist only in this working copy and in Git history up to commit `025ce91`. Losing the working copy loses all later handoff entries. Switching branches across the untracking commit deletes the working file — back it up first and restore afterwards.
- **Next recommended step:** Unchanged — create `F2-topic-management` and implement persistent topic add/list/enable/disable behind a repository interface.

## 2026-09-22 — Agent instruction files kept local

- **Status:** Completed, merged into `main`.
- **Task:** Treat `AGENTS.md` as local-only agent instructions and expose the same content as `CLAUDE.md`.
- **Branch:** `CHORE1-ignore-agent-instructions` (first chore allocation).
- **Summary:** Added `CLAUDE.md` as a symlink to `AGENTS.md` so Claude Code loads the existing conventions without a second copy to keep in sync. Added both filenames to `.gitignore` and untracked `AGENTS.md` with `git rm --cached`; the file remains on disk and remains authoritative for local work.
- **Decision:** One file, two names, via symlink rather than duplicated content — duplicated instruction files drift. Conventions are now a working-copy concern, not a distributed artifact.
- **Files affected:** `.gitignore`, `README.md`, `UPDATES.md`; `AGENTS.md` removed from version control (still present locally); `CLAUDE.md` created locally and ignored.
- **Verification:** `git check-ignore -v` confirms both paths are ignored; `git ls-files` no longer lists `AGENTS.md`; the file and symlink both resolve on disk. Ruff format/lint, strict mypy, and the 21-test suite pass unchanged. No source code was touched.
- **Known issues/risks:** `AGENTS.md` no longer reaches anyone cloning from GitHub, so a fresh clone has no conventions file; historical `UPDATES.md` entries still reference it as a repository file and were deliberately left unedited as a log. The `README.md` reference was reworded to state the file is local and untracked.
- **Next recommended step:** Unchanged — create `F2-topic-management` and implement persistent topic add/list/enable/disable behind a repository interface.

## 2026-09-22 — Complete v1 feature roadmap

- **Status:** Completed, merged into `main`, and re-verified on the merged tree.
- **Task:** Translate the full PRD/TRD into a sequential, branch-ready implementation roadmap covering every planned v1 product feature.
- **Branch:** `DOC2-feature-roadmap` (second numbered documentation task).
- **Summary:** Added `docs/FEATURE_ROADMAP.md` with a dependency-ordered F1–F20 plan. Each feature records its branch, prerequisites, goal, bounded deliverables, public/CLI surface where applicable, tests, acceptance gate, exclusions, and exact feature/merge commit-message convention. F1 is marked complete with its Git references; F2 remains the next product branch. The README now links directly to the roadmap.
- **Roadmap decisions:** The sequence establishes topic/domain/persistence foundations before network and model integrations; completes discovery, provider, query, classifier, and selection layers before document processing; builds analysis, synthesis, ideation, and reporting before LangGraph integration; then adds local operations, MVP hardening, and AWS portability validation. The roadmap reserves F2–F20 names but does not begin those features. AWS work proves replaceable contracts and documents deployment rather than creating paid infrastructure.
- **Important gates:** F8 cannot start until the actual pre-existing Classifier A implementation is located or supplied; F9 must confirm the intended Qwen model/runtime; F6 and F12 must select currently compatible local-model and Docling stacks when those branches begin. The roadmap explicitly forbids silently inventing replacement classifiers or committing model weights/secrets.
- **Files affected:** `docs/FEATURE_ROADMAP.md`, `README.md`, and `UPDATES.md`.
- **Verification:** Reviewed the PRD and TRD in full; mapped all in-scope requirements, CLI commands, database entities, workflow nodes, failure routes, testing obligations, local scheduling, and AWS compatibility constraints to at least one feature; confirmed F1–F20 numbering is unique and ordered. Before and after merge, Ruff formatting/linting, strict mypy, the 21-test suite with 89.77% coverage, and Markdown whitespace checks all passed.
- **Git references:** Documentation commit `dc8ae78`; merge commit `1df9db1`. Both use `Debesh Biswas <mail2debesh@gmail.com>` with no agent attribution or commit trailers.
- **Known issues/risks:** Future library/model selections may change as compatibility evolves; the roadmap therefore fixes required behavior and boundaries while deferring time-sensitive implementation choices to the named planning gates. Classifier A/B artifacts remain absent from the repository.
- **Next recommended step:** Publish the merged DOC2 state, then create `F2-topic-management`; do not begin F3 or any later branch until F2 is complete and merged.

## 2026-09-22 — F1 Python project scaffold

- **Status:** Completed, committed on the feature branch, merged into `main`, and re-verified on the merged tree.
- **Feature:** Establish the runnable, local-first Python project foundation required before product features.
- **Branch:** `F1-project-scaffold` (first allocation in the product-feature sequence).
- **Summary:** Added a Python 3.11+ `src` package managed by `uv`, the `research-agent` Typer CLI, typed YAML/environment configuration, strict topic validation, standard-library JSON logging, importable architecture boundaries, safe local defaults, repository hygiene rules, developer documentation, and an offline unit/integration test foundation. The CLI currently supports `--help`, `--version`, and `config validate`; remaining TRD commands are intentionally deferred until they have real behavior.
- **Important interfaces and files:** `research_agent.config.load_configuration()` resolves application settings and topic definitions into Pydantic models; process `RESEARCH_AGENT_*` variables override `.env`, which overrides `config/settings.yaml`, which overrides model defaults. `research_agent.observability.configure_logging()` emits UTC JSON records with optional workflow context. `pyproject.toml` defines the console script, Ruff, strict mypy, pytest, and coverage configuration; `uv.lock` captures the resolved environment. `.env.example` contains only non-secret examples, while `.gitignore` excludes credentials, runtime data, databases, PDFs, reports, logs, model artifacts, environments, caches, builds, and coverage output.
- **Configuration defaults:** Local artifact storage, SQLite metadata, launchd scheduling, local strong-model provider, 10-day topic lookback, active Classifier A with shadow B in the example topic, candidate/classification/download/deep-read limits of 500/250/50/15, discovery/download/analysis concurrency of 3/4/2, and TRD retry ceilings of 3/2/1/2. Validation rejects unknown keys, invalid classifiers, equal active/shadow classifiers, duplicate or malformed topic IDs, disabled discovery, and inconsistent or non-positive limits.
- **Dependency decision:** Added only dependencies used by F1: Typer, Pydantic, Pydantic Settings, and PyYAML at runtime; Ruff, mypy, pytest, pytest-cov, and PyYAML type stubs for development. LangGraph, HTTP clients, database layers, PDF tooling, and model runtimes remain deferred until the features that use them, preventing unused or premature infrastructure.
- **Verification:** On Apple Silicon with CPython 3.14.6 and uv 0.11.26, `uv lock` and `uv sync --all-groups` succeeded; `uv run ruff format --check .` and `uv run ruff check .` passed; strict `uv run mypy` passed across 18 source/test files; `uv run pytest` passed 21 tests with 89.77% branch-aware coverage against an 85% threshold; CLI version and committed-config validation passed; `python -m research_agent --version` passed; `uv build` produced both sdist and wheel; `git diff --check` passed. Formatting, linting, typing, tests, configuration validation, and whitespace checks were repeated successfully on `main` after the merge. Tests are offline and require no credentials, APIs, paid services, Docker, or model downloads.
- **Decisions and assumptions:** The distribution and command are `research-agent`, while imports use `research_agent`. `config/settings.yaml` is the local v1 profile; AWS configuration and Docker are out of scope. The authoritative `docs/` specifications are excluded from Ruff formatting so code snippets are not mechanically rewritten. Architectural subpackages are intentionally empty boundaries rather than misleading placeholder implementations.
- **Git references:** Feature commit `5bcd38a`; merge commit `46af966`. Both were authored/committed as `Debesh Biswas <mail2debesh@gmail.com>` with no agent attribution or commit trailers.
- **Known issues/risks:** Verification used Python 3.14.6 rather than the minimum Python 3.11; package metadata supports 3.11+, but a multi-version CI matrix is not part of F1. The PRD/TRD describe pre-existing Classifier A/B implementations, but their concrete code or model assets are still not present in this repository.
- **Next recommended step:** After publishing this merged state, allocate `F2-topic-management` to implement persistent topic add/list behavior behind a repository interface without beginning workflow orchestration.

## 2026-09-22 — Specifications organized under `docs/`

- **Status:** Completed, merged into `main`, and published to GitHub.
- **Task:** Move the project specifications into a documentation directory while preserving root-level agent discovery and handoff files.
- **Branch:** `DOC1-organize-specifications` (renamed from the pre-convention working name `docs/organize-specifications`).
- **Summary:** Moved the PRD and TRD from the repository root into `docs/` and updated all live convention/handoff references to their new paths. Kept `AGENTS.md` and `UPDATES.md` at the root because coding agents discover repository instructions there and the handoff log should remain immediately visible. Added numbered branch naming (`F1-...`, `DOC1-...`, and other task prefixes), Conventional Commit/merge-message rules, and a strict prohibition on agent/AI authorship or co-authorship metadata.
- **Files affected:** `docs/research_agent_PRD.md`, `docs/research_agent_TRD.md`, `AGENTS.md`, and `UPDATES.md`.
- **Decision:** Use `docs/` rather than `documentation/` for a concise, conventional path. Preserve file contents and Git history through tracked renames. Reserve the `F<number>-...` sequence for product features; use independently numbered task prefixes for non-feature work. Existing history remains unchanged, and all future Git metadata uses only the configured human identity.
- **Verification:** Confirmed both moved files are non-empty; searched tracked Markdown for stale root-path references; ran `git diff --check`. No application test suite exists yet.
- **Git/GitHub:** Documentation commit `fdcc402`; merge commit `8537fb7`. Configured `origin` as `https://github.com/debesh-biswas/Research-Agent.git`, created remote `main`, and set local `main` to track `origin/main`. HTTPS authentication succeeded for the repository owned by `debesh-biswas` using the machine's configured Git credentials. All commits use `Debesh Biswas <mail2debesh@gmail.com>` with no agent co-author metadata.
- **Known issues:** GitHub CLI is unavailable locally; Git transport and the configured credential helper are used for remote operations instead. No application code or test suite exists yet.
- **Next recommended step:** Start project scaffolding as the first product feature on `F1-project-scaffold`; complete, verify, commit, and merge it before allocating `F2`.

## 2026-09-22 — Repository conventions established

- **Status:** Completed pre-implementation setup.
- **Task:** Review the product and technical specifications and establish coding-agent conventions before project scaffolding.
- **Branch:** `docs/repository-conventions` (repository initialization uses a separate baseline specification commit; no product feature implemented).
- **Summary:** Added `AGENTS.md` with project-specific product guardrails, architecture boundaries, classifier/model behavior, persistence and security rules, reliability and observability requirements, coding conventions, test expectations, a mandatory per-feature Git workflow, and detailed handoff-log requirements.
- **Specifications reviewed:** `docs/research_agent_PRD.md` v1.0 and `docs/research_agent_TRD.md` v1.0 in full (paths updated after the documentation reorganization).
- **Key decisions captured:** Python 3.11+ and local-first operation; LangGraph limited to orchestration; deterministic mechanics separated from semantic LLM work; provider-neutral interfaces for discovery, classifiers, models, storage, repositories, and scheduling; Classifier A/B schema parity with active/shadow isolation; optional NIM with local fallback; SQLite plus local artifact storage; evidence provenance; bounded retries/concurrency; structured logs; AWS-compatible boundaries without premature AWS implementation.
- **Files added:** `AGENTS.md`, `UPDATES.md`.
- **Verification:** Confirmed both specification files are present and reviewed their complete contents; inspected the rendered source structure and required sections in both new Markdown files. No application test suite exists yet.
- **Git references:** Baseline specifications commit `b91b55f`; conventions commit `d8a903c`; merged into `main` as `7bb5677`.
- **Known state:** No application scaffold or runtime code exists yet. Classifier A and Classifier B are described as pre-existing in the specifications, but their concrete implementations/assets have not yet been located or supplied. No feature branch has started.
- **Next recommended step:** Initialize the Python project on `F1-project-scaffold`, add the baseline package/config/test structure and secret-safe `.gitignore`, run its verification, update this log, commit, merge into `main`, and only then allocate `F2`.
