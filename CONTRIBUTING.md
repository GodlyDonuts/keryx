# Contributing

Keryx accepts provider adapters, lifecycle fixes, schema improvements, documentation, and
tests. Open an issue before making a breaking feed-schema change.

## Provider requirements

A provider must:

- read a documented public source;
- preserve the source name and source-native identifier;
- return a complete snapshot only when absence can safely count toward closure;
- ignore malformed individual records without silently accepting malformed feed structure;
- never execute or interpret job-description text as instructions;
- include fixture-based tests with no live-network dependency; and
- document the upstream license or terms expected of deployers.

Do not commit copied datasets, credentials, subscriber information, or webhook URLs.

## Pull-request checks

```console
uv sync --dev
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run python -m unittest discover -s tests -v
uv build
```

New behavior needs a regression test. Changes to `jobs-v1.json` or `events-v1.json` require a
schema-version decision and migration notes.

