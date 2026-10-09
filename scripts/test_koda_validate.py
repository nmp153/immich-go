import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("validate", Path(__file__).with_name("koda-validate.py"))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.expected = {x: {"name": x, "size": 10, "tags": ["test"], "group": "pair"} for x in ("a", "b")}
        self.state = {"assets": [], "stacks": [{"id": "stack", "primaryAssetId": "a", "assets": [{"id": "a"}, {"id": "b"}]}]}
        for x in ("a", "b"):
            self.state["assets"].append({"id": x, "checksum": x, "ownerId": v.OWNER, "isTrashed": False,
                "isOffline": False, "fileCreatedAt": v.CAPTURE, "localDateTime": v.LOCAL,
                "tags": [{"value": "test"}], "exifInfo": {"timeZone": "UTC-5", "fileSizeInByte": 10},
                "stack": {"id": "stack", "primaryAssetId": "a", "assetCount": 2}})
        self.empty = {"assets": [], "stacks": []}

    def test_accepts_complete_details(self):
        self.assertEqual(v.audit(self.state, self.empty, self.expected), [])

    def test_rejects_observed_missing_tag(self):
        self.state["assets"][1]["tags"] = []
        self.assertIn("b: tags", v.audit(self.state, self.empty, self.expected))

    def test_rejects_recreated_stack_and_changed_cover(self):
        after = copy.deepcopy(self.state)
        after["stacks"][0]["id"] = "recreated"
        after["stacks"][0]["primaryAssetId"] = "b"
        self.assertFalse(v.unchanged(self.state, after))
        self.assertTrue(v.audit(after, self.state, {}))

    def test_rejects_old_seed_remaining(self):
        extra = dict(self.state["assets"][0], id="seed", checksum="old")
        self.state["assets"].append(extra)
        self.assertTrue(v.audit(self.state, self.empty, self.expected))

    def test_fresh_fixtures_preserve_duplicate_and_json_titles(self):
        source = Path(__file__).resolve().parents[1] / "internal/e2e/client/DATA/fromGooglePhotos"
        with tempfile.TemporaryDirectory() as tmp:
            roots, manifest = v.make_fixtures(source, Path(tmp), "test-run")
            self.assertEqual([len(manifest[x]) for x in ("pairs", "before", "takeout")], [16, 1, 3])
            seed = next(iter(manifest["before"]))
            self.assertIn(seed, manifest["takeout"])
            for root in roots.values():
                for p in root.rglob("*.json"):
                    self.assertTrue(v.json.loads(p.read_text())["title"].startswith("koda3_test-run_"))
                for p in root.rglob("*.jpg"):
                    self.assertTrue(p.read_bytes().startswith(b"\xff\xd8\xff\xfe"))

    def test_server_logs_use_run_window_and_preserve_cli_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = v.Validation(Path(tmp), "secret-test-key", Path(tmp) / "run")
            seen = []
            def fake_run(command, **kwargs):
                seen.append(command)
                self.assertNotIn("secret-test-key", " ".join(command))
                if command[0] == "scp":
                    Path(command[-1]).write_text("2026-10-09T02:00:00Z metadata read failed\n")
                return v.subprocess.CompletedProcess(command, 0)
            with patch.object(v.subprocess, "run", side_effect=fake_run):
                task.collect_server_logs()
            self.assertEqual(len(seen), 2)
            self.assertIn(task.started_at, seen[0][-1])
            self.assertIn("sudo docker logs", seen[0][-1])
            self.assertEqual(v.json.loads((task.logs / "server-log-export.json").read_text())["lines"], 1)

    def test_failed_server_log_export_does_not_download_stale_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            task = v.Validation(Path(tmp), "key", Path(tmp) / "run")
            with patch.object(v.subprocess, "run", return_value=v.subprocess.CompletedProcess([], 1)) as run:
                with self.assertRaises(RuntimeError):
                    task.collect_server_logs()
            self.assertEqual(run.call_count, 1)

    def test_main_keeps_redacted_client_bundle_when_server_export_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            def execute(task):
                task.save("client-evidence", {"test": "secret-value"})
                return {"result": "PASS"}
            with patch.object(v, "__file__", str(Path(tmp) / "koda-validate.py")), \
                 patch.object(v.sys, "argv", ["script", "--storage-template-enabled", "--collect-server-logs"]), \
                 patch.object(v.sys, "platform", "linux"), \
                 patch.dict(v.os.environ, {"KODA_TEST_API_KEY": "secret-value"}), \
                 patch.object(v.Validation, "execute", execute), \
                 patch.object(v.Validation, "collect_server_logs", side_effect=RuntimeError("SSH failed")):
                self.assertEqual(v.main(), 1)
            archive = next(Path(tmp).rglob("*.zip"))
            with v.zipfile.ZipFile(archive) as z:
                result = v.json.loads(z.read("evidence/RESULT.json"))
                self.assertEqual(result["result"], "INCOMPLETE")
                self.assertEqual(result["testResult"], "PASS")
                self.assertNotIn(b"secret-value", z.read("evidence/client-evidence.json"))


if __name__ == "__main__":
    unittest.main()
