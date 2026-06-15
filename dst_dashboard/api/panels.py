"""Panel API routes."""
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from dst_dashboard.storage.db import DSTDatabase

router = APIRouter(prefix="/experiments/{experiment_id}/panels", tags=["panels"])
db = DSTDatabase()

@router.get("", response_model=Dict[str, Any])
async def list_panels(experiment_id: str):
    """List all panels for an experiment."""
    # TODO: Implement panel listing
    panels = db.list_panels(experiment_id)
    if panels is None:
        raise HTTPException(status_code=404, detail="Panels not found")
    return panels

@router.get("/{panel_name}", response_model=Dict[str, Any])
async def get_panel_data(experiment_id: str, panel_name: str):
    """Get transformed panel data for visualization.
    
    TODO: Use PanelProcessor
    """
    data = db.get_panel_data(experiment_id, panel_name)
    if data is None:
        raise HTTPException(status_code=404, detail="Panel data not found")
    return data
