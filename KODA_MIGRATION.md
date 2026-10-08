# Koda migration build — candidate 3

This is a temporary migration candidate, not an official immich-go release.
Do not use it for a full library until synthetic and small real-data imports
have passed against the target Immich version.

## Provenance

- Base: v0.32.0, f7d19fce34acd4884ea2c02fc3025706a060afdf.
- Incorporated upstream PR https://github.com/simulot/immich-go/pull/1423
  at 4b1ec8b7fd5b8c2705fa41413fbf3987e5563fdb, preserving its authorship.
- Relevant unresolved report: https://github.com/simulot/immich-go/issues/1443.

## Changes

The upstream fix distinguishes edited/original group siblings from server
variants, resolves replaced IDs, removes empty/duplicate stack IDs, and assigns
server IDs to AlreadyProcessed assets. It includes edited-pair and replacement
fixtures and integration tests.

Additional candidate changes:

- Candidate 3: Google Photos/group imports read existing stack membership and
  preserve an exact stack, its ID, and its current cover. They create a stack
  only when membership differs. The explicit stack command still creates stacks.
  API keys now also need `stack.read` (the test account's all-permissions key
  already includes this). A failed read stops the operation instead of blindly
  recreating a stack. The 90-second bound includes the reads and any POST.
- Candidate 3: per-asset tag responses must account for every requested ID;
  rejected/missing responses are failures. An existing duplicate relation is
  accepted. Empty tag-creation responses are rejected without panicking.
- Candidate 3: early and final collection-save errors reach finalization and
  the CLI exit status. UI/non-UI runners preserve errors when the context has
  not been canceled; non-UI preparation failures are retained as well.
- Candidate 3: `koda-validate.py` automates fresh synthetic imports, repeats,
  replacement, metadata-refresh durability, and downloaded-original checksums.
  It checks full asset details and the stacks endpoint separately. Search
  results alone do not reliably include stack/tag fields in Immich v3.2.4.
- Candidate 2: finishing skips job-resume requests when
  --pause-immich-jobs=false. Candidate 1 inherited an unconditional resume
  request that a regular test account would reject. Regression coverage
  reproduces that rejection, checks that disabled job management sends no
  requests, and preserves resume after cancellation when management is enabled.
- CreateStack uses a 90-second context deadline, independent of a longer
  --client-timeout. Earlier parent/client deadlines still apply. The context
  reaches the actual HTTP request and response-body read. This bounds waiting;
  it does not establish or fix the server-side cause of issue #1443.
- Stack ID validation preserves cover order and does not mutate caller slices.
- HTTP call errors expose their underlying errors through Unwrap.
- Group processing retains earlier asset errors instead of overwriting them.
- Stack failures return to --on-errors handling and appear in the event report
  as server errors. Stacked events are recorded only after API success.
  The asset-only UI headline remains insufficient for checking metadata errors.
- Deterministic unit tests cover both edited-pair orders and size relationships,
  populated-index reruns, AlreadyProcessed IDs, and stack success/failure reporting.
- Real HTTP tests exercise hung response headers, partial success/error bodies,
  cancellation, duplicate IDs, and a successful request after timeout.
- The edited-pair integration test now re-imports its fixture and verifies stable
  asset IDs/checksums and two-item stacks within a bounded test context.

No automatic retry is added for a timed-out stack POST: the server might have
committed the operation even if the response was lost. Inspect before retrying.
Album per-item response validation is not comprehensively changed by this patch.
Event counts such as `tagged` represent queued work, not proof that metadata
survived asynchronous server processing. Validate the stored results as well.
This build does not repair a library already damaged by an earlier import.

## Live evidence from candidate 2 (Immich v3.2.4)

- Sixteen edited/original images uploaded with the expected checksums and eight
  correct two-image stacks. One image needed metadata refresh for its timezone;
  three others needed manual tag repair. Those repairs are not a clean pass.
- Repeating the import uploaded zero images and preserved image IDs/checksums,
  but recreated all eight stacks and changed six covers. Candidate 3 addresses
  this importer behavior.
- The smaller-copy replacement produced the expected two surviving images and
  removed the smaller seed, while preserving the earlier sixteen assets and
  eight stacks. One new edited image again lacked its Takeout tag.
- Candidate 3 has NOT yet run against the live server. No full Takeout migration
  has run with this candidate.

## Temporary storage-template workaround

Immich maintainers identified a race between storage-template moves and EXIF
extraction in issue https://github.com/immich-app/immich/issues/27267.
In the discussion, disabling the storage template prevented reproduction in
eleven attempts. Keep background queues running; do not pause them for this
workflow. Our observations are consistent with that report, but server logs
have not established it as the exact cause on this installation.

