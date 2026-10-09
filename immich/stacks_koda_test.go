package immich

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"reflect"
	"sync/atomic"
	"testing"
	"time"
)

func TestKodaStackValidationAndRepeat(t *testing.T) {
	var calls atomic.Int32
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if r.URL.Path != "/api/stacks" || r.Method != "POST" {
			t.Errorf("unexpected request %s %s", r.Method, r.URL.Path)
		}
		var body struct {
			IDs []string `json:"assetIds"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
		}
		if !reflect.DeepEqual(body.IDs, []string{"cover", "other"}) {
			t.Errorf("IDs = %v", body.IDs)
		}
		io.WriteString(w, `{"id":"stack"}`)
	}))
	defer s.Close()
	ic, err := NewImmichClient(s.URL, "test")
	if err != nil {
		t.Fatal(err)
	}
	defer ic.client.CloseIdleConnections()
	ids := []string{"", "cover", "cover", "other", ""}
	original := append([]string(nil), ids...)
	for range 2 {
		id, err := ic.CreateStack(context.Background(), ids)
		if err != nil || id != "stack" {
			t.Fatalf("%s %v", id, err)
		}
	}
	if !reflect.DeepEqual(ids, original) {
		t.Fatal("modified input IDs")
	}
	for _, invalid := range [][]string{nil, {""}, {"one", "one", ""}} {
		if _, err := ic.CreateStack(context.Background(), invalid); err == nil {
			t.Fatalf("accepted %v", invalid)
		}
	}
	if calls.Load() != 2 {
		t.Fatalf("calls = %d", calls.Load())
	}
}

// Exercise real net/http cancellation before headers, during JSON decoding,
// and while decoding an error body. Then prove another request can complete.
func TestKodaStackDeadlineAndWorkerRecovery(t *testing.T) {
	for _, mode := range []string{"headers", "body", "error-body"} {
		t.Run(mode, func(t *testing.T) {
			var calls atomic.Int32
			release := make(chan struct{})
			s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				io.Copy(io.Discard, r.Body)
				if calls.Add(1) == 1 {
					if mode != "headers" {
						w.Header().Set("Content-Type", "application/json")
						if mode == "error-body" {
							w.WriteHeader(500)
						}
						io.WriteString(w, `{`)
						w.(http.Flusher).Flush()
					}
					select {
					case <-r.Context().Done():
					case <-release:
					}
					return
				}
				io.WriteString(w, `{"id":"recovered"}`)
			}))
			defer s.Close()
			defer close(release)
			ic, err := NewImmichClient(s.URL, "test", OptionConnectionTimeout(time.Hour))
			if err != nil {
				t.Fatal(err)
			}
			defer ic.client.CloseIdleConnections()
			ic.stackTimeout = 50 * time.Millisecond
			start := time.Now()
			_, err = ic.CreateStack(context.Background(), []string{"a", "b"})
			if err == nil {
				t.Fatal("hung request reported success")
			}
			if mode != "error-body" && !errors.Is(err, context.DeadlineExceeded) {
				t.Fatalf("not a deadline error: %v", err)
			}
			if time.Since(start) > time.Second {
				t.Fatal("stack exceeded bounded wait")
			}
			id, err := ic.CreateStack(context.Background(), []string{"a", "b"})
			if err != nil || id != "recovered" {
				t.Fatalf("worker cannot continue: %s %v", id, err)
			}
		})
	}
}

func TestKodaStackParentCancellation(t *testing.T) {
	ic, err := NewImmichClient("http://127.0.0.1:1", "test")
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, err = ic.CreateStack(ctx, []string{"a", "b"})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation lost: %v", err)
	}
}
