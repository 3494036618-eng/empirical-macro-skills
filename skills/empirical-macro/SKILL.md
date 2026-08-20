---
name: "empirical-macro"
description: "Routes supported empirical-macro research through design, data, dynamic analysis, robustness, and synthesis. Invoke for end-to-end macro research or to continue an existing workflow."
---

# Empirical Macro

## Overview

Use this Skill as the single entry point for empirical-macro research. The
host Agent interprets natural language, but the deterministic Router and
workflow state decide whether execution is allowed and which atomic Skill is
next.

## Invoke When

- The user wants an end-to-end empirical macro study.
- The user starts with a vague macro research idea.
- The user asks to prepare macro data, run supported dynamic analysis, audit
  robustness, compile a final report, or resume a saved workflow.

Do not invoke for non-macro tasks. Do not execute panel, DID, IV, forecasting,
Nowcasting, structural-model, or other unimplemented methods.

## Required Flow

1. Compile the user request into a candidate `ResearchIntent`.
2. Validate it against `schemas/research-intent.schema.json`.
3. Call `scripts/route_empirical_macro.py`.
4. Obey the returned `RouteDecision`.
5. Call only the target atomic Skill through its public interface.
6. Validate its Artifact before advancing workflow state.
7. Persist state only through `scripts/run_workflow.py`.

Never infer a passed stage from prose, HTTP success, or an existing directory.
Never mutate `workflow-state.json` directly.

## Hard Method Gate

Only these execution families are enabled:

- `dynamic_shock_response`
- `conditional_dynamic_association`

For every other method, return exactly:

```text
当前版本不能执行该方法
```

Do not add explanation, alternatives, data requirements, or other user-facing
content.

## Route Actions

| Action | Target |
| --- | --- |
| `route_research_design` | `research-design` |
| `route_macro_data` | `macro-data` |
| `route_time_series_dynamics` | `time-series-dynamics` |
| `route_robustness_audit` | `robustness-audit` |
| `route_research_synthesis` | `research-synthesis` |
| `method_not_implemented` | Stop with the exact fixed message |
| `out_of_scope` | Do not trigger this suite |
| `completed` | Return the validated final state |

## Safety

- Use relative Artifact paths and SHA-256 checksums.
- Do not store credentials, DataPro raw payloads, model reasoning, or private
  absolute paths in workflow state.
- Resume only after state, registry version, Artifact checksum, and public
  validators pass.
- Default to one external stage per invocation unless the caller explicitly
  approves complete fixture or offline execution.

Read `references/routing-policy.md`, `references/supported-scope.md`, and
`references/artifact-handoffs.md` for the machine-facing policy.
