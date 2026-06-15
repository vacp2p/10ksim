"""Dataset API routes."""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException
from dst_dashboard.storage.db import DSTDatabase

router = APIRouter(
    prefix="/experiments/{experiment_id}/datasets", tags=["datasets"]
)
db = DSTDatabase()


@router.get("/{dataset_name}", response_model=List[Dict[str, Any]])
async def get_dataset(experiment_id: str, dataset_name: str):
    """Get dataset data.
    
    TODO: Use DatasetProcessor
    """
    data = db.get_dataset(experiment_id, dataset_name)
    if data is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return data
