from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .config import Config, default_config_text, load_config
from .engine import event_dicts, synchronize
from .providers import fetch_source
from .publish import publish
from .store import append_events, atomic_write_json, load_state


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sync(config: Config) -> int:
    snapshots = []
    errors: dict[str, str] = {}
    enabled = [source for source in config.sources if source.enabled]
    if not enabled:
        raise ValueError("no sources are enabled")
    for source in enabled:
        try:
            snapshots.append(fetch_source(source))
        except (OSError, ValueError) as error:
            errors[source.name] = str(error)
    if not snapshots:
        detail = "; ".join(f"{name}: {message}" for name, message in errors.items())
        raise RuntimeError(f"every source failed; state was not changed ({detail})")
    now = _now()
    state = load_state(config.state_path)
    updated, result = synchronize(
        state,
        tuple(snapshots),
        now=now,
        close_after_misses=config.close_after_misses,
        errors=errors,
    )
    atomic_write_json(config.state_path, updated)
    append_events(config.events_path, event_dicts(result.events))
    publish(config.output_dir, result, generated_at=now)
    open_count = sum(job["status"] == "open" for job in result.jobs)
    mode = "baseline" if result.baseline else f"{len(result.events)} change(s)"
    print(f"Keryx synchronized {open_count} open roles ({mode}).")
    for name, message in errors.items():
        print(f"warning: {name}: {message}", file=sys.stderr)
    print(f"Published feeds to {config.output_dir}")
    return 0


def _list(config: Config, *, status: str, limit: int) -> int:
    jobs = load_state(config.state_path)["jobs"].values()
    selected = [job for job in jobs if status == "all" or job["status"] == status]
    selected.sort(key=lambda job: (job["company"].casefold(), job["title"].casefold()))
    for job in selected[:limit]:
        locations = ", ".join(job["locations"]) or "Location not stated"
        print(f"{job['company']} — {job['title']} | {locations}\n  {job['url']}")
    print(f"Showing {min(limit, len(selected))} of {len(selected)} role(s).")
    return 0


def _init(path: Path, *, force: bool) -> int:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_config_text(), encoding="utf-8")
    print(f"Created {path}")
    print("Run `keryx sync` to establish the initial no-alert baseline.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="keryx", description="Open job-change feeds")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, default=Path("keryx.toml"))
    commands = parser.add_subparsers(dest="command", required=True)
    initialize = commands.add_parser("init", help="create a starter configuration")
    initialize.add_argument("--force", action="store_true")
    commands.add_parser("sync", help="fetch sources, update state, and publish feeds")
    listing = commands.add_parser("list", help="show locally tracked roles")
    listing.add_argument("--status", choices=("open", "closed", "all"), default="open")
    listing.add_argument("--limit", type=int, default=25)
    commands.add_parser("doctor", help="validate configuration and report paths")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "init":
            return _init(arguments.config, force=arguments.force)
        config = load_config(arguments.config)
        if arguments.command == "sync":
            return _sync(config)
        if arguments.command == "list":
            if arguments.limit < 1:
                raise ValueError("--limit must be at least 1")
            return _list(config, status=arguments.status, limit=arguments.limit)
        if arguments.command == "doctor":
            print(
                json.dumps(
                    {
                        "config": str(config.path),
                        "state": str(config.state_path),
                        "events": str(config.events_path),
                        "output": str(config.output_dir),
                        "sources": [source.name for source in config.sources if source.enabled],
                    },
                    indent=2,
                )
            )
            return 0
    except (FileExistsError, FileNotFoundError, OSError, RuntimeError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
