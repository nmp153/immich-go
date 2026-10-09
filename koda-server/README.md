# Immich 3.2.4 Koda metadata-ordering candidate

This is a server-side candidate for the metadata races reproduced during the
Koda synthetic Google Photos imports. It keeps Storage Template enabled. The
immich-go client remains 0.32.0-koda.3; this directory does not claim the server
patch is deployed or approved for the full migration.

## Source and behavior

`server.patch` applies to Immich v3.2.4, commit
`db355f79d910bbfc6378117ed10868493c97b922` at
<https://github.com/immich-app/immich>. It adds:

- Per-asset PostgreSQL transaction advisory locks shared by API and job workers.
- Coordination of tag assignment/removal, API metadata changes, sidecar
  discovery/writes, metadata extraction, and storage-template moves.
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

Local checks: four concurrency regressions fail against the unpatched upstream
service methods and pass with the patch. All 2,286 server unit tests pass;
TypeScript checking, linting of changed files, and the server build pass.

`negative-control.py` restores the original service methods temporarily, requires
all four targeted regressions to fail, and restores the candidate in `finally`.
The tests use an in-memory transactional lock backend locally. Setting
`KODA_TEST_DATABASE_URL` runs the same tests with independent PostgreSQL sessions.

The Koda server metadata regression workflow provisions PostgreSQL 14.19 and a
separate Immich stack on a disposable GitHub runner. It performs three rounds of
fresh uploads, repeated imports, smaller-copy replacement, metadata refresh, and
downloaded-original checksum verification. Each round must preserve prior assets,
stack IDs/covers, tags, and capture times. CI results must be reviewed separately;
this README is not an assertion that integration tests passed.

## Isolated verification package

`package.py IMMICH_CHECKOUT OUTPUT_DIRECTORY` assembles compiled JavaScript
changes, source patch, Dockerfile, fixtures, and the verifier. Supply a Linux
amd64 immich-go-koda binary built from the matching importer branch at version
0.32.0-koda.3. The Dockerfile extends the official v3.2.4 image and checks its
version before installing the seven changed runtime modules.

From the resulting package on a Linux Docker host:

```
python3 test-isolated.py --rounds 3
```

This creates a uniquely named Compose project, its own PostgreSQL/Redis/media
volumes, and a loopback-only listener at 127.0.0.1:2284. It does not use the live
Immich project, its files, API keys, database, or settings. It creates synthetic
accounts and enables Storage Template only in this disposable instance. It
stops its own containers after testing, retains test volumes for inspection, and
writes a redacted evidence ZIP. It does not deploy to production.

Do not start the real Google Photos migration based solely on the package
existing or on an importer exit code of zero. Review integration results first,
then test the candidate on the HP/WD path before a small real Takeout sample.
