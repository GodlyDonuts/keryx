# Keryx

**Know when a role opens—not after everyone else does.**

Keryx is an open-source, source-neutral job discovery engine. It reads public job feeds,
normalizes their incompatible schemas, merges duplicate listings, tracks role lifecycles, and
publishes stable JSON and Atom feeds for people, bots, and other career tools.

Keryx is deterministic and local-first. It does not require an AI model, an account, a hosted
database, or a model API key.

## What it does

- Combines multiple public job sources behind one versioned schema.
- Deduplicates tracking URLs and cross-posted roles conservatively.
- Establishes a silent first-run baseline so setup never produces an alert flood.
- Reports openings, reopenings, and closures as durable events.
- Requires repeated complete-source misses before inferring that a role closed.
- Preserves source-level provenance and health instead of hiding partial failures.
- Publishes `jobs-v1.json`, `events-v1.json`, `status.json`, and an Atom feed.

It deliberately does **not** submit applications, manufacture job facts, rank candidates with a
black-box model, or treat source content as instructions.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

The product, command, and Python module are all named `keryx`. The optional PyPI distribution will
be published as `keryx-jobs` because the unrelated bare `keryx` distribution name is already taken.

```console
git clone https://github.com/GodlyDonuts/keryx.git
cd keryx
uv sync
uv run keryx init
uv run keryx doctor
uv run keryx sync
uv run keryx list --limit 10
```

The first sync creates a baseline and intentionally emits no opening events. Later syncs emit only
changes discovered after that baseline.

## Configure sources

`keryx init` creates `keryx.toml`. The starter source uses the public JSON feed from the
MIT-licensed [Summer 2027 Internship Engine](https://github.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships).
Keryx is not affiliated with that project, and its adapter keeps the upstream source visible
in every record.

Supported source kinds in the first release:

| Kind | Expected input |
|---|---|
| `intern-engine` | The versioned JSON object published by the Summer 2027 Internship Engine |
| `simplify` | A Simplify/Pitt CSC `listings.json` array |

Add a source without changing Keryx's state or output contract:

```toml
[[sources]]
name = "community-list"
kind = "simplify"
url = "https://example.invalid/listings.json"
enabled = true
```

Only use feeds whose terms and licenses permit your intended use. Keryx contains adapters,
not copied upstream datasets.

## Outputs

After each successful sync:

```text
public/
├── jobs-v1.json       current open roles
├── events-v1.json     bounded, cursor-friendly change history
├── feed.xml           Atom representation of that history
└── status.json        source counts, failures, and feed health
```

Private operational state lives under `.keryx/` by default. Public event outputs retain the
most recent 1,000 transitions, and every event has a stable ID so consumers can safely maintain a
delivery cursor even when they skip a synchronization.
See [the schema documentation](docs/schema.md) for the compatibility contract.

## Design principles

1. **Official posting URLs are the destination.** Community lists are discovery sources, not
   authoritative job descriptions.
2. **Absence is not closure unless the snapshot was complete.** Temporary source failures never
   close roles.
3. **Public data and private subscriptions stay separate.** Keryx's feed contains jobs;
   downstream products own personal filters, seen state, and credentials.
4. **No initial alert storm.** Existing jobs become a baseline; only later changes become alerts.
5. **Consumers are independent.** A Discord bot, desktop tool, RSS reader, or career application
   can all consume the same versioned feed.

Read [the architecture](docs/architecture.md), [security policy](SECURITY.md), and
[contribution guide](CONTRIBUTING.md) before adding a provider.

## Development

```console
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run python -m unittest discover -s tests -v
uv build
```

Keryx is available under the [MIT License](LICENSE).
