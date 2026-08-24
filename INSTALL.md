# Install the Empirical Macro Skill Suite

## Quick Install

Use the npm entry point to select a supported Agent:

```bash
npx empirical-macro-skills
```

The npm command delegates to the Python installer in this repository. It does
not contain a separate Skill implementation.

## Prerequisites

- Node.js 20 or newer for the `npx` entry point
- Python 3.12
- `uv`

For directory-based hosts, the installer creates a locked `.venv` inside each
installed Skill and runs that Skill's quick validator before publishing files.
OpenAI4S uses its managed environment instead.

## Unified Installer

Run from the extracted repository root. The same `skills/` directories are
installed for every host; there is no separate OpenAI4S package.

Use `generic` for any Agent that supports a local Agent Skills directory:

```bash
uv run --isolated --project skills/empirical-macro --locked --no-dev \
  python scripts/install.py install \
  --host generic \
  --target-root /path/to/your-agent/skills
```

The target directory is controlled by the user. Preserve each Skill directory
and its `SKILL.md` entry point.

## Known Host Presets

### Trae

Run from the extracted public snapshot root:

```bash
uv run --isolated --project skills/empirical-macro --locked --no-dev \
  python scripts/install.py install \
  --host trae \
  --target-root ~/.trae/skills
```

### Codex

```bash
uv run --isolated --project skills/empirical-macro --locked --no-dev \
  python scripts/install.py install \
  --host codex \
  --target-root ~/.agents/skills
```

### Claude Code

```bash
uv run --isolated --project skills/empirical-macro --locked --no-dev \
  python scripts/install.py install \
  --host claude-code \
  --target-root ~/.claude/skills
```

Installation is atomic. If dependency setup or any quick validator fails, the
existing target remains unchanged.

### OpenAI4S

Run the same installer from the OpenAI4S project environment. Replace both
example paths with the corresponding local directories:

```bash
uv run --isolated --project /path/to/OpenAI4S --locked --no-dev \
  python /path/to/empirical-macro-skills/scripts/install.py \
  install --host openai4s --scope personal
```

For a project-scoped installation:

```bash
uv run --isolated --project /path/to/OpenAI4S --locked --no-dev \
  python /path/to/empirical-macro-skills/scripts/install.py install \
  --host openai4s \
  --scope project \
  --project-id <openai4s-project-id>
```

OpenAI4S installs the same six directories through its public
`SkillVersionService`. If any package or sidecar fails validation, the suite
installer rolls changed Skills back to their previous active versions and
deactivates newly installed Skills.

File installation and runtime readiness are separate checks. In an OpenAI4S
cell, import the selected Skill's `kernel.py`, then inspect
`kernel.requirements()`:

```python
requirements = kernel.requirements()
host.env.list_dependencies(requirements["imports"])
```

Prefer an existing environment that satisfies the imports. If packages remain
missing, obtain user approval before using OpenAI4S's managed mutation:

```python
host.env.create(
    name="empirical-macro",
    packages=requirements["pip"],
)
```

Do not run `pip`, `uv`, or create `.venv` directories inside an installed
Skill.

## Uninstall

Use the same snapshot and host, changing the operation to `uninstall`:

```bash
uv run --isolated --project skills/empirical-macro --locked --no-dev \
  python scripts/install.py uninstall \
  --manifest ~/.trae/skills/empirical-macro-install-manifest.json \
  --host trae \
  --target-root ~/.trae/skills
```

Uninstall removes unchanged managed files and installer-managed runtime
environments. User-created or modified files are retained.

OpenAI4S uninstall and rollback use its Skills UI or `SkillVersionService`, so
retained version history stays under platform control.
