# DST Dashboard

Web-based experiment publication and visualization tool.

## Quick Start

```bash
# Run API server
uvicorn dst_dashboard.main:app --reload

# API available at http://localhost:8000
# Swagger UI at http://localhost:8000/api/docs
```

## Environment Variables

```bash
export DST_CONFIG_PATH=~/.cache/dst_dashboard/config.yaml  # Optional, default location
export DST_MONGO_URI=mongodb://localhost:27017             # Optional, default location
export DST_MONGO_DB_NAME=dst_dashboard                      # Optional, default name
export DST_JWT_SECRET=<a real secret>                       # Required outside local dev
```

`config.yaml` only defines datasources (VictoriaLogs/Prometheus connections) - it no
longer defines experiments. Experiments live only in MongoDB and are managed
exclusively through the API (see below).

## Managing experiments

Creating, updating, and deleting experiments requires an admin bearer token.

1. Get a token from the `Admin Page` (Accessible from the vaclab home page).
2. Use it as `Authorization: Bearer <token>` on any write request below.

 `title` must be unique across all experiments.

### Create

```bash
TOKEN="<token>"

curl -X POST https://api.dashboard.lab.vac.dev/experiments \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @experiment.json
```

The response includes the generated `id` - save it, you'll need it for update/delete.
A `409` means an experiment with that `title` already exists.

### Update

```bash
curl -X PUT https://api.dashboard.lab.vac.dev/experiments/<id> \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @experiment.json
```

Only reprocesses datasets/panels if their configuration actually changed.

### Delete

```bash
curl -X DELETE https://api.dashboard.lab.vac.dev/experiments/<id> \
  -H "Authorization: Bearer $TOKEN"
```

Cascades to the experiment's datasets and panels.

### Bulk-loading from a file

See `dst_dashboard/scripts/seed_experiments.py` for loading many experiments at once
from a JSON file (`{"experiments": [...]}`, same shape as a single experiment's body).

There's also a small UI for all of this in the `Admin Page` - paste JSON, create/edit/delete
without needing curl.

## Structure

```
dst_dashboard/
├── main.py                 # FastAPI app entry
├── auth.py                 # Admin JWT issuing/verification
├── config/                 # Config loading + data models
├── processors/              # Data fetching/transformation
├── storage/                 # MongoDB client
├── scripts/                  # Seeding/ops scripts
└── api/                      # FastAPI REST endpoints
```
