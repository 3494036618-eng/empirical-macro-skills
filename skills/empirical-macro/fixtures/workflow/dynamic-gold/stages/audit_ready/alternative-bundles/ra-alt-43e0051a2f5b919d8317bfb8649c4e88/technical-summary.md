# Technical Summary

- Analysis track: `identified_shock_irf`
- Estimand: `impulse_response`
- Method profile: `observed_shock_linear_lp`
- Outcome: `lcpi`
- Exposure: `rr_shock`
- Controls: `dlrgdp, dlcpi, dstir`
- Sample: `1985Q1` to `2007Q4`
- Sample policy: `horizon_specific`
- Horizons: `0` to `17`
- Lags: `4`
- Covariance: `HAC`, Bartlett kernel, maxlags `8`
- Interval: `95%` pointwise
- Nobs range: `71` to `88`
- Source: Updated Romer-Romer monetary policy shocks
- Source checksum: `19ca23c02ff86dd1f7c78018e4052eea98de4ecca879f467c3a9d57f55b38d2c`

The dependent variable at horizon h is `100 * (outcome[t+h] - outcome[t-1])`. The exposure coefficient is estimated separately at each horizon.
