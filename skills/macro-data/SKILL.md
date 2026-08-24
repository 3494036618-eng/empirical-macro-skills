---
name: "macro-data"
description: "Use when audited macro-data preparation is the complete single-stage task and request JSON is validated; for end-to-end or multi-stage research, invoke empirical-macro first."
license: Apache-2.0
compatibility: "Requires Python 3.12; scripts use uv; OpenAI4S can load the optional kernel.py sidecar."
---

# Macro Data

Use this Skill to turn a macroeconomic research data request into a traceable
data bundle. The Skill retrieves candidates from DataPro and, after explicit
approval, can query World Bank WDI directly. It validates research semantics
deterministically and exports data plus quality and provenance artifacts.

## Entry Boundary

Use this Skill directly only when data preparation is the complete task and a
validated request JSON is available. For a new study that also requests design,
estimation, robustness, or reporting, invoke `empirical-macro` first and enter
here only after its `RouteDecision` selects `route_macro_data`.

## Scope

This Skill prepares data. It does not:

- estimate regressions or causal effects;
- forecast economic outcomes;
- solve structural models;
- generate investment or policy recommendations;
- silently substitute indicators, entities, sources, frequencies, or price
  bases;
- stitch sources, upsample, impute, seasonally adjust, convert currencies, or
  rebase data.

## Required Workflow

1. Treat validated request JSON as authoritative. Use
   `macro-data-request-v0.3.schema.json` for DataPro-first completion;
   `0.2.0-beta` remains a read-only legacy workflow. Natural language may only
   produce a candidate request for review.
2. Record `research_use`: `descriptive_latest`, `panel_analysis`,
   `forecasting`, or `real_time`; apply its metadata gate.
3. Fail closed when entity, indicator, time range, frequency, source policy, or
   research use is absent.
4. Build `ExpectedObservationMatrix`, then query DataPro first. Use the host
   MCP or `scripts/run_datapro_first.py --live`; never request, print, or
   persist a Key.
5. For long ranges, split the request deterministically before retrieval:
   monthly windows contain at most 12 months, quarterly windows at most 8
   quarters, and annual window size must be explicit. Each batch contains one
   entity and one indicator.
6. Treat every returned record as a candidate. Do not assume `code=0` means the
   research request was satisfied.
7. Lock one physical series identity per entity and indicator. Later batches
   must preserve source, dataset, `series_key`, frequency, unit, seasonal
   adjustment, and price basis.
8. Lock every eligible DataPro cell as immutable `datapro_primary`. Generate a
   `ResidualGapManifest` from the original matrix; never reduce the requested
   scope to make coverage appear complete.
9. Re-query contiguous missing windows within the declared call budget. Stop
   with `batch_period_incomplete` if the original matrix remains incomplete.
10. Only after the request policy permits it, send exact residual cells to the
   World Bank WDI Connector. Official results may fill missing cells but may
   never replace a DataPro cell. IMF official completion is not implemented.
11. Validate source, dataset, indicator, entity, frequency, time coverage, unit,
   seasonal adjustment, price basis, definition, release, and vintage.
12. Keep non-target entities in `filtered_candidates`; never mix them into
   normalized output.
13. Preserve unknown metadata as `unknown` or `unresolved`. Names may be retained
   as evidence but cannot become source-provided metadata.
14. Export the full bundle, validate `completion_manifest.json`, and report
    `datapro_only`, `datapro_primary`, `datapro_assisted`, or
    `datapro_attempted` from final estimator cells.
15. Only downstream modules may consume data with
   `delivery_eligibility=analysis_ready`. `comparison_only` and
   `not_deliverable` must not enter estimation.

## Commands

Dry-run the authoritative 0.3 structured request without network calls:

```bash
uv run python scripts/run_datapro_first.py \
  --request-json fixtures/completion/request.valid.json \
  --output output
```

Run DataPro-first live completion. World Bank is called only for permitted
residual WDI cells:

```bash
uv run python scripts/run_datapro_first.py \
  --request-json request-v0.3.json \
  --live \
  --output output
```

Run an offline completion integration fixture:

```bash
uv run python scripts/run_datapro_first.py \
  --request-json request-v0.3.json \
  --datapro-fixture datapro.json \
  --official-fixture world-bank.json \
  --output output
```

Compatibility: run the legacy 0.2 single-provider workflow:

```bash
uv run python scripts/run_macro_data.py \
  --request-json request-v0.2.json \
  --fixture fixtures/sanitized-live/02_china_monthly_cpi.json \
  --output output
```

Inspect a fixture without network access:

```bash
uv run python scripts/probe_datapro.py \
  --inspect-fixture fixtures/sanitized-live/02_china_monthly_cpi.json
```

Validate a bundle:

```bash
uv run python scripts/validate_bundle.py output
```

## Output Contract

The bundle contains:

```text
output/
├── data.csv
├── data.parquet
├── completion_manifest.json
├── request_manifest.json
├── result.json
├── series_catalog.json
├── quality_report.json
├── provenance.json
├── run_manifest.json
├── raw_response.json
└── raw/
    └── <provider>-<request-id>.json
```

Every estimator row records `retrieval_provider`, `source_system`,
`native_series_key`, `origin_role`, `raw_artifact`, and `raw_checksum`. Raw
artifacts are sanitized and must not contain keys, Authorization headers,
cookies, or unsanitized trace identifiers.

## Status Interpretation

- `execution_status`: whether retrieval and processing ran.
- `research_readiness`: whether semantic review is complete.
- `delivery_eligibility`: whether downstream estimation is permitted.

An HTTP 200 or DataPro `code=0` only affects execution status. Frequency,
entity, source, metadata, license, and provenance checks still control research
readiness and delivery.

## Failure Rules

Fail or require review according to `research_use` when:

- no exact candidate remains after source/entity/indicator filtering;
- the observed frequency differs from the requested frequency;
- requested time coverage is incomplete;
- multiple indicator definitions remain;
- required metadata for the declared research use is unavailable;
- the response is empty or malformed;
- checksum or provenance validation fails;
- data-use rights do not permit the requested delivery.

See:

- `references/datapro-contract.md`
- `references/world-bank-contract.md`
- `references/research-readiness.md`
- `references/indicator-identity.md`
- `references/source-policy.md`

## OpenAI4S Runtime

OpenAI4S may import `kernel.py` and call `plan()`, `run_with_datapro()`, or
`validate()`. Check `kernel.requirements()["imports"]` with
`host.env.list_dependencies()` first. If packages are missing, ask the user
before calling `host.env.create(packages=kernel.requirements()["pip"])`.
Professional-dataset retrieval must use the supplied `host` object; never read
an API key or TRAE configuration from this Skill.
