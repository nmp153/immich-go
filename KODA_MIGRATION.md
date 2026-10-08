# Koda migration build — candidate 2

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
Album/tag error reporting is not comprehensively changed by this patch.
This build does not repair a library already damaged by an earlier import.

## Validation completed in the development workspace

Go 1.25.1 on Linux amd64:

- go test ./... — passed
- go test -race ./app/upload ./immich — passed
- go vet ./... — passed
- go test -tags e2e ./internal/e2e/client -run '^$' — compilation passed only

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

    CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -trimpath -tags timetzdata -ldflags '-s -w -X github.com/simulot/immich-go/app.Version=0.32.0-koda.2' -o immich-go-koda .

The downloaded binary is unsigned and has not been executed on macOS here.
