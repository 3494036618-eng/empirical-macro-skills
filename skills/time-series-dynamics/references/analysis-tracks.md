# Analysis Tracks

## identified_shock_irf

Required:

- `analysis_track=identified_shock_irf`
- `estimand_type=impulse_response`
- `method_profile=observed_shock_linear_lp`
- `claim_eligibility=causal_candidate`
- approved shock Artifact with checksum, direction, unit, license, and provenance

The result remains `review_required`. Numerical estimation does not approve the
shock exogeneity assumption.

## conditional_dynamic_association

Required:

- `analysis_track=conditional_dynamic_association`
- `estimand_type=conditional_projection_path`
- `method_profile=observed_policy_change_projection`
- `claim_eligibility=associational_only`
- no shock Artifact

The coefficient at horizon `h` is the conditional linear projection coefficient
of the future outcome path on the observed policy variable, given the declared
controls. It is not an impulse response.

## Shared Numerical Kernel

Both tracks use the same horizon regression, transformation, lag, covariance,
and export code. Sharing numerical code prevents avoidable duplication; the
request Schema and claim policy prevent semantic reuse.
