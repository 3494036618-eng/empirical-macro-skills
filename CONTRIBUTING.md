# Contributing

Contributions should preserve scientific traceability, privacy, and the
fail-closed workflow.

## Before opening a pull request

1. Keep each Skill self-contained under `skills/<skill-name>/`.
2. Preserve the `SKILL.md` frontmatter contract: `name` and `description`.
3. Add or update tests for behavior, schemas, and failure cases.
4. Pin runtime dependencies in the Skill's `uv.lock`.
5. Do not add credentials, personal data, private paths, or internal run logs.
6. Run the public release scanner.

## Local validation

Run the changed Skill's tests:

```bash
uv run --project skills/<skill-name> --locked pytest
```

Run its quick validator:

```bash
uv run --project skills/<skill-name> --locked --no-dev \
  python skills/<skill-name>/scripts/quick_validate.py
```

Run the repository privacy and structure scan:

```bash
python scripts/scan_public_release.py .
```

## Scientific requirements

- Bind claims to explicit evidence and artifact checksums.
- Separate identified causal designs from conditional associations.
- Treat missing required artifacts as blocking errors.
- Preserve unfavorable, failed, and timed-out robustness checks.
- Do not silently replace data sources, units, entities, frequencies, or
  sample windows.

## Pull request scope

Keep changes focused. A pull request should state:

- the user-visible behavior being changed;
- the contracts or artifacts affected;
- the tests added or updated;
- any new external dependency, service, permission, or cost;
- known limitations.

## Public fixtures

Fixtures must be synthetic, openly licensed, or redistributable. Do not commit
private datasets or provider responses whose redistribution terms are unclear.
