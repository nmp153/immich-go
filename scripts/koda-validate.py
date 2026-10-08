#!/usr/bin/env python3
"""One bounded synthetic check for Koda candidate 3; never imports personal files.

Uses only KODA_TEST_API_KEY and refuses any account except the established test
user. It creates fresh fixture copies, performs real imports (including removal
of its own smaller replacement seed), and produces a redacted evidence ZIP.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import uuid
import zipfile

SERVER = "https://photos.mykodahome.com"
OWNER = "f2076ecf-6c00-4606-aa5d-1c91dedd4294"
CAPTURE = "2023-11-14T22:13:20.000Z"
LOCAL = "2023-11-14T17:13:20.000Z"


def checksum(data):
    return base64.b64encode(hashlib.sha1(data).digest()).decode()


def signature(asset):
    exif = asset.get("exifInfo") or {}
    return {
        **{k: asset.get(k) for k in ("id", "ownerId", "checksum", "originalPath",
                                     "fileCreatedAt", "localDateTime", "isTrashed", "isOffline")},
        "size": exif.get("fileSizeInByte"), "timezone": exif.get("timeZone"),
        "tags": sorted(t["value"] for t in asset.get("tags", [])),
        "stack": asset.get("stack"),
    }


def stack_signature(stack):
    return (stack["primaryAssetId"], sorted(a["id"] for a in stack["assets"]))


def audit(state, baseline, expected):
    """Check full asset details and /stacks, never assume search includes stacks."""
    problems = []
    assets = {a["id"]: a for a in state["assets"]}
    old = {a["id"]: a for a in baseline["assets"]}
    if len(assets) != len(state["assets"]) or len(assets) != len(old) + len(expected):
        problems.append("asset count / unique IDs")
    for asset_id, previous in old.items():
        if asset_id not in assets or signature(assets[asset_id]) != signature(previous):
            problems.append("previous asset changed: " + asset_id)
    current_stacks = {s["id"]: s for s in state["stacks"]}
    for previous in baseline["stacks"]:
        current = current_stacks.get(previous["id"])
        if current is None or stack_signature(current) != stack_signature(previous):
            problems.append("previous stack / cover changed: " + previous["id"])
    fresh = [a for a in state["assets"] if a["id"] not in old]
    by_hash = {a["checksum"]: a for a in fresh}
    if len(by_hash) != len(fresh) or set(by_hash) != set(expected):
        problems.append("fresh checksums (unexpected, missing, duplicate, or old smaller copy)")
    groups = {}
    for digest, want in expected.items():
        a = by_hash.get(digest)
        if not a:
            continue
        exif = a.get("exifInfo") or {}
        checks = {
            "owner": a.get("ownerId") == OWNER,
            "size": exif.get("fileSizeInByte") == want["size"],
            "capture time": a.get("fileCreatedAt") == CAPTURE,
            "local time": a.get("localDateTime") == LOCAL,
            "timezone": exif.get("timeZone") == "UTC-5",
            "tags": set(want["tags"]).issubset({t["value"] for t in a.get("tags", [])}),
            "availability": a.get("isTrashed") is False and a.get("isOffline") is False,
        }
        for name, passed in checks.items():
            if not passed:
                problems.append(want["name"] + ": " + name)
        if want.get("group"):
            groups.setdefault(want["group"], set()).add(a["id"])
        elif a.get("stack"):
            problems.append(want["name"] + ": unexpected stack")
    if len(current_stacks) != len(baseline["stacks"]) + len(groups):
        problems.append("stack count")
    for group, members in groups.items():
        matches = [s for s in state["stacks"] if {a["id"] for a in s["assets"]} == members]
        if len(members) != 2 or len(matches) != 1:
            problems.append(group + ": exact two-member stack")
            continue
        stack = matches[0]
        if stack["primaryAssetId"] not in members or len(stack["assets"]) != 2:
            problems.append(group + ": stack cover / duplicate member")
        for member in members:
            detail = assets[member].get("stack") or {}
            if (detail.get("id"), detail.get("primaryAssetId"), detail.get("assetCount")) != (stack["id"], stack["primaryAssetId"], 2):
                problems.append(group + ": asset and stack endpoints disagree")
    return problems


def unchanged(before, after):
    a = {x["id"]: signature(x) for x in before["assets"]}
    b = {x["id"]: signature(x) for x in after["assets"]}
    sa = {s["id"]: stack_signature(s) for s in before["stacks"]}
    sb = {s["id"]: stack_signature(s) for s in after["stacks"]}
    return a == b and sa == sb


def make_fixtures(source, destination, token):
    prefix = "koda3_" + token + "_"
    roots = {}
    manifest = {}
    for label, relative in (("pairs", "edited-pair"), ("before", "replaced-copy/before"),
                            ("takeout", "replaced-copy/takeout")):
        root = destination / ("koda3-" + token + "-" + label)
        roots[label] = root
        records = {}
        for path in sorted((source / relative).rglob("*")):
            if not path.is_file():
                continue
            target = root / path.relative_to(source / relative).parent / (prefix + path.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix.lower() == ".jpg":
                data = path.read_bytes()
                if not data.startswith(b"\xff\xd8"):
                    raise RuntimeError("Unexpected fixture format: " + path.name)
                # A valid JPEG comment changes bytes without changing pixels. The
                # same run marker preserves the byte-identical seed/photo(1) pair.
                comment = ("koda validation " + token).encode()
                data = data[:2] + b"\xff\xfe" + struct.pack(">H", len(comment) + 2) + comment + data[2:]
                target.write_bytes(data)
                name = path.name
                group = name.replace("-edited", "")[:-4] if label == "pairs" else None
                records[checksum(data)] = {"name": prefix + name, "size": len(data),
                                            "tags": [root.name], "group": group}
            elif path.suffix == ".json":
                obj = json.loads(path.read_text())
                obj["title"] = prefix + obj["title"]
                target.write_text(json.dumps(obj))
            else:
                raise RuntimeError("Unexpected fixture file: " + path.name)
        manifest[label] = records
    if [len(manifest[x]) for x in ("pairs", "before", "takeout")] != [16, 1, 3]:
        raise RuntimeError("Fixture counts differ from the reviewed package")
    seed_hash = next(iter(manifest["before"]))
    if seed_hash not in manifest["takeout"]:
        raise RuntimeError("Replacement duplicate no longer matches the smaller seed")
    return roots, manifest


class Validation:
    def __init__(self, package, key, run):
        self.package, self.key, self.run = package, key, run
        self.logs = run / "evidence"
        self.logs.mkdir(parents=True)

    def save(self, name, obj):
        text = json.dumps(obj, indent=2).replace(self.key, "[REDACTED]")
        (self.logs / (name + ".json")).write_text(text)

    def api(self, path, payload=None, raw=False):
        cmd = ["curl", "--http1.1", "--fail", "--silent", "--show-error", "--max-time", "30",
               "--header", "x-api-key: " + self.key]
        if payload is not None:
            cmd += ["--header", "Content-Type: application/json", "--data", json.dumps(payload)]
        result = subprocess.run(cmd + [SERVER + "/api" + path], capture_output=True)
        if result.returncode:
            detail = result.stderr.decode(errors="replace").replace(self.key, "[REDACTED]")
            raise RuntimeError("API request failed " + path + ": " + detail)
        if raw:
            return result.stdout
        return json.loads(result.stdout) if result.stdout.strip() else None

    def snapshot(self):
        items = []
        for page in range(1, 21):
            result = self.api("/search/metadata", {"page": page, "size": 1000, "withExif": True,
                                                  "withStacked": True, "withDeleted": True})["assets"]
            items.extend(result["items"])
            if not result.get("nextPage"):
                if result.get("nextCursor"):
                    raise RuntimeError("Unexpected cursor pagination; stopping to avoid incomplete verification")
                break
        else:
            raise RuntimeError("Unexpectedly large test account")
        if len(items) > 500:
            raise RuntimeError("Test account contains more than 500 assets; stopping")
        with ThreadPoolExecutor(max_workers=4) as pool:
            details = list(pool.map(lambda a: self.api("/assets/" + a["id"]), items))
        return {"assets": details, "stacks": self.api("/stacks")}

    def settle(self, name, baseline, expected, repeat=None, refreshed=None):
        deadline, last, stable_since = time.monotonic() + 180, None, None
        next_update = time.monotonic() + 15
        while True:
            state = self.snapshot()
            self.save(name, state)
            problems = audit(state, baseline, expected)
            if repeat is not None and not unchanged(repeat, state):
                problems.append("repeat / refresh changed an asset, stack, or cover")
            if refreshed:
                current = {a["id"]: a for a in state["assets"]}
                if any(current.get(i, {}).get("updatedAt") == stamp for i, stamp in refreshed.items()):
                    problems.append("waiting for requested metadata refresh to update every fresh asset")
            if not problems and last is not None and unchanged(last, state):
                if stable_since is None:
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since >= 8:
                    print("PASS:", name, flush=True)
                    return state
            else:
                stable_since = None
            if time.monotonic() >= deadline:
                self.save(name + "-failures", problems)
                raise RuntimeError(name + " did not pass within 3 minutes: " + "; ".join(problems[:12]))
            if time.monotonic() >= next_update:
                print("Waiting:", name, "—", "; ".join(problems[:3]) or "checking stability", flush=True)
                next_update = time.monotonic() + 15
            last = state
            time.sleep(3)

    def import_fixture(self, name, root):
        print("Import:", name, flush=True)
        cmd = [str(self.package / "immich-go-koda"), "upload", "from-google-photos",
               "--server=" + SERVER, "--api-key=" + self.key, "--admin-api-key=",
               "--pause-immich-jobs=false", "--dry-run=false", "--concurrent-tasks=4",
               "--client-timeout=2m", "--on-errors=stop", "--no-ui", "--log-level=debug",
               "--time-zone=America/New_York", "--manage-burst=Stack",
               "--log-file=" + str(self.logs / (name + ".log")), str(root)]
        env = dict(os.environ, TZ="America/New_York")
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=300, env=env)
        except subprocess.TimeoutExpired:
            raise RuntimeError(name + " exceeded 5 minutes; stopped the importer (server jobs may still finish)") from None
        output = (result.stdout + result.stderr).decode(errors="replace").replace(self.key, "[REDACTED]")
        (self.logs / (name + "-console.txt")).write_text(output)
        self.save(name + "-exit", {"exitCode": result.returncode})
        if result.returncode:
            raise RuntimeError(name + " exited with code " + str(result.returncode) + "; see the evidence bundle")

    def execute(self):
        who = self.api("/users/me")
        if who.get("id") != OWNER or who.get("isAdmin") is not False:
            raise RuntimeError("Wrong account. The key must belong to Koda Import Test, a non-admin user")
        self.save("account", {"id": who["id"], "name": who.get("name"), "isAdmin": who["isAdmin"]})
        version = subprocess.run([str(self.package / "immich-go-koda"), "--version"], capture_output=True, text=True)
        if version.returncode or version.stdout.strip() != "immich-go version 0.32.0-koda.3":
            raise RuntimeError("Expected candidate 3. Run ./immich-go-koda --version and allow it in macOS if prompted")
        roots, manifest = make_fixtures(self.package / "synthetic-fixtures", self.run / "fixtures", self.run.name)
        self.save("fixture-manifest", manifest)
        self.save("build", {"version": version.stdout.strip(), "sha256": hashlib.sha256((self.package / "immich-go-koda").read_bytes()).hexdigest()})
        baseline = self.snapshot()
        if any(a.get("ownerId") != OWNER for a in baseline["assets"]):
            raise RuntimeError("Baseline includes an unexpected asset owner")
        self.save("00-baseline", baseline)
        expected = dict(manifest["pairs"])
        if set(expected) & {a["checksum"] for a in baseline["assets"]}:
            raise RuntimeError("Fresh fixtures already exist; unexpected checksum collision")
        self.import_fixture("01-pairs", roots["pairs"])
        pairs = self.settle("01-pairs-state", baseline, expected)
        self.import_fixture("02-pairs-repeat", roots["pairs"])
        self.settle("02-pairs-repeat-state", baseline, expected, repeat=pairs)
        self.import_fixture("03-smaller-seed", roots["before"])
        expected.update(manifest["before"])
        seed = self.settle("03-smaller-seed-state", baseline, expected)
        seed_hash = next(iter(manifest["before"]))
        seed_id = next(a["id"] for a in seed["assets"] if a["checksum"] == seed_hash)
        self.import_fixture("04-replacement", roots["takeout"])
        del expected[seed_hash]
        for digest, original in manifest["takeout"].items():
            if digest == seed_hash:
                continue
            record = dict(original, group="replacement")
            if record["name"].endswith("photo.jpg"):
                record["tags"] = record["tags"] + manifest["before"][seed_hash]["tags"]
            expected[digest] = record
        replaced = self.settle("04-replacement-state", baseline, expected)
        if seed_id in {a["id"] for a in replaced["assets"]}:
            raise RuntimeError("Old smaller seed ID still exists")
        self.import_fixture("05-replacement-repeat", roots["takeout"])
        repeated = self.settle("05-replacement-repeat-state", baseline, expected, repeat=replaced)
        baseline_ids = {a["id"] for a in baseline["assets"]}
        fresh = [a for a in repeated["assets"] if a["id"] not in baseline_ids]
        print("Checking metadata survives a fresh read from the stored files...", flush=True)
        self.api("/assets/jobs", {"assetIds": [a["id"] for a in fresh], "name": "refresh-metadata"})
        self.settle("06-after-refresh", baseline, expected, repeat=repeated,
                    refreshed={a["id"]: a.get("updatedAt") for a in fresh})
        print("Verifying downloaded original bytes for all 18 fresh images...", flush=True)
        downloaded = []
        for asset in fresh:
            data = self.api("/assets/" + asset["id"] + "/original", raw=True)
            if checksum(data) != asset["checksum"]:
                raise RuntimeError("Downloaded original checksum mismatch: " + asset["id"])
            downloaded.append({"id": asset["id"], "checksum": checksum(data), "bytes": len(data)})
        self.save("07-original-download-checks", downloaded)
        return {"result": "PASS", "freshAssets": len(fresh), "newStacks": 9,
                "baselineAssetsPreserved": len(baseline["assets"]),
                "checks": ["fresh uploads", "repeat IDs and covers", "smaller-copy replacement",
                           "timezone and tags", "metadata refresh durability", "downloaded original bytes"],
                "next": "Review evidence, then a small real Takeout sample; full migration has not run"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-template-disabled", action="store_true",
                        help="Acknowledge temporarily disabling Storage Template in Immich settings")
    args = parser.parse_args()
    if not args.storage_template_disabled:
        parser.error("First turn off Enable Storage Template in Administration > Settings > Storage Template and save; then add --storage-template-disabled")
    key = os.environ.get("KODA_TEST_API_KEY", "").strip()
    if not key or "\n" in key or "\r" in key:
        parser.error("KODA_TEST_API_KEY is missing or malformed")
    package = Path(__file__).resolve().parent
    run = package / "validation-runs" / (time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
    task = Validation(package, key, run)
    result = {"result": "FAIL"}
    try:
        result = task.execute()
    except (Exception, KeyboardInterrupt) as error:
        # Do not print subprocess command objects: they may include the API key.
        result["reason"] = str(error).replace(key, "[REDACTED]") or "Interrupted"
        print("STOP:", result["reason"], flush=True)
    finally:
        task.save("RESULT", result)
        for path in task.logs.iterdir():
            if path.is_file():
                path.write_text(path.read_text(errors="replace").replace(key, "[REDACTED]"))
        archive = run.with_name("koda3-verification-" + run.name + ".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for path in sorted(task.logs.iterdir()):
                z.write(path, "evidence/" + path.name)
        print("\nResult:", result["result"], "\nUpload this ZIP here:\n" + str(archive), flush=True)
        if sys.platform == "darwin":
            subprocess.run(["open", "-R", str(archive)], check=False)
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
