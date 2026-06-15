from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from dst_dashboard.storage.db import DSTDatabase

router = APIRouter(prefix="/experiments", tags=["experiments"])
db = DSTDatabase()


@router.get("", response_model=List[Dict[str, Any]])
async def list_experiments(publish: Optional[bool] = Query(None, description="Filter by publish status")):
    """List all experiments. Use ?publish=true to filter only published experiments."""
    # TODO: Implement experiment listing
    experiments = db.list_experiments()
    
    # Filter by publish status if specified
    if publish is not None:
        experiments = [exp for exp in experiments if exp.get("publish") == publish]
    
    return [
        {
            "id": exp["id"],
            "title": exp["title"],
            "family": exp["family"],
            "metadata": exp["metadata"],
            "publish": exp.get("publish", True),
        }
        for exp in experiments
    ]


@router.get("/{experiment_id}", response_model=Dict[str, Any])
async def get_experiment(experiment_id: str):
    """Get experiment details."""
    # TODO: Implement experiment retrieval
    experiment = db.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment
