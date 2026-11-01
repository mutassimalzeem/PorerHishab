# AI-15R: Scenario Library & Comparative Planning

AI-15R makes existing AI-15Q scenarios discoverable, reusable and comparable. It does not add financial calculations, automatic money movement or an autonomous planning agent. `/scenarios` keeps the real financial picture separate from saved hypothetical alternatives. `/scenarios/compare` organizes two to five alternatives and their already-calculated impacts.

## Relationship with AI-15Q

The authoritative financial engine remains `services/finance/scenarios.py::calculate`, with the same `ai-15q-v1` calculation version. Its arithmetic and existing AI-13/15D/15K/15P dependencies are unchanged. AI-15R calls the existing `result_for` serializer to read typed metric comparisons and frozen goal/affordability evidence. Opening, searching, copying, renaming, archiving, restoring and comparing never invokes `calculate` or creates a simulation run. Explicit simulation still uses Q's authenticated endpoint and idempotency key.

The new comparison service contains no financial arithmetic. Every baseline value, hypothetical value, absolute delta, percentage delta, direction, availability status and reason comes from a stored Q result. It does not subtract scenario values from one another, rank alternatives, infer a financially correct plan, or fabricate unavailable runway/health dimensions. Q's structured explanation and scenario disclaimer remain available; no LLM arithmetic or provider integration is introduced.

## Lifecycle and metadata

- `draft`: an alternative being edited. Creation and duplication produce drafts. Replacing structured assumptions returns a saved scenario to draft.
- `saved`: an intentional saved alternative. Default library results contain only saved scenarios.
- `archived`: retained historical alternative, excluded from the default list. Its assumptions and runs remain readable/comparable; edits and new simulations retain Q's read-only restriction.

Restore changes archived to saved using the same ID and assumptions. Duplicating an archived scenario creates an independent draft and leaves the source archived. Rename and description updates are separate from structured assumptions. Names are user-controlled, normalized by collapsing whitespace, nonblank and at most 120 characters. Descriptions are at most 1000 characters; an empty string clears one. Description text is never interpreted as an instruction. Names are not unique, globally or within an owner's library, allowing intentional repeated labels. Default copy names avoid existing owner-local names deterministically: `Rent (Copy)`, `Rent (Copy 2)`, etc.; long source names are truncated to fit the suffix.

Existing Scenario fields are reused. Migration `f15r00000001` follows `f15q00000001` and adds only `updated_at`, nullable `saved_at`, nullable `archived_at`, nullable `source_scenario_id`, its self-referencing foreign key, and an owner/status/update/ID index. `updated_at` is backfilled from creation time for legacy rows. Historical save/archive timestamps remain null because Q did not record their actual times. New lifecycle events record actual UTC timestamps; SQLite-naive timestamps are normalized to UTC at response serialization. Restoring clears `archived_at`, preserves a known `saved_at`, and records a new update time.

Duplicates copy structured changes and descriptive metadata, receive independent IDs/timestamps/revisions, and record the owned source ID. They do not inherit runs, baseline references, save/archive timestamps or result availability. Editing the copy never edits the original. No deletion endpoint exists.

## API, service and repository

Routes remain thin authenticated adapters. `services/finance/scenario_library.py` owns listing, metadata, duplication, restoration and comparison orchestration. `repositories/scenarios.py` scopes scenario, change, run and metric queries to the authenticated owner. The Q service reuses that repository for its read paths. List summaries batch child changes/latest runs, keeping query count constant across page sizes.

| Endpoint under `/finance/scenarios` | Behavior |
| --- | --- |
| GET | Paginated library; default `status=saved`, `limit=20`, `offset=0` |
| POST | Existing Q create workflow with normalized name |
| GET /{id} | Existing detail plus lifecycle timestamps, source ID and last-run/freshness metadata |
| PATCH /{id} | Update name and/or description only |
| POST /{id}/duplicate | Independent draft with copied assumptions and deterministic owner-local copy name |
| POST /{id}/archive | Retain scenario/history; naturally idempotent |
| POST /{id}/restore | Archived to saved; repeated restore of saved is naturally idempotent |
| POST /compare | Read two to five distinct owned scenario IDs; organize saved Q results |
| POST /{id}/save | Existing Q save workflow, with lifecycle timestamps |
| POST/PATCH /{id}/changes | Existing Q structured assumption replacement and revision increment |
| POST /{id}/simulate | Existing Q deterministic calculation and replay behavior |
| GET /{id}/result, GET /{id}/comparison | Existing Q immutable latest/historical run access |

`GET` accepts `status=saved|draft|archived|active|all`; active includes saved and draft. Search matches name/description case-insensitively, treating SQL wildcard characters literally. Limit is 1-50 and offset is nonnegative. Results order by `updated_at DESC, id DESC` for deterministic ties. The response is `{items, total, limit, offset}` rather than Q's unpaginated array; the frontend client and generated contracts are updated together. Every count/filter remains owner-scoped.

Compare request:

```json
{"scenario_ids":[12,19,24]}
```

The response contains scenario columns (metadata, typed assumptions and a current stored result or null), a metric matrix, calculation version, structured warnings and the disclaimer. Each cell retains Q's exact `MetricComparison`. A cell with no usable result or missing metric has `comparison: null`, `status: insufficient_data`, and a reason. A stored Q unavailability status such as `not_available_for_scenario` is preserved exactly.

## Result reuse, staleness and versions

Q already records the scenario's assumption `revision` in each run request. Detail/list responses expose `latest_run_id`, `latest_run_at`, `result_revision`, `result_calculation_version` and `result_state`:

