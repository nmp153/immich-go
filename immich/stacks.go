package immich

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// EnsureStack preserves an existing, exact stack, including a cover chosen by
// the user. POST /stacks recreates stacks, even when their members are unchanged.
// Keep CreateStack available for commands that intentionally change the cover.
func (ic *ImmichClient) EnsureStack(ctx context.Context, ids []string) (string, error) {
	wanted := make(map[string]bool, len(ids))
	clean := make([]string, 0, len(ids))
	for _, id := range ids {
		if id != "" && !wanted[id] {
			wanted[id] = true
			clean = append(clean, id)
		}
	}
	if len(clean) < 2 {
		return "", fmt.Errorf("stack must have at least 2 distinct assets")
	}
	if ic.dryRun {
		return ic.CreateStack(ctx, clean)
	}
	timeout := ic.stackTimeout
	if timeout <= 0 {
		timeout = 90 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	asset, err := ic.GetAssetInfo(ctx, clean[0])
	if err != nil {
		return "", fmt.Errorf("check existing stack: %w", err)
	}
	if asset.Stack != nil && asset.Stack.ID != "" {
		var existing struct {
			ID             string `json:"id"`
			PrimaryAssetID string `json:"primaryAssetId"`
			Assets         []struct {
				ID string `json:"id"`
			} `json:"assets"`
		}
		err := ic.newServerCall(ctx, "getStack").do(
			getRequest("/stacks/"+asset.Stack.ID, setAcceptJSON()), responseJSON(&existing))
		if err != nil {
			return "", fmt.Errorf("read existing stack: %w", err)
		}
		members := make(map[string]bool, len(existing.Assets))
		for _, member := range existing.Assets {
			members[member.ID] = true
		}
		match := existing.ID == asset.Stack.ID && members[existing.PrimaryAssetID] && len(existing.Assets) == len(wanted) && len(members) == len(wanted)
		for id := range wanted {
			match = match && members[id]
		}
		if match {
			return existing.ID, nil
		}
	}
	return ic.CreateStack(ctx, clean)
}

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
