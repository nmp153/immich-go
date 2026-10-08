package upload

import (
	"context"
	"errors"
	"io"
	"log/slog"
	"reflect"
	"testing"
	"time"

	"github.com/simulot/immich-go/app"
	"github.com/simulot/immich-go/immich"
	"github.com/simulot/immich-go/internal/assets"
	"github.com/simulot/immich-go/internal/assettracker"
	"github.com/simulot/immich-go/internal/fileevent"
	"github.com/simulot/immich-go/internal/fileprocessor"
)

type kodaStackClient struct {
	immich.ImmichInterface
	err   error
	calls int
	ids   []string
}

func (c *kodaStackClient) CreateStack(_ context.Context, ids []string) (string, error) {
	c.calls++
	c.ids = append([]string(nil), ids...)
	return "stack", c.err
}

func TestKodaGroupStackReportingAndAlreadyProcessedIDs(t *testing.T) {
	for _, fail := range []bool{true, false} {
		t.Run(map[bool]string{true: "failure", false: "success"}[fail], func(t *testing.T) {
			logger := slog.New(slog.NewTextHandler(io.Discard, nil))
			application := app.New(t.Context(), nil)
			application.SetLog(&app.Log{Logger: logger})
			fp := fileprocessor.New(assettracker.New(), fileevent.NewRecorder(logger))
			application.SetFileProcessor(fp)
			client := &kodaStackClient{}
			sentinel := errors.New("stack API failed")
			if fail {
				client.err = sentinel
			}
			uc := &UpCmd{app: application, assetIndex: newAssetIndex(), client: app.Client{Immich: client}}
			var groupAssets []*assets.Asset
			for _, id := range []string{"a", "b"} {
				indexed := localAsset(id+".jpg", id+".jpg", 100, id, time.Now())
				indexed.ID = id
				uc.assetIndex.addLocalAsset(indexed)
				local := localAsset(id+".jpg", id+".jpg", 100, id, indexed.CaptureDate)
				groupAssets = append(groupAssets, local)
				fp.RecordAssetDiscovered(t.Context(), local.File, 100, fileevent.DiscoveredImage)
			}
			err := uc.handleGroup(t.Context(), assets.NewGroup(assets.GroupByOther, groupAssets...))
			if fail && !errors.Is(err, sentinel) {
				t.Fatalf("stack failure lost: %v", err)
			}
			if !fail && err != nil {
				t.Fatal(err)
			}
			if client.calls != 1 || !reflect.DeepEqual(client.ids, []string{"a", "b"}) {
				t.Fatalf("stack calls=%d IDs=%v", client.calls, client.ids)
			}
			counts := fp.GetEventCounts()
			if fail {
				if counts[fileevent.ProcessedStacked] != 0 || counts[fileevent.ErrorServerError] != 1 {
					t.Fatalf("failure report: %v", counts)
				}
			} else if counts[fileevent.ProcessedStacked] != 2 {
				t.Fatalf("success report: %v", counts)
			}
		})
	}
}
