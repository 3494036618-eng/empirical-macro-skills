---
name: "macro-data"
description: "Builds auditable macroeconomic research datasets from validated request JSON. Invoke for country, region, industry, time-series, or panel data preparation before econometric analysis."
---

# Macro Data

Use this Skill to turn a macroeconomic research data request into a traceable
data bundle. The Skill retrieves candidates from DataPro and, after explicit
approval, can query World Bank WDI directly. It validates research semantics
deterministically and exports data plus quality and provenance artifacts.

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
5. Treat every returned record as a candidate. Do not assume `code=0` means the
   research request was satisfied.
6. Lock every eligible DataPro cell as immutable `datapro_primary`. Generate a
   `ResidualGapManifest` from the original matrix; never reduce the requested
   scope to make coverage appear complete.
7. Only after the request policy permits it, send exact residual cells to the
   World Bank WDI Connector. Official results may fill missing cells but may
   never replace a DataPro cell. IMF official completion is not implemented.
8. Validate source, dataset, indicator, entity, frequency, time coverage, unit,
   seasonal adjustment, price basis, definition, release, and vintage.
9. Keep non-target entities in `filtered_candidates`; never mix them into
   normalized output.
10. Preserve unknown metadata as `unknown` or `unresolved`. Names may be retained
   as evidence but cannot become source-provided metadata.
11. Export the full bundle, validate `completion_manifest.json`, and report
    `datapro_only`, `datapro_primary`, `datapro_assisted`, or
    `datapro_attempted` from final estimator cells.
12. Only downstream modules may consume data with
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
