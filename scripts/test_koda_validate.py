import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
