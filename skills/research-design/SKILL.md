---
name: "research-design"
description: "Use when empirical-macro research design is the complete single-stage task; for end-to-end or multi-stage research, invoke empirical-macro first."
license: Apache-2.0
compatibility: "Requires Python 3.12; scripts use uv; OpenAI4S can load the optional kernel.py sidecar."
---

# Research Design

Use this Skill to turn a macroeconomic research idea into validated intake,
request, plan, identification-audit, and data-requirement artifacts.

## Entry Boundary

Use this Skill directly only when the user asks for research design as the
complete task. For a new study that also requests data, estimation, robustness,
or reporting, invoke `empirical-macro` first and enter here only after its
`RouteDecision` selects `route_research_design`.

## Required Workflow

1. Classify the current input as `idea_only`, `question_ready`,
   `design_ready`, or `execution_ready`; do not classify the user.
2. For vague input, offer 2-3 distinct candidate questions and register at
   most 3 high-impact clarifications.
3. Record every compiled field as `user_provided`, `inferred_from_text`,
   `recommended_default`, or `unresolved`.
4. Preserve user-provided and expert-locked fields. Never overwrite them with
   a default or inferred value.
5. If the user cannot answer a required clarification, apply only the
   registered descriptive or associational safe downgrade.
6. Treat validated JSON as authoritative. Run the deterministic pipeline; do
   not use prose as a cross-module contract.
7. Keep causal and structural candidates in `review_required`. Identification
   assumptions, shock exogeneity, parallel trends, exclusion restrictions, and
   structural stability are never auto-approved.
8. Send data work to `macro-data` only through a request artifact validated by
   its external Schema. Never import `macro_data` internals.
9. Validate the exported bundle and report all unresolved issue codes.

## Decision Contract

Use these outcomes exactly:

| Condition | Action | `claim_eligibility` |
|---|---|---|
| Intake has a pending required clarification | `block` | `not_eligible` |
| A requested causal/structural design lacks or violates a hard prerequisite | `block` | `not_eligible` |
| High-risk prerequisites exist but assumptions still need independent review | `review` | `causal_candidate` or `structural_candidate` |
| A macro-data Artifact mismatches variables, indicators, entities, frequency, or time scope | `block` | preserve the research design's claim class; never mark data ready |
| A low-risk design has zero issues and a validated aligned macro-data Artifact | `ready` | its controlled descriptive, associational, or predictive class |

A failed causal request is not a safe downgrade. Do not relabel the same plan
as `descriptive_only` or `associational_only`. A lower-claim alternative must
be a separate candidate selected by the user, with updated field provenance.

Use canonical issue codes instead of inventing labels:

| Gate | Canonical issue code |
|---|---|
| `idea_only` has fewer than two candidates | `idea_only_requires_candidate_choice` |
| Raw or unresolved policy shock identification | `shock_identification_unresolved` |
| Macro concept/role mismatch | `concept_role_mismatch` |
| Macro indicator coverage mismatch | `indicator_coverage_mismatch` |
| Macro entity identity mismatch | `entity_identity_mismatch` |

For a gate-only decision, return only the decision and existing evidence.
Candidate generation and field-provenance compilation are separate requested
operations; do not synthesize candidates, fields, or provenance to fill a gate
response. Emit every applicable canonical code and no aliases. A missing
exposure concept and indicator triggers both `concept_role_mismatch` and
`indicator_coverage_mismatch`.
Apply codes only to structured fields that already exist. Text inside an
unanswered clarification does not instantiate that candidate's shock,
treatment, estimand, or data fields. A pending intake with no selected causal
candidate emits only its intake gate codes.

## Command

```bash
uv run python scripts/run_research_design.py \
  --intake-json intake.json \
  --request-json request.json \
  --macro-schema ../macro-data/schemas/macro-data-request.schema.json \
  --macro-request-json macro-data-request.json \
  --output output
```

Omit `--macro-request-json` while data identity remains unresolved. The plan
will stay blocked or review-required instead of inventing a data request.

## Boundaries

This Skill does not:

- estimate regressions, VARs, local projections, treatment effects, forecasts,
  or structural parameters;
- mark VAR or SVAR as executable in the current suite; `var_svar` is a
  deferred design candidate, while Local Projection is the only implemented
  dynamic estimator;
- claim causality, select methods from significance, or invent instruments,
  shocks, comparison groups, horizons, vintages, or missing data;
- silently shrink entities, periods, variables, or the research question;
- call DataPro, World Bank, CUA, or other live sources;
- treat comparison-only data as eligible for estimation.

An Agent must not replace a deferred design with handwritten `statsmodels`
VAR/SVAR code. Return the deferred candidate for review or use an eligible
Local Projection candidate when its prerequisites and the user's request
permit it.

## Failure Rules

Fail closed or require review when the selected candidate is not registered,
field provenance is incomplete, the estimand is partial, method prerequisites
are absent, a forecast lacks point-in-time protocol, a high-risk design lacks
independent review, the macro-data Artifact is unvalidated, or any checksum
does not match.

## References

- [Research taxonomy](references/research-taxonomy.md)
- [Design cards](references/design-cards.md)
- [Identification assumptions](references/identification-assumptions.md)
- [Forecasting design](references/forecasting-design.md)
- [Expert review policy](references/expert-review-policy.md)

## OpenAI4S Runtime

OpenAI4S may import `kernel.py` and call `run()`. Check
`kernel.requirements()["imports"]` with `host.env.list_dependencies()` first.
If packages are missing, ask the user before calling
`host.env.create(packages=kernel.requirements()["pip"])`. Do not install
packages or create a virtual environment from inside this Skill.

For a new monthly or quarterly dynamic question, call the high-level public
entry instead of reading Schemas or manually constructing `intake` and
`request` dictionaries:

```python
import importlib

design = importlib.import_module("research-design.kernel")
result = design.run_dynamic_question(
    user_question,
    outcome="美国消费者价格通胀",
    policy_variable="美联储货币政策收紧",
    entity="USA",
    start="1969-01",
    end="2023-12",
    frequency="M",
    horizon=16,
    output_dir="output/research-design",
    shock_identification="unresolved",
)
```

Use `shock_identification="unresolved"` unless the user supplied a concrete
narrative, external-instrument, statistical-innovation, or randomized shock
source. The word "unexpected" does not by itself prove identification. Pass
the result to `empirical-macro.kernel.decide_after_stage()` and obey
`stopped`.
