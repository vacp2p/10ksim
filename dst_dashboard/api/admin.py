"""Admin API routes for configuration and data management."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from dst_dashboard.auth import create_admin_token, require_admin_token
from dst_dashboard.config.utils import LoadConfig
from dst_dashboard.processors.experiment_processor import ExperimentProcessor
from dst_dashboard.storage.db import DSTDatabase

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

_ADMIN_HTML_PATH = Path(__file__).parent.parent / "static" / "admin.html"


@router.post("/reload")
def reload_config(request: Request, _: None = Depends(require_admin_token)):
    """Reload datasources from config.yaml (experiments are API-managed and unaffected)."""
    try:
        logger.info("Reloading configuration...")

        # Load and validate configuration
        config = LoadConfig().WithValidateDatasources()
        logger.info(f"Reloaded configuration with {len(config.datasources)} datasources")

        # Update app state
        request.app.state.config = config
        request.app.state.datasources = config.datasources

        # Initialize database
        db = DSTDatabase()

        # Clear and re-insert datasources
        db.datasources.delete_many({})
        db.insert_datasource_list(config.datasources)
        logger.info(f"Re-inserted {len(config.datasources)} datasources")

        return {
            "status": "success",
            "message": "Datasources reloaded successfully",
            "summary": {
                "datasources": len(config.datasources),
            },
        }

    except Exception as e:
        logger.error(f"Failed to reload configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reload configuration: {str(e)}")


@router.delete("/datasets/{experiment_id}/{dataset_name}")
def clear_dataset(experiment_id: str, dataset_name: str, _: None = Depends(require_admin_token)):
    """Clear cached dataset data to force re-fetch on next request."""
    try:
        db = DSTDatabase()

        if db.delete_dataset(experiment_id, dataset_name):
            logger.info(f"Cleared dataset: {experiment_id}:{dataset_name}")
            return {
                "status": "success",
                "message": f"Dataset '{dataset_name}' cleared successfully",
            }
        else:
            raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear dataset: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear dataset: {str(e)}")


@router.delete("/datasets")
def clear_all_datasets(_: None = Depends(require_admin_token)):
    """Clear all cached dataset data to force re-fetch."""
    try:
        db = DSTDatabase()
        count = db.clear_all_dataset_cache()

        logger.info(f"Cleared {count} datasets")

        return {"status": "success", "message": f"Cleared {count} datasets successfully"}

    except Exception as e:
        logger.error(f"Failed to clear datasets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear datasets: {str(e)}")


@router.post("/experiments/{experiment_id}/reprocess")
def reprocess_experiment(
    experiment_id: str, request: Request, _: None = Depends(require_admin_token)
):
    """Reprocess a single experiment - fetch datasets and regenerate panels."""
    try:
        db = DSTDatabase()

        # Get experiment from database
        experiment_data = db.get_experiment(experiment_id)
        if not experiment_data:
            raise HTTPException(status_code=404, detail="Experiment not found")

        # Get config from app state
        config = request.app.state.config

        # Initialize processor
        from dst_dashboard.config.data_structures import ExperimentConfig

        processor = ExperimentProcessor(config, db)

        experiment = ExperimentConfig(**experiment_data)

        logger.info(f"Reprocessing experiment: {experiment_id}")

        # Process the experiment (this will fetch datasets and transform panels)
        success = processor.process_experiment(experiment)

        if success:
            return {
                "status": "success",
                "message": f"Experiment '{experiment_id}' reprocessed successfully",
                "experiment_id": experiment_id,
                "datasets_count": len(experiment.datasets),
                "panels_count": len(experiment.panels),
            }
        else:
            raise HTTPException(
                status_code=500, detail=f"Failed to reprocess experiment '{experiment_id}'"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reprocess experiment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reprocess experiment: {str(e)}")


@router.get("/token", response_class=HTMLResponse)
def admin_page():
    """
    Serve the admin page: a "Generate token" button, plus a small UI for
    creating/editing/deleting experiments by pasting JSON.

    Not gated by require_admin_token - you need this page to get a token in
    the first place. Access is instead controlled upstream by Authentik
    forward-auth on this ingress path (which covers both GET and POST here).
    """
    return HTMLResponse(content=_ADMIN_HTML_PATH.read_text())


@router.post("/token")
def generate_admin_token():
    """Mint a fresh admin-scope token. Same protection boundary as GET /admin/token."""
    return {"token": create_admin_token()}
