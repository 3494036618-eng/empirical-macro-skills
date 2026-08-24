---
name: "empirical-macro"
description: "Invoke as the mandatory first entry point when starting or resuming end-to-end empirical-macro research on monetary-policy shocks, inflation responses, data, robustness, or synthesis."
license: Apache-2.0
compatibility: "Requires Python 3.12; scripts use uv; OpenAI4S can load the optional kernel.py sidecar."
---

# Empirical Macro

## Overview

Use this Skill as the single entry point for empirical-macro research. The
host Agent interprets natural language, but the deterministic Router and
workflow state decide whether execution is allowed and which atomic Skill is
next.

## Entry Boundary

For an initial request that spans two or more workflow stages, load this Skill
before any atomic Skill and call `empirical-macro.kernel.run()`. The total
controller performs initial routing, research design, the first stage gate,
and workflow-state persistence in one call. Loading several atomic Skills is
not a substitute for running the total controller.

Direct atomic-Skill use remains valid for a clearly scoped single-stage request
whose required upstream Artifacts are already available.

## Invoke When

- The user wants an end-to-end empirical macro study.
- The user starts with a vague macro research idea.
- The user asks to prepare macro data, run supported dynamic analysis, audit
  robustness, compile a final report, or resume a saved workflow.

Do not invoke for non-macro tasks. Do not execute panel, DID, IV, forecasting,
Nowcasting, structural-model, or other unimplemented methods.

## Required Flow

1. Determine the requested `method_family`.
2. Compile method-specific facts into `method_inputs`.
3. Call `empirical-macro.kernel.run()` once for the initial end-to-end request.
4. Obey the returned `status`, `next_action`, and `target_skill`.
5. A `stopped` result ends the current workflow run. Do not create or present
   downstream outputs as validated results of that run.
6. Continue an active workflow only from its validated
   `workflow-state.json`; never infer a passed stage from prose or an existing
   directory.
7. Validate every new Artifact before advancing workflow state.
8. Persist later state changes only through `scripts/run_workflow.py`.

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

## OpenAI4S Runtime

OpenAI4S injects the loaded Skill through its import hook.
Do not search the workspace for this Skill.
Do not call `list_dir` or `glob_files` to locate it, and do not import `host`;
the runtime injects `host` into Python cells.

Use this exact import pattern:

```python
import importlib

router = importlib.import_module("empirical-macro.kernel")
requirements = router.requirements()
```

`requirements()` declares what the Skill needs; it does not mean those packages
are missing. Check `requirements["imports"]` with the native `env_list` tool and
prefer an existing compatible environment. If packages are still missing, ask
the user before calling the native `env_create` tool with
`requirements["pip"]`. If it succeeds, continue in a new Python cell. If it
fails, stop and report the failure.

Never install dependencies with `pip`, `uv`, or `host.bash`, and never create a
virtual environment inside this Skill.

For a new end-to-end supported shock-response study with no existing
Artifacts, call `router.run()` exactly once:

```python
result = router.run(
    user_question=user_question,
    method_family="dynamic_shock_response",
    method_inputs={
        "outcome": "美国消费者价格通胀",
        "policy_variable": "美联储货币政策收紧",
        "entity": "USA",
        "start": "1969-01",
        "end": "2023-12",
        "frequency": "M",
        "horizon": 16,
        "intended_claim": "causal",
        "shock_identification": "unresolved",
    },
    output_dir="output/empirical-macro",
)
print(result)
```

Do not call private helpers or inspect private module source. Do not replace
`shock_identification="unresolved"` with a narrative, external-instrument,
statistical, or structural identification strategy unless the user supplied
that evidence.

If `result["status"] == "stopped"`, return the structured reason and do not
continue that workflow or label later work as its validated output. The host
Agent decides whether to continue the conversation or route a later user
request. `route()` and `decide_after_stage()` remain public only for
single-stage compatibility and diagnostics.
