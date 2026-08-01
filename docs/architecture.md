# Architecture

RoleBeacon separates public discovery from private delivery.

```text
public sources -> provider adapters -> normalized observations
                                      |
                                      v
                              canonical identity
                                      |
                                      v
                         lifecycle state + provenance
                                      |
                     +----------------+----------------+
                     v                v                v
                current jobs      change events     health
                     |                |                |
                     +----------------+----------------+
                                      v
                              JSON and Atom feeds
```

## Provider boundary

Providers translate one external schema into `Observation` records and state whether their
snapshot is complete. They do not deduplicate, notify users, mutate application records, or decide
what another product should display.

## Identity and deduplication

RoleBeacon canonicalizes official URLs by removing fragments, ordinary tracking parameters, and a
terminal `/apply`. Job-identifying query parameters are retained. The canonical URL is hashed into
a stable opaque RoleBeacon ID. When no usable URL exists, source name and source-native ID form the
identity.

This is intentionally conservative. Similar company/title/location text is not enough to merge two
records because employers frequently publish distinct roles with the same title.

## Lifecycle

Each job contains one source record per provider. A job remains open while any source says it is
active. An explicit inactive record closes that source immediately. Absence increments a miss
counter only after a complete snapshot; incomplete or failed providers leave existing state
untouched. The default closure threshold is two complete misses.

The first successful sync is a baseline. It populates state but emits no opening events. Every
later transition is emitted with an event ID and timestamp. The latest 1,000 events remain in the
public feed so an intermittently connected consumer can catch up using its own event cursor.

## Publication boundary

State and each output file are written atomically. The append-only local event ledger is fsynced
separately. Consumers should use event IDs or their own cursor to guarantee idempotent delivery.

## Future boundaries

- Direct Greenhouse, Lever, Ashby, Workday, and other ATS adapters
- Configurable scope filters applied at publication rather than source ingestion
- Signed feed manifests
- A static dashboard over the same public schema
- Exactly-once webhook and Discord delivery as a separate consumer package
