---
name: "time-series-dynamics"
description: "Estimate auditable dynamic paths for empirical-macro questions, separating identified-shock impulse responses from noncausal conditional associations."
---

# Time-Series Dynamics

Use this Skill after `research-design` and `macro-data` have produced validated
Artifacts for a dynamic macroeconomic question.

## User Outcome

The final delivery is not a readiness decision. A successful run returns:

- horizon-by-horizon estimates, standard errors, intervals, and sample sizes;
- a CSV table and a nonblank PNG chart;
- diagnostics and input/output checksums;
- a technical summary;
- a plain-language summary with the correct claim boundary.

## Required Workflow

1. Send vague or incomplete research ideas to `research-design`. The user does
   not need to choose Local Projection, controls, or lag order.
2. Require a selected `analysis_track` in the research plan:
   - `identified_shock_irf`; or
   - `conditional_dynamic_association`.
3. Require every macro-data handoff to be `dynamic_response` and
   `analysis_ready`.
4. For `identified_shock_irf`, require an approved, checksummed
   `shock-identification-artifact`.
5. For `conditional_dynamic_association`, reject any shock Artifact and keep
   `claim_eligibility=associational_only`.
6. Validate request and cross-Artifact consistency before loading data.
7. Run the frozen horizon-by-horizon OLS and HAC profile without selecting
   specifications from significance.
8. Validate the complete exported bundle before reporting results.

## Decision Contract

| Input state | Analysis | Result semantics |
|---|---|---|
| Valid identified shock | `observed_shock_linear_lp` | `impulse_response`, causal candidate, review required |
| Observed policy change only | `observed_policy_change_projection` | `conditional_projection_path`, associational only |
| Invalid data, scope, frequency, checksum, or claim | none | blocked with canonical issue codes |

An invalid causal request is never silently relabelled. A lower-claim path must
be a separate candidate with its own request ID and field provenance.

## Canonical Agent Decisions

When a caller requests a structured release decision, return only the issue
codes and output filenames defined here. Do not invent synonyms or add
explanatory strings to `required_outputs`.

| Input state | Action | Track | Claim eligibility | Issue codes | Required outputs |
|---|---|---|---|---|---|
| Vague question with no research plan | `route_research_design` | `not_selected` | `not_eligible` | `research_design_required` | none |
| Raw policy change requested as causal | `offer_association` | `conditional_dynamic_association` | `associational_only` | `separate_candidate_required`, `shock_identification_unresolved` | none |
| Valid identified shock and analysis-ready data | `run` | `identified_shock_irf` | `causal_candidate` | none | complete result bundle |
| Association request carrying a shock Artifact | `block` | `conditional_dynamic_association` | `associational_only` | `shock_artifact_forbidden` | none |
| Selected track with non-analysis-ready macro data | `block` | preserve selected track | preserve that track's claim eligibility | `macro_bundle_not_analysis_ready` | none |

`offer_association` does not mutate or execute the failed causal request. It
offers a separate candidate whose request ID and field provenance must differ.
For a selected track, `claim_eligibility` describes result semantics even when
the current request is blocked; only an unselected track uses `not_eligible`.

The complete result bundle reported by an Agent is exactly:

```text
result.json
diagnostics.json
dynamic-path.csv
dynamic-path.png
technical-summary.md
plain-language-summary.md
run-manifest.json
```

## Claim Firewall

Association output must include:

```text
这是一项条件关联分析，不是因果效应估计。
结果不能说明政策变化导致了后续经济变量变化。
```

After that disclaimer, association output must not use `IRF`, `impulse
response`, “冲击响应”, “因果效应”, or “导致”.

Identified-shock output remains a causal candidate. It must not say that
causality has been proved.

## Command

```bash
uv run python scripts/run_time_series_dynamics.py \
  --request-json request.json \
  --research-plan-json research-plan.json \
  --macro-result-json macro-result.json \
  --shock-artifact-json shock-artifact.json \
  --data observations.dta \
  --output output
```

Omit `--shock-artifact-json` only for
`conditional_dynamic_association`.

## Boundaries

V0.1 does not implement LP-IV, VAR, SVAR, state dependence, cumulative
multipliers, mixed-frequency estimation, imputation, seasonal adjustment,
automatic lag selection, or significance-driven specification search.

V0.1 accepts one quarterly macro-data handoff and contiguous horizons `0..H`.
Monthly and multi-bundle requests are blocked at the request contract.

The estimator does not fetch data, construct shocks, rewrite the research
estimand, or generate claims beyond the structured result.

## References

- [Analysis tracks](references/analysis-tracks.md)
- [Claim language policy](references/claim-language-policy.md)
- [Jordà–Taylor Example 5](references/jorda-taylor-example5.md)
