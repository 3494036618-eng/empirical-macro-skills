# Jordà–Taylor Example 5 Benchmark

## Evidence

- Paper: Jordà and Taylor, “Local Projections,” JEL 63(1), 2025.
- AEA/openICPSR: https://doi.org/10.3886/E208590V1
- Code: https://github.com/ojorda/JEL-Code
- Commit: `655696c1c576b7537c5a939d2c261f0a111ae663`
- License: CC0-1.0

## Frozen Specification

```text
sample: 1985Q1–2007Q4
outcome: lcpi
identified shock: rr_shock
controls: four lags of dlrgdp, dlcpi, dstir
horizons: 0–17
dependent variable: lead_h(lcpi) - lag_1(lcpi)
covariance: Newey–West/Bartlett, maxlags=17
```

The causal-candidate benchmark uses `rr_shock`. The association track replaces
the exposure with `dstir` and must be labelled `conditional_projection_path`;
it is not an impulse response.

## Integrity

```text
archive:
8fa0ad974eda885e7fc9570b601ca619f4b6216d6605cd2e8e1c7f2fbac246f6

aggregatedata_final.dta:
19ca23c02ff86dd1f7c78018e4052eea98de4ecca879f467c3a9d57f55b38d2c

all.log:
02c5f11a8417403b24306762feeb7f5b1133644424dcc461cbd79d4b903b5538
```
