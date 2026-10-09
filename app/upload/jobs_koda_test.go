package upload

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"testing"

	"github.com/simulot/immich-go/app"
	"github.com/simulot/immich-go/immich"
	"github.com/simulot/immich-go/internal/assets"
	"github.com/simulot/immich-go/internal/assets/cache"
)

type kodaJobClient struct {
	immich.ImmichInterface
	calls int
	err   error
}

func (c *kodaJobClient) SendJobCommand(ctx context.Context, _ string, command immich.JobCommand, _ bool) (immich.SendJobCommandResponse, error) {
	c.calls++
	if err := ctx.Err(); err != nil {
		return immich.SendJobCommandResponse{}, err
	}
	if command != immich.Resume {
		return immich.SendJobCommandResponse{}, errors.New("unexpected job command")
	}
	return immich.SendJobCommandResponse{}, c.err
}

func TestKodaFinishingHonorsJobManagement(t *testing.T) {
	for _, enabled := range []bool{false, true} {
		t.Run(map[bool]string{false: "regular-user-job-management-disabled", true: "resume-after-cancellation"}[enabled], func(t *testing.T) {
			application := app.New(t.Context(), nil)
			application.SetLog(&app.Log{Logger: slog.New(slog.NewTextHandler(io.Discard, nil))})
			client := &kodaJobClient{}
			if !enabled {
				client.err = errors.New("403: regular user cannot manage jobs")
			}
			uc := &UpCmd{
				app:         application,
				client:      app.Client{AdminImmich: client, PauseImmichBackgroundJobs: enabled},
				albumsCache: cache.NewCollectionCache[assets.Album](1, nil),
				tagsCache:   cache.NewCollectionCache[assets.Tag](1, nil),
			}
			ctx, cancel := context.WithCancel(t.Context())
			cancel()
			if err := uc.finishing(ctx); err != nil {
				t.Fatalf("finishing: %v", err)
			}
			want := 0
			if enabled {
				want = 5
			}
			if client.calls != want {
				t.Fatalf("job requests = %d, want %d", client.calls, want)
			}
			if err := uc.finishing(ctx); err != nil || client.calls != want {
				t.Fatalf("second finishing: err=%v job requests=%d", err, client.calls)
			}
		})
	}
}
