# Claim Language Policy

## Structured Semantics

| Track | Label | Allowed claim |
|---|---|---|
| `identified_shock_irf` | `impulse_response` | causal candidate, independent review required |
| `conditional_dynamic_association` | `conditional_projection_path` | association only |

## Association Requirements

The plain-language summary must contain the canonical two-sentence disclaimer.
After removing that disclaimer, the summary must not contain:

```text
导致
因果效应
冲击响应
impulse response
IRF
```

The chart title must say “Conditional dynamic association”. The JSON result
must set `causal_language_allowed=false`.

## Identified-Shock Requirements

The summary must say that the result is a causal candidate and that causal
interpretation still requires independent review. Pointwise intervals cannot
support a whole-path significance statement.
