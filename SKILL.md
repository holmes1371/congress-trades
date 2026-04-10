---
name: congress-trades
description: >
  Fetches, analyzes, and reports on congressional stock trading activity from
  capitoltrades.com. Use this skill any time the user wants to: pull fresh
  trade data for specific Congress members, analyze trading patterns and
  signals, find consensus buys/sells, generate a trade intelligence report,
  update their congressional trading dataset, act on congressional trading
  trends, or pull/analyze trades for an entire congressional committee
  (e.g. "House Armed Services Committee", "Senate Banking", "pull trade data
  for [committee name]"). Trigger words include: "congress trades", "capitol
  trades", "politician IDs", "fetch trades", "trade analysis", "congressional
  trading report", "update the data", any mention of a House or Senate
  committee by name, or any mention of running the trading script. All
  scraping, statistics, and HTML rendering happen in local Python scripts;
  the agent only writes the prose interpretation.
---

# Congressional Trade Analysis Skill — CANONICAL

**This file in the project folder is the canonical SKILL.md.** Any copy under
`/sessions/.../mnt/.claude/skills/congress-trades/SKILL.md` is a read-only
stub that may be stale. Whenever the skill is triggered, the agent must
immediately read THIS file before doing anything else, and follow its
instructions over whatever the stub contained.

## Pipeline

All scripts live in this project folder. Steps 1–4 are now bundled into a
single orchestrator (`run_pipeline.py`); the agent only invokes individual
scripts for Steps 5–6.

1. **`run_pipeline.py`** — single entry point that internally runs:
   - `committee_lookup.py` (only when `--committee` is supplied; invoked inside `fetch_trades.py`)
   - `fetch_trades.py`     — scrapes capitoltrades.com → `trade_data[_<slug>].json` + `data/` archive
   - `compute_analysis.py` — aggregates stats → `computed_stats[_<slug>].json`. **May short-circuit with `NO_CHANGES:<date>` — see below.**
   - `build_skeleton.py`   — builds `analysis_skeleton[_<slug>].json` with every mechanical HTML field pre-rendered
2. `fill_skeleton.py`   — applies the agent's `fills.json` to the skeleton → `analysis[_<slug>].json`
3. `generate_report.py` — wraps the filled-in analysis JSON in the styled HTML shell

The agent's only job is **writing prose into the `[[FILL: ...]]` placeholders** in the skeleton (via `fills.json`).

---

## Runtime actions checklist (STRICT)

During a skill run the agent is permitted to take ONLY the following actions, in order. Any other tool call is a violation of the skill contract:

1. **`run_pipeline.py`** — with `--committee`, `--members`, or no args (default list); honor exit codes (see below)
2. **Write** a small `fills.json` containing only agent-authored prose strings, then run `fill_skeleton.py` to apply them to the skeleton and emit `analysis.json`
3. `generate_report.py analysis.json`
4. `present_files` with the emitted report path

Nothing else. No exploratory tool calls between steps. The agent never invokes `committee_lookup.py`, `fetch_trades.py`, `compute_analysis.py`, or `build_skeleton.py` directly — `run_pipeline.py` owns all of that.

### run_pipeline.py contract

```bash
# default politician list
python3 run_pipeline.py

# committee mode
python3 run_pipeline.py --committee "House Committee on Armed Services"
python3 run_pipeline.py --committee HSAS --days 60

# explicit bioguide IDs or member names
python3 run_pipeline.py --members K000389 M001157
python3 run_pipeline.py --members "Ro Khanna" "Dave McCormick"
```

The orchestrator streams the digests printed by `compute_analysis.py` and `build_skeleton.py` through to stdout. Those streamed digests are the agent's ONLY source of truth for authoring `fills.json` — the agent must not re-open any intermediate file to "verify" them.

**Exit contract:**

- Exit `0`, final line `PIPELINE_READY: skeleton=<path> slug=<slug-or-default>` → proceed to Step 5 (write `fills.json`, run `fill_skeleton.py` against the announced skeleton path)
- Exit `2`, final line `NO_CHANGES: <date>` → **stop the pipeline. Report exactly one line: "No new congressional trades since `<date>`." Do not run any further steps.**
- Exit `1`, `PIPELINE_ERROR: ...` on stderr → report the failure to the user; do not retry blindly

### The fill step uses fill_skeleton.py — the agent does NOT read the skeleton

The agent never opens `analysis_skeleton.json`. The skeleton is a large, mechanically-generated artifact; reading it is wasteful and invites structural inspection.

Instead, the agent writes a small `fills.json` containing ONLY the prose it authored, then calls `fill_skeleton.py` to apply those strings to the skeleton and write `analysis.json`. All substitution, validation, and leftover-placeholder detection happen in the script.

**`fills.json` schema** (all keys optional):

```json
{
  "title": "House Committee on Homeland Security — 60-Day Trade Review",
  "summary_alerts": {
    "consensus_buy_GOOGL":  "prose that MUST mention GOOGL",
    "consensus_sell_T":     "prose that MUST mention T",
    "conviction_Hern_TXN":  "prose that MUST mention TXN"
  },
  "ranked_ideas": {
    "GOOGL_BUY": "1-line rationale that MUST mention GOOGL",
    "AAPL_SELL": "1-line rationale that MUST mention AAPL"
  },
  "members": {
    "Michael McCaul": "2-3 sentence observation...",
    "Sheri Biggs":    "..."
  },
  "inactive_default": "Boilerplate for members with no disclosed trades."
}
```

**Both `summary_alerts` and `ranked_ideas` MUST be dicts keyed by the stable IDs the skeleton emits** — positional lists are rejected to prevent header/prose misalignment. The alert IDs are visible in the skeleton digest; `ranked_ideas` keys are `TICKER_ACTION` (e.g. `AAPL_SELL`). Every ticker named in an ID must appear in its prose — `fill_skeleton.py` validates this and will exit non-zero on mismatch, missing keys, or fabricated keys not in the skeleton. Members not listed in `members` receive `inactive_default`.

**Command:**

```bash
python3 fill_skeleton.py \
    --skeleton analysis_skeleton/analysis_skeleton_<slug>.json \
    --fills    fills.json \
    --out      analysis/analysis_<slug>.json
```

To know *which* members and how many alerts/ideas need prose, the agent uses the digest that `compute_analysis.py` and `build_skeleton.py` already print to stdout (member table, consensus signals, placeholder count). Those printed digests are the agent's only source of truth for the fill step.

### Forbidden during fills

While performing Step 5, the agent MUST NOT:

- Open, Read, `cat`, `head`, `tail`, or `grep` `analysis_skeleton*.json`, `computed_stats*.json`, `trade_data*.json`, or `member_bioguide.json`
- Run `python3 -c "..."` or any ad-hoc Python to dump keys, count placeholders, inspect structure, or extract fields
- Re-read any upstream artifact to "verify" what the skeleton contains
- Call the skeleton or any intermediate file "complex" and decide to explore it — the skeleton shape is contractual and pre-validated by `build_skeleton.py`

The agent's ONLY inputs at Step 5 are the stdout digests already printed by the earlier scripts plus out-of-band context the agent knows (committee jurisdiction, member background). The agent's ONLY output at Step 5 is `fills.json`. `fill_skeleton.py` handles everything mechanical.

---

## Steps 1–4 — `run_pipeline.py` (single invocation)

All member-set resolution, fetching, stat computation, change detection, and skeleton building happen inside `run_pipeline.py`. The agent picks one of three modes based on the user's request and invokes the orchestrator exactly once:

**A. Committee mode** — user names a committee (e.g. "pull trade data for House Armed Services Committee", "run the analysis for Senate Banking", "trades for HSAS"):

```bash
python3 run_pipeline.py --committee "House Committee on Armed Services" [--days 60]
```

`--committee` accepts a thomas_id (`HSAS`), an exact committee name, or a unique substring. If `committee_lookup.py` cannot resolve the supplied name, the pipeline hard-stops with `PIPELINE_ERROR`. Do not fall back to the default list, do not guess a roster, do not try to build one from web search.

**B. Explicit IDs / names** — user supplied bioguide IDs or member names:

```bash
python3 run_pipeline.py --members F000110 K000389 P000197
python3 run_pipeline.py --members "Ro Khanna" "Dave McCormick"
```

**C. Default list** — scheduled runs, "an update" with no further specification, **and whenever no committee name is supplied at trigger time**:

```bash
python3 run_pipeline.py
```

This uses the `POLITICIAN_IDS` list baked into `fetch_trades.py`.

`--days N` changes the lookback window (default 60).

**Important:** Do not hand-build a member list by reading `member_bioguide.json` or `committee_membership_current.json` directly, and do not invoke `committee_lookup.py`, `fetch_trades.py`, `compute_analysis.py`, or `build_skeleton.py` separately. All of that is owned by `run_pipeline.py`.

### What `run_pipeline.py` streams to stdout

The orchestrator passes through the digests from `compute_analysis.py` (biases, consensus signals) and `build_skeleton.py` (member table, placeholder count). Those streamed digests are the agent's ONLY source of truth for Step 5 — do not re-open any intermediate file to verify them.

### Output naming

- Default / explicit-ID runs → `trade_data.json`, `computed_stats.json`, `analysis_skeleton.json`
- Committee runs → `trade_data_<slug>.json`, `computed_stats_<slug>.json`, `analysis_skeleton/analysis_skeleton_<slug>.json`. Slug is derived automatically. The orchestrator announces the final skeleton path on its `PIPELINE_READY:` line — pass that path to `fill_skeleton.py` in Step 5.

### Change detection

If `compute_analysis.py` detects no new disclosures, the orchestrator exits `2` with final line `NO_CHANGES: <date>`. When that happens, **stop. Report exactly one line: "No new congressional trades since `<date>`." Do not run any further steps.**

### What the skeleton contains

`run_pipeline.py` ends with `build_skeleton.py`, which produces a skeleton with everything pre-built:

- `title`, `date`, `window`, `members`, `source` — derived from metadata
- `overview_table_rows` — full member overview HTML
- `sector_html` — sector rotation cards
- `member_sections` — stat cards + top-ticker chips per member
- `ranked_ideas_rows` — top 10 mechanically-ordered ideas with rank, ticker, action, star strength, members
- `summary_alerts` — pre-built shells for top cross-party signals + top conviction pattern

Every place the agent needs to add prose is marked with `[[FILL: ...]]`.

---

## Step 5 — Fill in the Prose

**Do not open the skeleton.** Write a `fills.json` with only the prose strings and run `fill_skeleton.py` (see "The fill step uses fill_skeleton.py" above). Four kinds of fills:

- **`summary_alerts[].html`** — finish each headline with 1–2 sentences explaining what the signal implies and why it matters. Lead with the strongest cross-party signals.
- **`ranked_ideas_rows` rationales** — one short sentence per row explaining the thesis behind that buy/sell.
- **`member_sections` observation `<p class="obs">`** — 2–3 sentences per member: posture, sector concentration, what the activity implies.
- **(optional) `title`** — when running in committee mode, retitle to reflect the committee (e.g. "House Armed Services Committee — 60-Day Trade Review"). Otherwise the default is fine.

Do not modify any of the mechanical fields (overview rows, sector cards, stat cards, ticker chips, ranking, stars, member counts) — those are authoritative from the script.

When writing, lean on context the script can't know: committee jurisdiction (e.g. defense exposure for Armed Services), McCormick's Goldman background, Fields' pure-buy posture, etc. Keep the tone academically neutral.

---

## Step 6 — Render the Report

```bash
# default-list run
python3 generate_report.py analysis.json

# committee run — fill the skeleton into analysis_<slug>.json first, then:
python3 generate_report.py analysis_<slug>.json
```

The script:
- Writes the report into a **lineage-scoped subfolder** under `reports/`:
  - Default politician list → `reports/default/report_YYYYMMDD_HHMMSS.html`
  - Committee runs → `reports/<slug>/report_<slug>_YYYYMMDD_HHMMSS.html`
    (e.g. `reports/house_committee_on_armed_services/report_house_committee_on_armed_services_YYYYMMDD_HHMMSS.html`)
- Archives a copy of the analysis JSON to `analysis/analysis[_<slug>]_YYYYMMDD_HHMMSS.json`
- Prints both paths
- Prints a `WARNING` if any `[[FILL:` placeholders are still present (use this to catch missed prose)

Each lineage lives in its own subfolder, so `NO_CHANGES` stubs written by `compute_analysis.py` land in the same subfolder as that lineage's full reports and their "most recent full analysis" back-link resolves as a plain relative filename. A default-list stub can never link to a committee report and vice versa — isolation is structural, not regex-based.

Legacy pre-scheme files live in `reports/_legacy/` and must be ignored.

Present the report path with `present_files`.

---

---

## Scoring pipeline — `scoring/score_members.py` (separate subsystem)

A second, fully independent pipeline under `scoring/` ranks every Congress member in `member_bioguide.json` by followability and produces the default follow list. It is **not** invoked by `run_pipeline.py` and does not share any output paths with the weekly report flow. Use it whenever the user wants to update, inspect, or tune the default follow list — typical phrases: "update the follow list", "re-score members", "who should we be following", "rerun the scoring", "adjust the weights".

### Files

- `scoring/score_members.py` — orchestrator; takes `--top-n`, `--limit`, `--refresh`, `--members`, `--min-trades`, `--window-days`, `--short-window-days`
- `scoring/price_cache.py` — yfinance bulk fetch with per-ticker CSV cache at `scoring/cache/prices/`
- `scoring/factors.py` — per-trade alpha (BUYs only, 5/20/60d vs SPY), per-member aggregation, z-score composite. Weights live in `COMPOSITE_WEIGHTS`.
- `scoring/cache/trades/<bioguide>.json` — per-member fetch checkpoints, 30-day TTL
- `scoring/output/leaderboard_<YYYYMMDD>.xlsx` — ranked leaderboard, dual-window sheets, sub-factor columns
- `scoring/output/default_follow_<YYYYMMDD>.json` — top-N stable picks (divergence-filtered)

### Runtime contract

```bash
python3 scoring/score_members.py --top-n 20          # full 538-member run
python3 scoring/score_members.py --limit 5           # dry run on first 5
python3 scoring/score_members.py --members K000389   # score one or more bioguide IDs
```

**The full run exceeds the 10-minute Bash tool timeout.** Expect exit code 143 on the first invocation — this is not a failure. The per-member trade cache writes after every successful fetch, so rerunning resumes from wherever the first invocation stopped. A typical flow is two invocations: the first runs the fetch loop until SIGTERM, the second reads entirely from cache and completes the price fetch + scoring + xlsx output in under a minute. Do NOT treat exit 143 as an error; check `scoring/cache/trades/` to confirm all 538 members were cached, then immediately rerun.

### Filesystem caveats (the cowork mount is Windows-backed)

Two quirks have been patched in the code but are worth knowing about so nobody "fixes" them back:

1. **xlsx writes are staged through a local scratchpad.** Writing multi-sheet openpyxl workbooks directly through the mount produced files with a valid PK header but missing end-of-central-directory record, causing every subsequent read to fail with `BadZipFile`. `score_members.py` writes to a `tempfile.NamedTemporaryFile` first, verifies the zip with `zipfile.ZipFile().namelist()`, then `shutil.copy` into the mount. Do not collapse this back to a direct write.

2. **Price cache filenames avoid Windows reserved device names.** `CON`, `PRN`, `AUX`, `NUL`, `COM1–9`, `LPT1–9` are Windows device names and cannot exist as files anywhere on the mount. `price_cache._cache_path()` suffixes reserved tickers with `_` (so Concentrix stores as `CON_.csv`). This is transparent to callers.

### Answering follow-up questions without re-running

Once a leaderboard xlsx has been written, it is durable and the agent can answer any sub-factor question by reading it directly — no scoring rerun needed. Only rerun the pipeline when the user wants to change weights, thresholds, or the qualify floor.

---

## Summary of agent vs script responsibilities

| Concern                                       | Owner   |
|-----------------------------------------------|---------|
| Committee name → thomas_id resolution         | script  |
| thomas_id → bioguide list                     | script  |
| Name/ID resolution against bioguide directory | script  |
| HTTP scraping, pagination                     | script  |
| Change detection / short-circuit              | script  |
| All counting and aggregation                  | script  |
| Star strength assignment                      | script  |
| Idea ranking and dedupe                       | script  |
| All HTML row/card generation                  | script  |
| Placeholder substitution into skeleton        | script (`fill_skeleton.py`) |
| Leftover-placeholder validation               | script (`fill_skeleton.py`) |
| Headline narrative prose                      | agent   |
| Per-member observation prose                  | agent   |
| Per-idea rationale prose                      | agent   |
| Committee-aware framing in prose              | agent   |
