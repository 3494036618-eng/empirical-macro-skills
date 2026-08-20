# Install the Empirical Macro Skill Suite

## Prerequisites

- Python 3.12
- `uv`

The installer creates a locked `.venv` inside each installed Skill and runs
that Skill's quick validator before publishing any files to the target.

## Any Agent

Use `generic` for any Agent that supports a local Agent Skills directory:

```bash
uv run --project skills/empirical-macro --locked --no-dev \
  python skills/empirical-macro/scripts/install_skill_suite.py install \
  --source-root skills \
  --host generic \
  --target-root /path/to/your-agent/skills
```

The target directory is controlled by the user. Preserve each Skill directory
and its `SKILL.md` entry point.

## Known Host Presets

### Trae

Run from the extracted public snapshot root:

```bash
uv run --project skills/empirical-macro --locked --no-dev \
  python skills/empirical-macro/scripts/install_skill_suite.py install \
  --source-root skills \
  --host trae \
  --target-root ~/.trae/skills
```

### Codex

```bash
uv run --project skills/empirical-macro --locked --no-dev \
  python skills/empirical-macro/scripts/install_skill_suite.py install \
  --source-root skills \
  --host codex \
  --target-root ~/.agents/skills
```

### Claude Code

```bash
uv run --project skills/empirical-macro --locked --no-dev \
  python skills/empirical-macro/scripts/install_skill_suite.py install \
  --source-root skills \
  --host claude-code \
  --target-root ~/.claude/skills
```

Installation is atomic. If dependency setup or any quick validator fails, the
existing target remains unchanged.

## Uninstall

Use the same snapshot and host, changing the operation to `uninstall`:

```bash
uv run --project skills/empirical-macro --locked --no-dev \
  python skills/empirical-macro/scripts/install_skill_suite.py uninstall \
  --manifest ~/.trae/skills/empirical-macro-install-manifest.json \
  --host trae \
  --target-root ~/.trae/skills
```

Uninstall removes unchanged managed files and installer-managed runtime
environments. User-created or modified files are retained.
