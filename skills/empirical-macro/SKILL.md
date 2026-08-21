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
before any atomic Skill and call `route()` before web search, data retrieval,
estimation, robustness checks, or report generation. Loading several atomic
Skills is not a substitute for a `RouteDecision`.

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
Artifacts, use this exact routing candidate:

```python
intent = {
    "schema_version": "0.1.0-beta",
    "domain": "empirical_macro",
    "request_kind": "research_idea",
    "method_family": "dynamic_shock_response",
    "has_research_plan": False,
    "has_macro_data_bundle": False,
    "has_estimator_bundle": False,
    "has_robustness_bundle": False,
    "has_workflow_state": False,
}
decision = router.route(intent)
print(decision)
```

`ResearchIntent` contains only routing metadata. Do not add research variables,
sample dates, or identification details; those belong to `research-design`.
Do not call private helpers or inspect private module source. The public
`route()` function validates the contract.

Call `route()` before preparing downstream dependencies, loading atomic Skills,
invoking web or DataPro tools, writing files, or running an estimator. Obey the
returned action and execute only its `target_skill`.