- `missing`: no run exists.
- `current`: latest run revision and calculation version match the scenario.
- `stale`: assumptions or calculation version no longer match that run.

Metadata edits do not increment the financial assumption revision. Saving, archiving and restoring do not invalidate a result. Duplicates have no run. Current refers to matching assumptions, not a guarantee that today's real financial picture is unchanged since the recorded snapshot. The comparison view always identifies recorded real baselines and snapshot dates; it does not silently replace them with live balances.

Comparison never reruns missing/stale scenarios. It exposes their current assumptions and state, excludes stale money from the matrix, and directs the user to open/rerun explicitly. Historical Q results remain accessible, including after editing or archiving. Incompatible stored calculation versions produce a clear 409, preventing silent mixing. Uniform historical versions can still be displayed as their original version; no stored result is recalculated or rewritten.

Different baseline references, snapshot dates, horizons, or schedule-completeness confirmations produce explicit machine-readable warnings. Each column preserves its own baseline rather than claiming a shared real current plan. Assumptions are compared as multisets of complete typed changes, including dates, targets and descriptions: a repeated identical change is shared only as many times as every selected scenario contains it. This organizes selected assumptions without financial interpretation.

## Tenant isolation, transactions and idempotency

Authenticated ownership controls every endpoint and repository read, including child changes, runs, comparisons, source scenarios and library counts. Foreign IDs return the same 404 as nonexistent IDs. All IDs in a comparison are authorized before inspecting result versions or producing output. Bodies cannot assign authoritative users/owners, status, financial changes or arbitrary metadata fields through rename.

Create/rename/duplicate/save/archive/restore and simulation use the existing AI-15P/Q owner row lock. Comparison takes the same lock for a coherent view of selected revisions and runs. Duplicate naming, concurrent metadata updates and lifecycle transitions serialize for an owner. A duplicate and its copied assumptions commit atomically; failures roll back the entire copy. Source metadata and all real financial entities remain unchanged. The source foreign key and library index are the only new database structures beyond timestamps.

Q's unique owner/simulation-request key and exact replay remain unchanged. Repeated save/archive/restore requests are naturally idempotent and preserve timestamps when already in the requested state. A duplicate POST intentionally creates a new copy, matching Q's keyless create convention; the UI disables mutation controls while a request is running. There is no second request-key store or incompatible idempotency system.

## Frontend and localization

`/scenarios` retains Q's creation/change/run workspace and real baseline summary, with library cards for saved, draft and archived alternatives. Users search, page, open, rename in a keyboard-accessible dialog, duplicate, archive/restore, and select two to five scenarios across pages for comparison. A refresh after rename restores focus to the new card button, or search when the renamed item no longer matches the filter.

`/scenarios/compare` provides bounded selection, scenario cards, shared/different assumption labels and a horizontally scrollable semantic comparison matrix. The table has row/column headers and a labelled keyboard-focusable scroll region. Real recorded baselines, hypothetical outputs, stored directions, deltas, dates and versions stay explicit; color is not the only indicator. Missing/stale results and unavailable metrics have visible states and expandable recorded reasons. User names/descriptions and backend evidence retain their original language. The recorded English evidence is not silently machine-translated.

Both routes use the existing authenticated API client and shared `translations.ts` / `t` / `uiLabel` mechanisms. Q's component-local translation dictionary has been migrated into the shared catalog, preserving existing translations rather than introducing another localization mechanism. Monetary strings/deltas are rendered directly; the frontend performs no financial arithmetic.

## Examples

A user saves `Rent + BDT 5,000` and `Salary -15%`, explicitly runs each through Q, and compares their existing baseline/hypothetical values. The matrix shows the precomputed changes, dates and reasons alongside each set of assumptions. If one alternative was calculated against a different recorded balance, the page says so.

Duplicating `Laptop Purchase` creates `Laptop Purchase (Copy)` as a new draft with the same assumptions and no result. Rename it `Laptop + Emergency Fund`, edit structured assumptions through Q, save and run explicitly. The original remains unchanged. Archive an alternative to hide it from the default library; restore it later using the same ID and history.

## Validation strategy and non-goals

Focused tests cover status filters, literal search, pagination/ties, metadata normalization, independent copies, archive/restore, exact result reuse, shared/different assumption multisets, bounds, staleness, version rejection, baseline warnings and cross-tenant failures. Financial-state snapshots verify library operations leave accounts, transactions, goals, obligations and health rows untouched. Query-count tests guard against per-card child queries. Real PostgreSQL tests cover fresh migrations, Q/R downgrade/upgrade/backfill, owner locking under concurrent duplicates/saves/lifecycle/metadata changes, and duplicate rollback. Q's existing isolation/idempotency tests remain enabled.

Frontend tests cover cards/search/tabs/paging, open/rename/duplicate/archive/restore, bounded selection, matrix/assumptions, unknowns, errors/loading and both languages. Desktop/mobile browser tests cover the complete lifecycle, rename focus restoration, comparison-region keyboard access, responsive containment and Bengali rendering, while asserting no simulation is triggered by comparison. Full backend/frontend suites, browser tests, OpenAPI generation/freshness, Python compilation and whitespace checks are required before handoff.

No second calculation engine, Monte Carlo, new cashflow/runway/goal/health formulas, tax/investment optimization, autonomous actions, ranking/guarantees, automatic financial application, goal/budget mutation, transfers, bank execution, speculative prediction, destructive history deletion, or LLM arithmetic is added.
