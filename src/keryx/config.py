from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SourceConfig:
    name: str
    kind: str
    url: str
    enabled: bool = True


@dataclass(frozen=True)
class Config:
    path: Path
    state_path: Path
    events_path: Path
    output_dir: Path
    close_after_misses: int
    sources: tuple[SourceConfig, ...]


def _resolve(base: Path, value: object, *, field: str) -> Path:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    path = Path(text).expanduser()
    return path if path.is_absolute() else base / path


def load_config(path: Path) -> Config:
    resolved = path.expanduser().resolve()
    with resolved.open("rb") as handle:
        raw = tomllib.load(handle)
    base = resolved.parent
    state = raw.get("state", {})
    output = raw.get("output", {})
    policy = raw.get("policy", {})
    raw_sources = raw.get("sources", [])
    if not isinstance(raw_sources, list):
        raise ValueError("sources must be an array of tables")
    sources: list[SourceConfig] = []
    for item in raw_sources:
        if not isinstance(item, dict):
            raise ValueError("each source must be a table")
        name = str(item.get("name", "")).strip()
        kind = str(item.get("kind", "")).strip().casefold()
        url = str(item.get("url", "")).strip()
        if not name or not kind or not url:
            raise ValueError("each source requires name, kind, and url")
        sources.append(
            SourceConfig(name=name, kind=kind, url=url, enabled=bool(item.get("enabled", True)))
        )
    if len({item.name.casefold() for item in sources}) != len(sources):
        raise ValueError("source names must be unique")
    close_after_misses = int(policy.get("close_after_complete_misses", 2))
    if close_after_misses < 1:
        raise ValueError("close_after_complete_misses must be at least 1")
    return Config(
        path=resolved,
        state_path=_resolve(base, state.get("path", ".keryx/state.json"), field="state.path"),
        events_path=_resolve(
            base, state.get("events", ".keryx/events.jsonl"), field="state.events"
        ),
        output_dir=_resolve(base, output.get("directory", "public"), field="output.directory"),
        close_after_misses=close_after_misses,
        sources=tuple(sources),
    )


def default_config_text() -> str:
    return """# Keryx only reads configured public feeds. Add or disable providers here.
[state]
path = ".keryx/state.json"
events = ".keryx/events.jsonl"

[output]
directory = "public"

[policy]
# A role closes only after this many complete snapshots omit it.
close_after_complete_misses = 2

[[sources]]
name = "summer-2027-engine"
kind = "intern-engine"
url = "https://raw.githubusercontent.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships/main/docs/api/jobs.json"
enabled = true
"""
