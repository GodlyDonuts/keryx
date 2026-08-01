# Feed schema v1

Keryx publishes four files. Additive fields may appear within schema version 1; consumers must
ignore fields they do not recognize. Renaming, removing, or changing the meaning of a field requires
a new schema version.

## `jobs-v1.json`

The current open-role snapshot:

```json
{
  "schema_version": 1,
  "generated_at": "2026-08-01T12:00:00Z",
  "count": 1,
  "jobs": [
    {
      "id": "job_...",
      "company": "Example",
      "title": "Software Engineer Intern",
      "url": "https://jobs.example.com/123",
      "locations": ["New York, NY"],
      "category": "Software",
      "cycles": ["Summer 2027"],
      "posted_at": "2026-08-01T00:00:00Z",
      "first_seen_at": "2026-08-01T12:00:00Z",
      "last_seen_at": "2026-08-01T12:00:00Z",
      "status": "open",
      "sources": {}
    }
  ]
}
```

## `events-v1.json`

A bounded history of the most recent 1,000 transitions. `event_type` is `opened`, `reopened`, or
`closed`; `batch_count` reports how many were created by the latest synchronization. Consumers
should persist the last processed `event_id`. `baseline: true` guarantees that existing roles were
intentionally suppressed during the first sync.

## `feed.xml`

An Atom representation of the latest transition batch. JSON is the canonical machine interface;
Atom is the convenient subscription interface.

## `status.json`

Contains source observation counts and redacted error messages. `healthy` is false when at least
one enabled source failed, even if other sources allowed the synchronization to complete.
