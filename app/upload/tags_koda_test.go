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
	"github.com/simulot/immich-go/internal/assettracker"
	"github.com/simulot/immich-go/internal/fileevent"
	"github.com/simulot/immich-go/internal/fileprocessor"
)

type kodaTagClient struct {
	immich.ImmichInterface
	results   []immich.TagAssetsResponse
	albumsErr error
}

func (c *kodaTagClient) TagAssets(context.Context, string, []string) ([]immich.TagAssetsResponse, error) {
	return c.results, nil
}
func (c *kodaTagClient) UpsertTags(context.Context, []string) ([]immich.TagSimplified, error) {
	return nil, nil
}
func (c *kodaTagClient) GetAllAlbums(context.Context) ([]immich.AlbumSimplified, error) {
	return nil, c.albumsErr
}
func (c *kodaTagClient) GetAssetStatistics(context.Context) (immich.UserStatistics, error) {
	return immich.UserStatistics{}, nil
}
func (c *kodaTagClient) GetAllAssets(context.Context, func(*immich.Asset) error) error { return nil }

type kodaEmptyReader struct{}

func (kodaEmptyReader) Browse(context.Context) chan *assets.Group {
	ch := make(chan *assets.Group)
	close(ch)
	return ch
}

func kodaTestApplication(t *testing.T) *app.Application {
	a := app.New(t.Context(), nil)
	l := slog.New(slog.NewTextHandler(io.Discard, nil))
	a.SetLog(&app.Log{Logger: l})
	a.SetFileProcessor(fileprocessor.New(assettracker.New(), fileevent.NewRecorder(l)))
	a.ConcurrentTask = 1
	return a
}

func TestSaveTagsChecksEveryResult(t *testing.T) {
	for _, tc := range []struct {
		name    string
		results []immich.TagAssetsResponse
		ok      bool
	}{
		{"success", []immich.TagAssetsResponse{{ID: "a", Success: true}, {ID: "b", Success: true}}, true},
		{"already-tagged", []immich.TagAssetsResponse{{ID: "a", Success: true}, {ID: "b", Error: "duplicate"}}, true},
		{"partial-failure", []immich.TagAssetsResponse{{ID: "a", Success: true}, {ID: "b", Error: "not_found"}}, false},
		{"missing", []immich.TagAssetsResponse{{ID: "a", Success: true}}, false},
		{"duplicate-result", []immich.TagAssetsResponse{{ID: "a", Success: true}, {ID: "a", Success: true}}, false},
		{"unknown-result", []immich.TagAssetsResponse{{ID: "a", Success: true}, {ID: "b", Success: true}, {ID: "c", Success: true}}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			uc := &UpCmd{app: kodaTestApplication(t), client: app.Client{Immich: &kodaTagClient{results: tc.results}}}
			_, err := uc.saveTags(t.Context(), assets.Tag{ID: "tag", Value: "test"}, []string{"a", "b"})
			if (err == nil) != tc.ok {
				t.Fatalf("err=%v want success=%v", err, tc.ok)
			}
		})
	}
	uc := &UpCmd{app: kodaTestApplication(t), client: app.Client{Immich: &kodaTagClient{}}}
	if _, err := uc.saveTags(t.Context(), assets.Tag{Value: "new"}, []string{"a"}); err == nil {
		t.Fatal("accepted empty upsert response")
	}
}

func TestNoUIRetainsFinishingAndPreparationErrors(t *testing.T) {
	for _, preparation := range []bool{false, true} {
		t.Run(map[bool]string{false: "final-tag-save", true: "album-list"}[preparation], func(t *testing.T) {
			failure := errors.New("server rejected request")
			client := &kodaTagClient{}
			if preparation {
				client.albumsErr = failure
			}
			a := kodaTestApplication(t)
			uc := &UpCmd{app: a, adapter: kodaEmptyReader{}, client: app.Client{Immich: client}, assetIndex: newAssetIndex(), immichAssetsReady: make(chan struct{})}
			uc.tagsCache = cache.NewCollectionCache(50, func(tag assets.Tag, ids []string) (assets.Tag, error) { return tag, failure })
			uc.tagsCache.AddIDToCollection("test", assets.Tag{ID: "tag"}, "a")
			err := uc.runNoUI(t.Context(), a)
			if preparation {
				_ = uc.finishing(t.Context())
			}
			if !errors.Is(err, failure) {
				t.Fatalf("error lost before CLI exit: %v", err)
			}
		})
	}
}
