#!/usr/bin/env python3
"""Run the four race regressions against unpatched upstream service methods.

Restores patched files even on test failure; never writes outside the supplied
Immich checkout. A failed test suite is expected only for these four regressions.
"""
import json
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
base = 'db355f79d910bbfc6378117ed10868493c97b922'
paths = [
    'server/src/services/metadata.service.ts',
    'server/src/services/tag.service.ts',
    'server/src/services/storage-template.service.ts',
]
saved = {name: (root / name).read_bytes() for name in paths}
report = root / 'negative-control.json'
try:
    for name in paths:
        old = subprocess.check_output(['git', 'show', base + ':' + name], cwd=root)
        (root / name).write_bytes(old)
    result = subprocess.run([
        'pnpm', '--filter', 'immich', 'exec', 'vitest', '--config', 'test/vitest.config.mjs',
        'run', 'src/services/metadata-ordering.spec.ts',
        '-t', 'does not let|keeps tag relation|cannot clear|moves a sidecar',
        '--reporter=json', '--outputFile=' + str(report),
    ], cwd=root)
finally:
    for name, data in saved.items():
        (root / name).write_bytes(data)
if not report.exists():
    raise SystemExit('FAIL: the negative control did not produce a report')
summary = json.loads(report.read_text())
failed = [test['fullName'] for suite in summary['testResults']
          for test in suite['assertionResults'] if test['status'] == 'failed']
if result.returncode == 0 or len(failed) != 4:
    raise SystemExit(f'FAIL: expected four reproduced races, found {len(failed)}')
print('PASS: all four race regressions fail against the unpatched upstream methods:')
for name in failed:
    print(' -', name)
