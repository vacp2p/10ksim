"""Panel API routes."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from dst_dashboard.auth import require_admin_token
from dst_dashboard.config.data_structures import ExperimentConfig
from dst_dashboard.storage.db import DSTDatabase

router = APIRouter(prefix="/experiments/{experiment_id}/panels", tags=["panels"])
logger = logging.getLogger(__name__)


@router.get("")
def get_all_panels(experiment_id: str, request: Request) -> Dict[str, Any]:
    """Get all panels for an experiment with their rendered visualizations."""
    db = DSTDatabase()

    # Get experiment from database
    experiment_data = db.get_experiment(experiment_id)
    if experiment_data is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    experiment = ExperimentConfig(**experiment_data)

    # Get panel processor to transform data on-demand
    from dst_dashboard.api.utils import get_panel_processor

    processor = get_panel_processor(request)

    # Get stored panel data from database
    rendered_panels = []
    for panel_config in experiment.panels:
        # Get pre-processed panel from database
        panel_data = processor.db.get_panel_data(experiment_id, panel_config.name)

        if panel_data:
            rendered_panels.append(
                {
                    "panel_name": panel_config.name,
                    "panel_title": panel_config.title,
                    "panel_type": panel_config.type,
                    "dataset": panel_config.dataset,
                    "option": panel_data,
                }
            )
        else:
            logger.warning(
                f"Panel '{panel_config.name}' not found in database, may need reprocessing"
            )
            rendered_panels.append(
                {
                    "panel_name": panel_config.name,
                    "panel_title": panel_config.title,
                    "panel_type": panel_config.type,
                    "dataset": panel_config.dataset,
                    "error": "Panel not preprocessed",
                }
            )

    return {"experiment_id": experiment_id, "panels": rendered_panels}


@router.get("/by-dataset/{dataset_name}")
def get_panels_by_dataset(
    experiment_id: str, dataset_name: str, request: Request
) -> Dict[str, Any]:
    """Get all preprocessed panels that use a specific dataset."""
    db = DSTDatabase()

    # Get experiment from database
    experiment_data = db.get_experiment(experiment_id)
    if experiment_data is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    experiment = ExperimentConfig(**experiment_data)

    # Filter panels by dataset
    matching_panels = [p for p in experiment.panels if p.dataset == dataset_name]

    if not matching_panels:
        return {"experiment_id": experiment_id, "dataset_name": dataset_name, "panels": []}

    # Retrieve preprocessed panels from database
    rendered_panels = []
    for panel_config in matching_panels:
        panel_data = db.get_panel_data(experiment_id, panel_config.name)

        if panel_data is not None:
            rendered_panels.append(
                {
                    "panel_name": panel_config.name,
                    "panel_title": panel_config.title,
                    "panel_type": panel_config.type,
                    "option": panel_data,
                }
            )
        else:
            rendered_panels.append(
                {
                    "panel_name": panel_config.name,
                    "panel_title": panel_config.title,
                    "panel_type": panel_config.type,
                    "error": "Panel data not found in database. Please reprocess the experiment.",
                }
            )

    return {"experiment_id": experiment_id, "dataset_name": dataset_name, "panels": rendered_panels}


@router.get("/{panel_name}")
def get_panel(experiment_id: str, panel_name: str, request: Request) -> Dict[str, Any]:
    """Get a preprocessed panel with its rendered ECharts option."""
    db = DSTDatabase()

    # Get experiment from database
    experiment_data = db.get_experiment(experiment_id)
    if experiment_data is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    experiment = ExperimentConfig(**experiment_data)

    # Find panel config
    panel_config = None
    for panel in experiment.panels:
        if panel.name == panel_name:
            panel_config = panel
            break

    if panel_config is None:
        raise HTTPException(status_code=404, detail="Panel not found")

    # Get preprocessed panel data from database
    panel_data = db.get_panel_data(experiment_id, panel_name)

    if panel_data is None:
        raise HTTPException(
            status_code=404,
            detail="Panel data not found in database. Please reprocess the experiment.",
        )

    return {
        "panel_name": panel_name,
        "panel_title": panel_config.title,
        "panel_type": panel_config.type,
        "option": panel_data,
    }


@router.delete("/{panel_name}", status_code=204)
def delete_panel(
    experiment_id: str,
    panel_name: str,
    request: Request,
    _: None = Depends(require_admin_token),
):
    """Delete a panel."""
    db = DSTDatabase()

    # Get experiment from database
    experiment_data = db.get_experiment(experiment_id)
    if experiment_data is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    experiment = ExperimentConfig(**experiment_data)

    # Find panel
    panel_index = None
    for i, p in enumerate(experiment.panels):
        if p.name == panel_name:
            panel_index = i
            break

    if panel_index is None:
        raise HTTPException(status_code=404, detail="Panel not found")

    # Remove panel from experiment
    experiment.panels.pop(panel_index)

    # Update experiment in database
    db.store_experiment(experiment.model_dump())

    # Delete cached panel data
    db.delete_panel(experiment_id, panel_name)

    return None
