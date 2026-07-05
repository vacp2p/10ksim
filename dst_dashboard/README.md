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
export DST_DB_PATH=~/.cache/dst_dashboard  # Optional, default location
```

## Structure

```
dst_dashboard/
├── main.py                        # FastAPI app entry
├── experiment_descriptors/        # YAML config models
├── processors/                    # Data fetching/transformation
├── storage/                       # MontyDB cache
└── api/                           # FastAPI REST endpoints
```