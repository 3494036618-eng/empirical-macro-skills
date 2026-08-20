# Robustness Audit Technical Summary

- Audit plan: `ra-plan-f5827e8808cba1802b8f4dd0f75f6d15`
- Plan timing: `post_result_exploratory`
- Baseline request: `tsd-request-0123456789abcdef`
- Assessment: `passed_declared_checks`
- Release recommendation: `review_required`
- Claim eligibility: `causal_candidate`

## Declared Checks

- `exact_rerun`: `passed` (check `ra-check-93904c8f1da58963089e6bd0364f92b8`)
- `lag_sensitivity`: `passed` (check `ra-check-4381c1fabc0180978aec15efc6c64e44`)
- `covariance_sensitivity`: `passed` (check `ra-check-077835ba64641086db09119bd2ac2655`)
- `sample_policy_sensitivity`: `passed` (check `ra-check-3a9fe68cc441b45c1a8ccb68c340ea1c`)
- `sample_window_sensitivity`: `passed` (check `ra-check-bc473607aa39a18e94dfdbf98833cdc5`)

## Threat Ledger

- `simultaneity`: `unexamined`; upstream remains `open`
- `sample_selection`: `no_sensitivity_detected`; upstream remains `open`
- `structural_break`: `no_sensitivity_detected`; upstream remains `open`
- `multiple_testing`: `no_sensitivity_detected`; upstream remains `open`

Pointwise sensitivity checks do not provide whole-path inference.
No audit result upgrades the baseline identification claim.
