# Security Policy

## Supported release

Security fixes are applied to the latest Beta release.

## Reporting a vulnerability

Use the repository's private GitHub Security Advisory form. Do not open a
public issue for credentials, private data exposure, command injection, path
traversal, unsafe archive handling, or dependency-supply-chain concerns.

Include:

- the affected Skill and file;
- reproduction steps;
- expected and observed behavior;
- whether credentials or private data may have been exposed;
- a minimal proof of concept without real secrets.

## Credential policy

This repository does not contain credentials. Live connector credentials must:

- be supplied by the agent host or process environment;
- never be printed in logs or model output;
- never be written into Skill artifacts;
- use the minimum provider permissions required.

Do not commit `.env` files, API keys, authorization headers, cookies, raw trace
identifiers, private certificates, or local credential stores.

## External data and code

Skills may execute Python and may optionally connect to external data
providers. Before running a Skill:

1. Read its `SKILL.md`, scripts, dependencies, and external-service notes.
2. Confirm the requested data and destination are appropriate.
3. Use explicit approval for live or potentially billable calls.
4. Review generated code and artifacts before execution or publication.

## Privacy

The public release must not contain:

- absolute user or workspace paths;
- personal documents or private datasets;
- raw provider responses containing private identifiers;
- internal agent transcripts or run directories;
- virtual environments, caches, or editor state.

Run the release scanner before publication:

```bash
python scripts/scan_public_release.py .
```
