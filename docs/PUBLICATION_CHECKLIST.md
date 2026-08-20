# Publication Checklist

Publish only the generated public snapshot directory. Never initialize or push
the parent development workspace.

## Required files

- `README.md`
- `INSTALL.md`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `plugin.json`
- `skills/`

## Required checks

1. `python scripts/scan_public_release.py .` returns `valid: true`.
2. The public snapshot validator returns `valid: true`.
3. All six post-install quick validators return `valid: true`.
4. A fresh install creates six managed runtime environments.
5. Same-version upgrade and managed uninstall pass.
6. No `.venv`, cache, editor, agent-run, or Git metadata is present.
7. No personal path, email address, credential, raw trace identifier, private
   dataset, or internal transcript is present.

## Beta disclosure

The README must retain the Beta notice until direct host smoke tests and the
full routing certification suite are complete. Do not claim full host
certification before those gates pass.

## Human review

Before creating a public repository:

1. Review both language sections in the rendered `README.md`.
2. Review the complete top-level file list.
3. Review `LICENSE` and `THIRD_PARTY_NOTICES.md`.
4. Confirm the repository name and public owner.
5. Confirm that no development workspace history will be pushed.
