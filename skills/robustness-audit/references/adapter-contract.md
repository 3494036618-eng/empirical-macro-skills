# Adapter Contract

The audit core never imports estimator internals. The time-series adapter may
call only:

```text
scripts/run_time_series_dynamics.py
scripts/validate_bundle.py
```

The adapter capability is an explicit validated input. Its `adapter_id` and
`adapter_version` must match the frozen audit plan. Test fixtures are not
production configuration.

Each derived request:

- starts from the immutable baseline request;
- applies only one declared allowlisted patch;
- receives `tsd-request-<alternative hash suffix>`;
- preserves the baseline estimand fingerprint;
- is executed in an isolated process group with a bounded timeout.

Sample-window alternatives receive a derived macro-data handoff whose
`observation_period` and result ID match the derived request. The baseline
macro-data Artifact remains unchanged.

The adapter returns success, non-zero exit, timeout, or invalid-bundle
evidence. It never drops a record or converts an error to a pass.