For the fresh test, log into Immich as the administrator and open
Administration > Settings > Storage Template. Turn off Enable Storage Template
(sometimes labeled Storage Template Engine), then save. This is a server-wide
setting. New uploads stay under `/data/upload`; the existing dated library is
not moved back. In the documented Koda bind mounts, upload and library are both
on the WD volume. Leave the template text intact.

Keep it disabled through validation and any approved import. After import
processing settles, re-enable it and run Storage Template Migration as a
separate operation, then recheck metadata and integrity. Re-enabling and
migrating are still future steps, not actions taken by the validation script.

Sources:
- https://github.com/immich-app/immich/issues/27267#issuecomment-4162571638
- https://github.com/immich-app/immich/issues/27267#issuecomment-4162463028
- https://docs.immich.app/administration/storage-template/

## One automated fresh test on the Mac

The Apple Silicon ZIP includes the binary, reviewed synthetic source fixtures,
and `koda-validate.py` at the package root. It requires Python 3, curl, and the
existing `KODA_TEST_API_KEY` environment variable. It refuses the main/admin
account and accepts only the established Koda Import Test user.

After disabling the storage template and verifying/extracting the ZIP:

    cd ~/koda-import-test-v3/immich-go-koda
    chmod +x ./immich-go-koda
    ./immich-go-koda --version
    python3 ./koda-validate.py --storage-template-disabled

Expected version: `immich-go version 0.32.0-koda.3`. If macOS blocks the unsigned
binary, allow this specific binary in System Settings > Privacy & Security >
Open Anyway, then rerun the version command before starting validation.

The script generates a unique set of small synthetic images, retains the
existing account baseline, imports sixteen edited/original images twice, then
imports a smaller seed and replaces it with a larger original plus an edit.
It repeats replacement, refreshes metadata for only its eighteen new images,
and downloads those originals to verify actual bytes. The importer removes
only the fresh smaller seed as part of the replacement scenario. There is no
cleanup of previous tests, bulk deletion, manual tag repair, server setting
change, admin job management, or personal Takeout access in the script.

It checks baseline asset IDs/checksums/paths/tags/times and stacks/covers,
exact new checksum sets, sizes, ownership, dates, timezone, tags, availability,
stack membership, and repeat stability. Polling allows three minutes per
stage; each import has a five-minute deadline. A timeout is a failure, not proof
of corruption. A fresh metadata refresh must update every new asset and retain
the verified fields. This does not prove every server queue is empty.

It saves a redacted evidence ZIP and reveals it in Finder on success or failure.
Upload that one ZIP for review. Do not manually repair failures to obtain PASS.
Each invocation creates a new test set; do not rerun just to hide a failed run.

PASS means move to a small real Takeout sample, not directly to the 182 GB import.
It does not yet verify personal albums, videos, Live Photos, or metadata unique
to the real archives. Use the small real-data gate for those.

## Validation completed in the development workspace

Go 1.25.1 on Linux amd64:

- go test ./... — passed
- go test -race ./app/upload ./immich ./internal/assets/cache — passed
- go vet ./... — passed
- go test -tags e2e ./internal/e2e/client -run '^$' — compilation passed only
- python3 -m unittest discover -s scripts -p test_koda_validate.py — passed
- Fresh generated JPEGs decoded; the auditor reproduced the real replacement
  report's missing edited-image tag, with no spurious stack failures.

Live Immich integration tests have NOT run: Docker is absent in the workspace.
The synthetic fixtures are upstream-generated test images, not personal photos.

## Required next gates

1. Fresh database backup and clean integrity baseline on the test target.
2. Synthetic edited-pair and replacement imports against Immich v3.2.4;
   use --on-errors=stop and inspect full logs and event reports.
3. Repeat import; verify originals and edits, checksums, stacks, dates, albums,
   tags, no deleted assets, and no stuck requests.
4. Small real Takeout subset, then integrity and metadata verification.
5. Only after approval, full Takeout migration. Keep original source archives.

Existing synthetic tests can run against a disposable, provisioned Immich test
server using the upstream e2e user configuration:

    go test -tags e2e ./internal/e2e/client -run 'Test_FromGooglePhotos_(EditedPair|ReplacedCopy)$' -timeout 10m

Do not run upstream provisioning/cleanup scripts against a production server.
Review test names with go test -tags e2e ./internal/e2e/client -list GooglePhotos.

## Reproducible Apple Silicon build

    CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -trimpath -tags timetzdata -ldflags '-s -w -X github.com/simulot/immich-go/app.Version=0.32.0-koda.3' -o immich-go-koda .

The downloaded binary is unsigned and has not been executed on macOS here.
