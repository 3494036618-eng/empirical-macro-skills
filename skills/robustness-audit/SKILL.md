---
name: "robustness-audit"
description: "Use when a validated empirical-macro estimator bundle needs declared robustness checks, sensitivity assessment, or a release decision."
---

# Robustness Audit

Audit a validated estimator bundle without changing its estimand or claim
boundary. Freeze the audit plan before reading result values, then retain every
planned success, failure, timeout, and unfavorable result.

## Required Workflow

1. Require a validated baseline bundle, its exact request and inputs, a
   `research-design` robustness handoff, an audit request, and an adapter
   capability.
2. Compile the audit plan without baseline results, charts, summaries, or
   p-values. If the baseline was already seen, set
   `plan_timing=post_result_exploratory`.
3. Reject any patch outside the capability and handoff allowlists. Never patch
   the estimand, analysis track, claim eligibility, horizons, or source refs.
4. Verify baseline inputs and checksums, then run one exact rerun.
5. Execute every declared alternative with a new alternative ID and request
   ID. Never select, delete, or reorder specifications by significance.
6. Preserve failed, timed-out, invalid, sensitive, and unfavorable
   alternatives in the evidence.
7. Recompute check results, threat ledger, assessment, content IDs, and
   manifest. Publish only after the complete bundle validates.

## Decision Contract

For structured release decisions, use these outcomes and issue codes exactly:

| Input state | Action | Timing | Assessment | Release | Claim | Issue code |
|---|---|---|---|---|---|---|
| Planned unfavorable alternative | `retain_all_results` | preserve | `sensitive` | `review_required` | preserve | `unfavorable_result_retained` |
| Plan created after seeing results | `label_post_result` | `post_result_exploratory` | `not_assessed` | `review_required` | `causal_candidate` | `post_result_plan_cannot_be_pre_registered` |
| Passed association audit requested as causal | `block_claim` | `unknown` | `passed_declared_checks` | `review_required` | `associational_only` | `causal_upgrade_forbidden` |
| Required check missing or errored | `stop_ship` | `unknown` | `inconclusive` | `stop_ship` | preserve | `required_check_missing` |
| Whole-path claim from pointwise intervals | `block_claim` | `unknown` | preserve | `review_required` | preserve | `simultaneous_inference_required` |

`passed_declared_checks` means only that completed, declared checks did not
cross their frozen thresholds. It never proves identification assumptions,
shock exogeneity, causality, or robustness to unexecuted specifications.

## Command

```bash
uv run python scripts/run_robustness_audit.py \
  --audit-request-json audit-request.json \
  --audit-plan-json audit-plan.json \
  --handoff-json robustness-handoff.json \
  --baseline-bundle baseline-bundle \
  --request baseline-request.json \
  --research-plan research-plan.json \
  --macro-result macro-result.json \
  --shock-artifact shock-artifact.json \
  --data observations.dta \
  --adapter-capability-json adapter-capability.json \
  --adapter-root ../time-series-dynamics \
  --output audit-bundle
```

Validate with:

```bash
uv run python scripts/validate_bundle.py audit-bundle
```

## V0.1 Boundary

V0.1 supports `time-series-dynamics` exact rerun plus declared lag, HAC,
sample-policy, and sample-window alternatives. It does not implement shock
predictability, bootstrap, simultaneous bands, leave-block-out, CUSUM,
VAR/SVAR, LP-IV, panel, causal-policy, or forecast adapters.

## References

- [Audit semantics](references/audit-semantics.md)
- [Adapter contract](references/adapter-contract.md)
- [Claim language policy](references/claim-language-policy.md)
