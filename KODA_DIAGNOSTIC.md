# Koda diagnostic: storage template stays ON

Purpose: reproduce the remaining metadata failure and collect enough server
evidence to identify a correction. This is not a server fix or full migration.

The supplied historical server log has one XMP read failure during the first
edited-pair import. The read failed in the upload directory; the earlier asset
report has a timezone anomaly within milliseconds. This is a strong timing
correlation, but the warning contains a storage filename, not an asset ID, so
the identity and move sequence are not proven by that line. The replacement
import has no corresponding warning. Missing tags can therefore not all be
assigned to that one error.

In Immich v3.2.4, MetadataRepository.readTags catches read failures and returns
an empty object. Metadata extraction merges media and sidecar values and later
updates stored tags. The storage-template move and sidecar-write paths also
run in different queues. A trace is needed to distinguish stale paths from
overlapping writes or metadata snapshots. No speculative server modification
is included in this package.

## 1. Immich web settings

Sign in as the administrator. Keep Storage Template enabled and leave its
template unchanged. If it was disabled while following earlier instructions,
re-enable and save it. Do not start Storage Template Migration manually.

Open Administration > Settings > Logging. Record the current Level, leave
logging enabled, choose Verbose, and Save. This increases diagnostic detail;
it does not alter the import/storage behavior. Use the web setting rather than
editing Docker files. After this run finishes, restore the previous Level.

The exact v3.2.4 UI is implemented at:
https://github.com/immich-app/immich/blob/v3.2.4/web/src/routes/admin/system-settings/LoggingSettings.svelte

## 2. Mac preparation

Extract the verified diagnostic ZIP into `~/koda-storage-on-test`.
The package folder is `~/koda-storage-on-test/immich-go-koda`.

    cd ~/koda-storage-on-test/immich-go-koda
    chmod +x ./immich-go-koda
    ./immich-go-koda --version

Expected: `immich-go version 0.32.0-koda.3`.
If macOS blocks this unsigned binary, allow it in System Settings > Privacy &
Security > Open Anyway, then rerun the version command.

Keep `KODA_TEST_API_KEY` in this Mac terminal. If it is missing, copy the test
account API key and run:

    export KODA_TEST_API_KEY="$(pbpaste | tr -d '\r\n')"

Do not print or paste the key into chat. The script independently checks the
account ID and refuses an administrator or any other user.

## 3. One command

    python3 ./koda-validate.py --storage-template-enabled --collect-server-logs

The runner imports uniquely named, byte-distinct synthetic fixtures using the
candidate 3 importer. It checks fresh pairs, repeat stack identity/covers, and
replacement; if those pass, it checks metadata-refresh durability and original
downloaded bytes. It stops the test sequence on failure and retains evidence.
It does not repair tags, delete previous test sets, pause queues, change server
settings, or import personal Takeout files. The smaller seed created by this
run is intentionally removed by the importer in the replacement scenario.

At the end, it uses the existing Mac SSH shortcut `patel-homecloud` to export
only the matching time window of `immich_server` logs. Enter the HP account's
sudo password if prompted. It then copies that log back and packages client
and server evidence together. It records the UTC window, account, fixture
checksums, intermediate paths/times/tags, importer output, and final result.
The test key is redacted from the evidence before archiving. A plain server
log copy remains in `/home/nmp153/koda-diagnostic-<run>.log` on the HP.

Finder highlights one verification ZIP. Upload it even when the result is FAIL.
If log export fails, the client evidence still gets archived; do not repeat
imports just to obtain the missing log. The saved server-log-window.json has
the information needed to retrieve it separately.

Restore the previous logging Level after the ZIP is produced. Keep Storage
Template ON. A PASS means only this run passed; it cannot establish that an
intermittent server race is permanently fixed.

## Local checks and scope

The unchanged candidate 3 binary previously passed full Go tests, targeted race
tests, vet, and e2e compilation. The updated runner's tests cover the known
missing-tag and changed-stack failures, unique fixture relationships, SSH log
window construction, and preservation of client evidence after export failure.
No live server or macOS test has been executed from the development workspace.
