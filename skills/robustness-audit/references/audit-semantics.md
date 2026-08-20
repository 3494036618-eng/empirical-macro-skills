# Audit Semantics

## State Priority

1. Exact rerun failure:
   `failed + blocked + not_assessed + stop_ship`.
2. A required check is missing, errored, failed, or blocked:
   `partial + blocked + inconclusive + stop_ship`.
3. A frozen decision rule fails:
   `success + review_required + sensitive + review_required`.
4. All required declared checks pass:
   `passed_declared_checks`; post-result plans remain `review_required`.

`pre_result_bound` is legal only with a verifiable pre-result binding.
Otherwise use `post_result_exploratory`.

## Threat Ledger

Upstream threat status is immutable. An audit records only:

- `unexamined`
- `partially_examined`
- `no_sensitivity_detected`
- `sensitivity_detected`

An upstream `open` threat never becomes `mitigated` because a sensitivity
check passed.

## Completeness

The planned and observed alternative ID sequences must match exactly. Every
alternative uses a unique estimator request ID. Failures and timeouts remain
in check evidence and contribute to an inconclusive Stop-Ship decision.
