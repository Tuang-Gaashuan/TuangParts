import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from warehouse.git_sync import init_or_update, read_unread_event_files, load_sync_state


class GitSyncTests(unittest.TestCase):
    def _run(self, cwd, *args):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)

    def _remote(self, root):
        work = root / "seed"
        bare = root / "remote.git"
        work.mkdir()
        self._run(work, "init", "-b", "main")
        event_dir = work / "events" / "2026" / "08" / "24"
        event_dir.mkdir(parents=True)
        for n in (1, 2):
            (event_dir / f"event-{n}.json").write_text(json.dumps({
                "event_id": f"event-{n}", "part_id": "part-1", "delta": -n,
            }), encoding="utf-8")
        (work / "README.md").write_text("test", encoding="utf-8")
        self._run(work, "add", ".")
        self._run(work, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "initial")
        self._run(root, "init", "--bare", str(bare))
        self._run(work, "remote", "add", "origin", str(bare))
        self._run(work, "push", "origin", "main")
        return bare

    def test_clone_and_read_event_files_from_file_remote(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bare = self._remote(root)
            local = root / "client"
            cfg = {"remote_url": str(bare), "local_dir": str(local), "branch": "main", "events_dir": "events"}
            result = init_or_update(cfg)
            self.assertTrue(result["ok"], result)
            events = read_unread_event_files(cfg)
            self.assertTrue(events["ok"], events)
            self.assertEqual(events["count"], 2)
            self.assertEqual(set(events["read_event_ids"]), {"event-1", "event-2"})
            again = read_unread_event_files(cfg)
            self.assertTrue(again["ok"], again)
            self.assertEqual(again["count"], 0)
            self.assertEqual(set(load_sync_state(cfg)["read_event_ids"]), {"event-1", "event-2"})

    def test_missing_event_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bare = self._remote(root)
            local = root / "client"
            cfg = {"remote_url": str(bare), "local_dir": str(local), "branch": "main", "events_dir": "events"}
            self.assertTrue(init_or_update(cfg)["ok"])
            bad = local / "events" / "2026" / "08" / "24" / "bad.json"
            bad.write_text('{"delta": -1}', encoding="utf-8")
            self._run(local, "add", str(bad.relative_to(local)))
            self._run(local, "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "bad event")
            self._run(local, "push", "origin", "main")
            self._run(local, "fetch", "origin", "main")
            result = read_unread_event_files(cfg, since_commit="")
            self.assertFalse(result["ok"])
            self.assertIn("event_id", result["message"])

    def test_missing_configuration_is_explained(self):
        result = init_or_update({"remote_url": "", "local_dir": ""})
        self.assertFalse(result["ok"])
        self.assertIn("仓库地址", result["message"])


if __name__ == "__main__":
    unittest.main()
