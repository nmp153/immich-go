package immich

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// CreateStack create a stack with the given assets, the 1st asset is the cover, return the stack ID
func (ic *ImmichClient) CreateStack(ctx context.Context, ids []string) (string, error) {
	// Copy IDs so validation never mutates the caller's slice; preserve cover order.
	clean := make([]string, 0, len(ids))
	seen := make(map[string]bool, len(ids))
	for _, id := range ids {
		if id != "" && !seen[id] {
			clean = append(clean, id)
			seen[id] = true
		}
	}
	ids = clean
	if len(ids) < 2 {
		return "", fmt.Errorf("stack must have at least 2 distinct assets")
	}

	// A stack is a small metadata request. Bound the entire request (including
	// response-body decoding) independently of the much longer upload timeout.
	timeout := ic.stackTimeout
	if timeout <= 0 {
		timeout = 90 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	if ic.dryRun {
		return uuid.NewString(), nil
	}

	param := struct {
		AssetIds []string `json:"assetIds"`
	}{
		AssetIds: ids,
	}

	var result struct {
		ID             string `json:"id"`
		PrimaryAssetID string `json:"primaryAssetId"`
	}

	err := ic.newServerCall(ctx, "createStack").do(postRequest("/stacks", "application/json", setAcceptJSON(), setJSONBody(param)), responseJSON(&result))
	return result.ID, err
}
