# OpenLLM search gateway

<!-- cspell:ignore DDGS duckduckgo ghcr healthz openllm OpenLLM OPENWEBUI scilifelabdatacentre -->

A small service that sends web searches from OpenLLM (Open WebUI) to a search engine, but only after the user who made each search has approved it in Open WebUI. It is the only route for web searches out of the cluster.

This repository contains the gateway and builds its container image. Deployment, the Open WebUI tool and assistant, and the operations runbook are in [openllm-setup](https://github.com/ScilifelabDataCentre/openllm-setup/tree/develop/search-gateway-kth-cluster-k8s).

## How it works

- The Open WebUI tool sends each search to `POST /search`. A new search returns an approval request instead of results, and nothing is sent.
- The user answers in Open WebUI: approve once, approve for this session, or decline. The answer reaches the gateway at `POST /approvals/<id>`, and only the user who searched can give it.
- Approved searches go to one configured search engine (`SEARCH_ENGINE`, DuckDuckGo by default) through the DDGS library.

All endpoints except `GET /healthz` require `Authorization: Bearer <API_KEY>`. Approvals and sessions are kept in memory, so run a single replica; a restart clears them.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `API_KEY` | required | Key shared with Open WebUI |
| `OPENWEBUI_URL` | required | Open WebUI address, used in approval links |
| `SEARCH_ENGINE` | `duckduckgo` | The one engine to use; `auto` or a list is refused at startup |
| `APPROVALS_MODEL` | `search_approvals` | Id of the Search approvals function in Open WebUI |
| `SESSION_HOURS` | `8` | Length of an approved session |
| `APPROVAL_EXPIRY_SECONDS` | `900` | Lifetime of an unanswered approval |
| `MAX_WAITING_PER_USER` | `5` | Open approvals per user |
| `MAX_APPROVALS_PER_HOUR` | `30` | Approval requests per user and hour |

## Development

```bash
python3 tests/test_gateway.py    # checks: plain Python 3.10 or newer, nothing to install
docker build -t search-gateway:dev .
docker run --rm -p 8000:8000 -e API_KEY=test -e OPENWEBUI_URL=http://localhost:3000 search-gateway:dev
```

## Build and release

GitHub Actions (`.github/workflows/build-image.yml`) runs the checks, builds the image and publishes it as `ghcr.io/scilifelabdatacentre/openllm-search-gateway`:

| Event | Published tags |
|---|---|
| Pull request | none (checks and a test build only) |
| Push to `main` | `sha-<short commit>` and `main` |
| Tag `vX.Y.Z` | `X.Y.Z` |

Deploy `sha-...` tags to dev and release tags to production. To make a release:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## Licence

See `LICENSE-CODE` and `LICENSE-CONTENT`.
