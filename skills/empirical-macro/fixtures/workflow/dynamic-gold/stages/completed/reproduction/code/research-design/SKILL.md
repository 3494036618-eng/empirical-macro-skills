---
name: "research-design"
description: "Use when an empirical-macro research question, claim, identification strategy, forecast protocol, or macro-data handoff must be clarified before data preparation or estimation."
---

# Research Design

Use this Skill to turn a macroeconomic research idea into validated intake,
request, plan, identification-audit, and data-requirement artifacts.

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
- claim causality, select methods from significance, or invent instruments,
  shocks, comparison groups, horizons, vintages, or missing data;
- silently shrink entities, periods, variables, or the research question;
- call DataPro, World Bank, CUA, or other live sources;
- treat comparison-only data as eligible for estimation.

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
