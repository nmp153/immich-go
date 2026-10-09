# Immich 3.2.4 Koda metadata-ordering candidate

This is a server-side candidate for the metadata races reproduced during the
Koda synthetic Google Photos imports. It keeps Storage Template enabled.
The accompanying immich-go client is 0.32.0-koda.4; this directory does not claim the server
patch is deployed or approved for the full migration.

## Source and behavior

`server.patch` applies to Immich v3.2.4, commit
`db355f79d910bbfc6378117ed10868493c97b922` at
<https://github.com/immich-app/immich>. It adds:

- Per-asset PostgreSQL transaction advisory locks shared by API and job workers.
- Coordination of tag assignment/removal, API metadata changes, sidecar
  discovery/writes/copying, metadata extraction, and storage-template moves.
- Fresh file-path reads after acquiring the storage-move lock.
- Propagation of sidecar-write and required-sidecar-read errors, so failed I/O
  cannot silently clear metadata protection or import an empty sidecar.
- Deferred motion-photo extraction after releasing the still-photo lock, avoiding
  nested acquisition of another asset.

There are no database migrations, no queue pausing, and no changes to storage
layout or the image/video originals. Locks use a separate pool, up to four
connections per API/job process; waiting for a metadata lock cannot consume the
query-pool connections needed by its holder. Different assets can progress in
parallel. Multi-asset locks are acquired in sorted order.

The patch is scoped to import metadata and related API operations. It does not
claim to fix every Immich issue, tag rename/delete synchronization, or storage
outages. Original Immich and these modifications are licensed under AGPL-3.0.

## Validation

Local checks: five concurrency regressions fail against the unpatched upstream
service methods and pass with the patch. All 2,286 original candidate tests passed; the added copy-path regression also passes;
TypeScript checking, linting of changed files, and the server build pass.

`negative-control.py` restores the original service methods temporarily, requires
all five targeted regressions to fail, and restores the candidate in `finally`.
The tests use an in-memory transactional lock backend locally. Setting
`KODA_TEST_DATABASE_URL` runs the same tests with independent PostgreSQL sessions.

The Koda server metadata regression workflow provisions PostgreSQL 14.19 and a
separate Immich stack on a disposable GitHub runner. It performs three rounds of
fresh uploads, repeated imports, smaller-copy replacement, metadata refresh, and
downloaded-original checksum verification. Each round must preserve prior assets,
stack IDs/covers, tags, and capture times. CI results must be reviewed separately;
this README is not an assertion that integration tests passed.

The first full integration run passed fresh edited pairs, their repeated import,
and the initial smaller-copy replacement. It then exposed a separate importer
bug: another import uploaded the removed smaller copy as `photo(1).jpg` and
changed the stack. Candidate 4 resolves that numbered copy through the group's
matching larger original only when that original's checksum already exists on
the server. It does not use an edited sibling or a shared title alone. The
regression fails with candidate 3's code and passes with candidate 4's code.

## Isolated verification package

`package.py IMMICH_CHECKOUT OUTPUT_DIRECTORY` assembles compiled JavaScript
changes, source patch, Dockerfile, fixtures, and the verifier. Supply a Linux
amd64 immich-go-koda binary built from the matching importer branch at version
0.32.0-koda.4. The Dockerfile extends the official v3.2.4 image and checks its
version before installing the seven changed runtime modules.

The top-level importer binary is for the HP's Linux amd64 environment.
`mac-verifier/immich-go-koda` is the matching macOS arm64 build, with its own
fixtures and verifier. The Mac verifier checks the existing Koda Import Test
account and requires an explicit `--storage-template-enabled` flag.

From the resulting package on a Linux Docker host:

```
python3 test-isolated.py --rounds 3
```

If Docker requires sudo, use `sudo -v` followed by
`python3 test-isolated.py --sudo --rounds 3`. Do not run the entire Python script
as root; the `--sudo` option keeps the evidence files owned by your login user.

This creates a uniquely named Compose project, its own PostgreSQL/Redis/media
volumes, and a loopback-only listener at 127.0.0.1:2284. It does not use the live
Immich project, its files, API keys, database, or settings. It creates synthetic
accounts and enables Storage Template only in this disposable instance. It
stops its own containers after testing, retains test volumes for inspection, and
writes a redacted evidence ZIP. It does not deploy to production.

Do not start the real Google Photos migration based solely on the package
existing or on an importer exit code of zero. Review integration results first,
then test the candidate on the HP/WD path before a small real Takeout sample.

## HP installation handoff

The package is not an automatic production installer. It must first pass the
isolated integration checks. The first command on the HP is:

```
python3 preflight.py
```

This reports the active Compose files, server image and health, storage mounts,
existing override files, and recovery-timer state. It does not print environment
variables or credentials, change configuration, or restart any container.

Use that output to choose an override filename that Docker Compose loads by
default. This matters because the existing storage-recovery service also runs
Compose: a temporary `-f` override alone could let recovery revert the image.
Do not replace the existing Compose file or alter its volume definitions.

The installation sequence after reviewing that layout is:

1. Create a fresh Immich database backup and verify its gzip integrity. Keep the
   original v3.2.4 image locally and record its immutable image ID.
2. Build `immich-server-koda:3.2.4-koda.1` with this package's Dockerfile.
3. Save the current Compose configuration files. Add an image-only server
   override, preserving any existing override. Compare the effective Compose
   configuration in memory: only the server image and its pull policy may change.
   Keep Storage Template enabled and the existing media/database mounts intact.
4. Briefly stop the storage-recovery timer, recreate only `immich-server` with
   `--no-deps`, check its health and patch label, and restore the timer's prior
   state. PostgreSQL, Redis, and machine learning do not need recreation.
5. Run the existing Mac verifier against **Koda Import Test** on the HP/WD path.
   This checks the fix on the storage that previously exposed the problem.

Rollback removes only the new image override (or restores the exact previous
override), recreates only the server from its recorded original image, checks
health, and restores the recovery timer. This patch has no database migrations;
rolling back the server code does not require restoring an older database or
deleting any photos. A database restore is a separate recovery action and must
not be bundled into ordinary code rollback.
