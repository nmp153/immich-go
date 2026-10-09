#!/usr/bin/env python3
"""Assemble the version-pinned server overlay and isolated verifier."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
server = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
out.mkdir(parents=True, exist_ok=True)
files = [
    'repositories/database.repository', 'repositories/metadata.repository',
    'services/asset.service', 'services/metadata.service',
    'services/storage-template.service', 'services/tag.service',
    'utils/asset-metadata-lock',
]
for name in files:
    for suffix in ['.js', '.js.map']:
        src = server / 'server/dist' / (name + suffix)
        dest = out / 'overlay' / (name + suffix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
for name in ['Dockerfile', 'compose.test.yml', 'test-isolated.py', 'server.patch', 'negative-control.py']:
    shutil.copy2(root / 'koda-server' / name, out / name)
shutil.copy2(root / 'scripts/koda-validate.py', out / 'koda-validate.py')
shutil.copytree(root / 'internal/e2e/client/DATA/fromGooglePhotos/edited-pair', out / 'synthetic-fixtures/edited-pair', dirs_exist_ok=True)
shutil.copytree(root / 'internal/e2e/client/DATA/fromGooglePhotos/replaced-copy', out / 'synthetic-fixtures/replaced-copy', dirs_exist_ok=True)
manifest = {
    'patchVersion': '3.2.4-koda.1',
    'upstreamVersion': '3.2.4',
    'upstreamCommit': 'db355f79d910bbfc6378117ed10868493c97b922',
    'importerVersion': '0.32.0-koda.3',
    'storageTemplateRequired': True,
    'schemaChanges': False,
    'sourcePatchSHA256': hashlib.sha256((out / 'server.patch').read_bytes()).hexdigest(),
}
(out / 'BUILD.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(out)
