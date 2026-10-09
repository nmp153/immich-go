package immich

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"
)

func TestEnsureStackPreservesExactMembershipAndCover(t *testing.T) {
	for _, mode := range []string{"same", "fresh", "changed", "read-error"} {
		t.Run(mode, func(t *testing.T) {
			var posts atomic.Int32
			s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch r.Method + " " + r.URL.Path {
				case "GET /api/assets/a":
					if mode == "read-error" {
						http.Error(w, "forbidden", 403)
						return
					}
					if mode == "fresh" {
						io.WriteString(w, `{"id":"a","stack":null}`)
						return
					}
					io.WriteString(w, `{"id":"a","stack":{"id":"old","primaryAssetId":"b","assetCount":2}}`)
				case "GET /api/stacks/old":
					if mode == "changed" {
						io.WriteString(w, `{"id":"old","primaryAssetId":"b","assets":[{"id":"b"},{"id":"c"}]}`)
						return
					}
					io.WriteString(w, `{"id":"old","primaryAssetId":"b","assets":[{"id":"b"},{"id":"a"}]}`)
				case "POST /api/stacks":
					posts.Add(1)
					io.WriteString(w, `{"id":"new","primaryAssetId":"a"}`)
				default:
					t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
					http.NotFound(w, r)
				}
			}))
			defer s.Close()
			ic, err := NewImmichClient(s.URL, "test")
			if err != nil {
				t.Fatal(err)
			}
			id, err := ic.EnsureStack(t.Context(), []string{"", "a", "a", "b"})
			if mode == "read-error" {
				if err == nil || posts.Load() != 0 {
					t.Fatalf("read failure must not POST: id=%s err=%v posts=%d", id, err, posts.Load())
				}
				return
			}
			wantID, wantPosts := "new", int32(1)
			if mode == "same" {
				wantID, wantPosts = "old", 0
			}
			if err != nil || id != wantID || posts.Load() != wantPosts {
				t.Fatalf("id=%s err=%v posts=%d", id, err, posts.Load())
			}
		})
	}
}

func TestEnsureStackReadDeadline(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-r.Context().Done() }))
	defer s.Close()
	ic, err := NewImmichClient(s.URL, "test")
	if err != nil {
		t.Fatal(err)
	}
	ic.stackTimeout = 50 * time.Millisecond
	_, err = ic.EnsureStack(t.Context(), []string{"a", "b"})
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("deadline lost: %v", err)
	}
}
