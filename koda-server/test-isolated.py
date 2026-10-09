#!/usr/bin/env python3
"""Validate the patch in a disposable loopback-only Immich, never production."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile

PACKAGE = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:2284'
SECRETS = []

def scrub(text):
    for value in SECRETS:
        text = text.replace(value, '[REDACTED]')
    return text

def api(path, payload=None, token=None, method=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(URL + '/api' + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
            return json.loads(data) if data else None
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'{path}: HTTP {error.code}: ' + scrub(error.read().decode())) from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds', type=int, default=3, choices=range(1,6))
    parser.add_argument('--sudo', action='store_true', help='Run Docker through sudo; keep evidence owned by your login user')
    args = parser.parse_args()
    if not (PACKAGE / 'immich-go-koda').is_file():
        raise SystemExit('Missing the Linux test importer in this package.')
    os.umask(0o077)
    token = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    project = 'koda-fix-test-' + token.lower()
    run = PACKAGE / 'test-results' / token
    run.mkdir(parents=True)
    docker = ['sudo', 'docker'] if args.sudo else ['docker']
    compose = docker + ['compose', '-p', project, '-f', str(PACKAGE / 'compose.test.yml')]
    result = {'result': 'FAIL', 'mode': 'isolated', 'productionModified': False, 'roundsRequested': args.rounds, 'rounds': []}
    subprocess.run(docker + ['info'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    # Port ownership is established by successfully starting our own uniquely
    # named Compose project before any signup, configuration, or test writes.
    started = False
    try:
        print('Building the candidate and starting a separate test server on localhost:2284...', flush=True)
        subprocess.run(compose + ['up', '-d', '--build', '--wait', '--wait-timeout', '180'], check=True)
        started = True
        container_id = subprocess.check_output(compose + ['ps', '-q', 'server'], text=True).strip()
        inspect = json.loads(subprocess.check_output(docker + ['inspect', container_id], text=True))[0]
        if inspect['Config']['Labels'].get('com.docker.compose.project') != project:
            raise RuntimeError('Unexpected test container identity')
        if inspect['Config']['Labels'].get('com.mykodahome.koda.metadata-fix') != '1':
            raise RuntimeError('Test server does not contain the candidate patch')
        for mount in inspect.get('Mounts', []):
            if mount.get('Type') == 'bind':
                raise RuntimeError('The isolated server must not have host bind mounts')
        version = api('/server/version')
        if [version.get(x) for x in ['major', 'minor', 'patch']] != [3, 2, 4]:
            raise RuntimeError('Unexpected server version')
        password = secrets.token_urlsafe(32)
        SECRETS.append(password)
        email = 'admin@koda-isolated.example'
        api('/auth/admin-sign-up', {'email': email, 'password': password, 'name': 'Koda isolated admin'})
        admin = api('/auth/login', {'email': email, 'password': password})['accessToken']
        SECRETS.append(admin)
        config = api('/system-config', token=admin)
        config['storageTemplate']['enabled'] = True
        config['storageTemplate']['template'] = '{{y}}/{{y}}-{{MM}}-{{dd}}/{{filename}}'
        config['machineLearning']['enabled'] = False
        config['logging']['level'] = 'verbose'
        config['logging']['enabled'] = True
        api('/system-config', config, token=admin, method='PUT')
        verified = api('/system-config', token=admin)
        if verified['storageTemplate']['enabled'] is not True:
            raise RuntimeError('Storage Template was not enabled')
        regular = api('/admin/users', {'email': 'test@koda-isolated.example', 'password': password,
            'name': 'Koda isolated test', 'isAdmin': False, 'shouldChangePassword': False}, token=admin)
        login = api('/auth/login', {'email': regular['email'], 'password': password})['accessToken']
        SECRETS.append(login)
        key = api('/api-keys', {'name': 'isolated-regression', 'permissions': ['all']}, token=login)['secret']
        SECRETS.append(key)
        spec = importlib.util.spec_from_file_location('koda_validate', PACKAGE / 'koda-validate.py')
        validation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validation)
        # Only this disposable verifier overrides the production runner's fixed
        # URL and owner. It never accepts a production URL or production API key.
        validation.SERVER, validation.OWNER = URL, regular['id']
        for index in range(args.rounds):
            print(f'\nRound {index + 1}/{args.rounds}: uploads, repeats, replacement, refresh, original-byte checks', flush=True)
            round_dir = run / f'{token}-round-{index + 1}'
            checker = validation.Validation(PACKAGE, key, round_dir)
            outcome = checker.execute()
            checker.save('RESULT', outcome)
            result['rounds'].append(outcome)
            print(f'Round {index + 1}: PASS', flush=True)
        result['result'] = 'PASS'
        result['freshAssetsVerified'] = args.rounds * 18
    except Exception as error:
        result['reason'] = scrub(str(error))
        print('FAIL:', result['reason'], flush=True)
    finally:
        if started:
            logs = subprocess.run(compose + ['logs', '--no-color', '--timestamps', 'server'], capture_output=True, text=True)
            (run / 'immich-server.log').write_text(scrub(logs.stdout + logs.stderr))
        # Only remove containers from the unique test project. Retain its named
        # volumes for review; never touch the live Immich project or its data.
        subprocess.run(compose + ['down'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        result['testProject'] = project
        result['finishedAtUTC'] = datetime.now(timezone.utc).isoformat()
        (run / 'RESULT.json').write_text(json.dumps(result, indent=2))
        for path in run.rglob('*'):
            if path.is_file() and path.suffix in ['.json', '.jsonl', '.log', '.txt']:
                path.write_text(scrub(path.read_text()))
        bundle = PACKAGE / ('koda-server-fix-verification-' + token + '.zip')
        with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(run.rglob('*')):
                if path.is_file() and 'fixtures' not in path.parts:
                    archive.write(path, path.relative_to(run))
        print('\nResult:', result['result'], '\nEvidence:', bundle, flush=True)
        print('The live Immich server and its settings were not changed.', flush=True)
    return 0 if result['result'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
