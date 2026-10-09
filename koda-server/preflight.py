#!/usr/bin/env python3
"""Read the HP installation layout without exposing its environment or changing it."""
import json
from pathlib import Path
import subprocess


def run(args, *, cwd=None):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit('STOP: Could not complete ' + ' '.join(args[:4]))
    return result.stdout


def main():
    subprocess.run(['sudo', '-v'], check=True)
    container = json.loads(run(['sudo', 'docker', 'inspect', 'immich_server']))[0]
    labels = container['Config'].get('Labels') or {}
    directory = labels.get('com.docker.compose.project.working_dir')
    if not directory or not Path(directory).is_dir():
        raise SystemExit('STOP: Cannot identify the live Compose directory.')
    configuration = json.loads(run(['sudo', 'docker', 'compose', 'config', '--format', 'json'], cwd=directory))
    service = configuration.get('services', {}).get('immich-server')
    if not service:
        raise SystemExit('STOP: The default Compose configuration has no immich-server service.')
    timer = subprocess.run(['systemctl', 'is-active', 'immich-storage-recovery.timer'], capture_output=True, text=True)
    report = {
        'mode': 'read-only',
        'composeDirectory': directory,
        'composeFiles': labels.get('com.docker.compose.project.config_files'),
        'defaultComposeProject': configuration.get('name'),
        'runningComposeProject': labels.get('com.docker.compose.project'),
        'configuredServerImage': service.get('image'),
        'runningServerImage': container['Config']['Image'],
        'runningImageID': container['Image'],
        'serverStatus': container['State']['Status'],
        'serverHealth': container['State'].get('Health', {}).get('Status'),
        'serverVersion': run(['sudo', 'docker', 'exec', 'immich_server', 'node', '-p',
            "require('/usr/src/app/server/package.json').version"]).strip(),
        'recoveryTimer': timer.stdout.strip(),
        'existingOverrideFiles': [name for name in (
            'compose.override.yaml', 'compose.override.yml',
            'docker-compose.override.yaml', 'docker-compose.override.yml'
        ) if (Path(directory) / name).exists()],
        'serverMounts': [{key: mount.get(key) for key in ('Type', 'Source', 'Destination', 'RW')}
            for mount in container.get('Mounts', [])],
    }
    print(json.dumps(report, indent=2))
    print('\nPreflight complete. No container, file, setting, or database was changed.')


if __name__ == '__main__':
    main()
