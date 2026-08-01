from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from keryx.config import default_config_text, load_config
from keryx.models import SyncEvent, SyncResult
from keryx.publish import publish


class ConfigPublishTests(unittest.TestCase):
    def test_default_config_loads_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "keryx.toml"
            path.write_text(default_config_text(), encoding="utf-8")
            config = load_config(path)
            self.assertEqual(config.state_path, root.resolve() / ".keryx/state.json")
            self.assertEqual(config.output_dir, root.resolve() / "public")
            self.assertEqual(config.sources[0].kind, "intern-engine")

    def test_publish_writes_versioned_json_and_atom(self) -> None:
        job = {
            "id": "job_123",
            "company": "Example & Co",
            "title": "Software <Intern>",
            "url": "https://jobs.example.com/123?a=1&b=2",
            "locations": ["Remote"],
            "status": "open",
        }
        event = SyncEvent("evt_123", "opened", "job_123", "2026-08-01T00:00:00Z", job)
        result = SyncResult(False, (job,), (event,), (event,), {"feed": 1}, {})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            publish(output, result, generated_at="2026-08-01T00:00:00Z")
            jobs = json.loads((output / "jobs-v1.json").read_text(encoding="utf-8"))
            self.assertEqual(jobs["schema_version"], 1)
            self.assertEqual(jobs["count"], 1)
            atom = (output / "feed.xml").read_text(encoding="utf-8")
            self.assertIn("Example &amp; Co", atom)
            self.assertIn("a=1&amp;b=2", atom)


if __name__ == "__main__":
    unittest.main()
