"""Dataset API routes."""

from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Request, Body
from pydantic import BaseModel

from dst_dashboard.config.data_structures import DatasetConfig, ExperimentConfig
from dst_dashboard.storage.db import DSTDatabase
from dst_dashboard.api.utils import get_processor

router = APIRouter(
    prefix="/experiments/{experiment_id}/datasets", tags=["datasets"]
)


class DatasetDataUpdate(BaseModel):
    """Model for updating dataset data."""
    data: List[Dict[str, Any]]


@router.get("")
async def get_experiment_datasets(experiment_id: str, request: Request):
    """
    Get all datasets for an experiment with their data.
    
    Args:
        experiment_id: Experiment identifier
        
    Returns:
        List of datasets with their configurations and data
    """
    db = DSTDatabase()
    
    # Get experiment from database (source of truth)
    experiment_data = db.get_experiment(experiment_id)
    if experiment_data is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    experiment = ExperimentConfig(**experiment_data)
    
    # Initialize database
    db = DSTDatabase()
    
    # Get all datasets with their data
    datasets = []
    for dataset_config in experiment.datasets:
        cached_data = db.get_dataset(experiment_id, dataset_config.name)
        
        datasets.append({
            "name": dataset_config.name,
            "datasource": dataset_config.datasource,
            "timeRange": {
                "start": dataset_config.timeRange.start.isoformat(),
                "end": dataset_config.timeRange.end.isoformat()
            },
            "schema": [{"name": f.name, "type": f.type} for f in dataset_config.schema],
            "rowCount": len(cached_data) if cached_data else 0,
            "data": cached_data if cached_data else []
        })
    
    return {
        "experiment_id": experiment_id,
        "datasets": datasets
    }


@router.get("/{dataset_name}", response_model=DatasetConfig)
async def get_dataset(experiment_id: str, dataset_name: str, request: Request):
    """Get dataset configuration for an experiment."""
    db = DSTDatabase()
    
    # Get experiment from database
    experiment_data = db.get_experiment(experiment_id)
    if experiment_data is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    experiment = ExperimentConfig(**experiment_data)
    
    # Find dataset
    for dataset in experiment.datasets:
        if dataset.name == dataset_name:
            return dataset
    
    raise HTTPException(status_code=404, detail="Dataset not found")


@router.get("/{dataset_name}/data")
async def get_dataset_data(
    experiment_id: str,
    dataset_name: str,
    request: Request,
    refresh: bool = False
):
    """
    Get dataset data (with caching support).
    
    Args:
        experiment_id: Experiment identifier
        dataset_name: Dataset name
        refresh: If True, force re-fetch from datasource even if cached
        
    Returns:
        Dataset data (list of records)
    """
    db = DSTDatabase()
    
    # Get experiment from database
    experiment_data = db.get_experiment(experiment_id)
    if experiment_data is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    experiment = ExperimentConfig(**experiment_data)
    
    # Find dataset config
    dataset_config = None
    for dataset in experiment.datasets:
        if dataset.name == dataset_name:
            dataset_config = dataset
            break
    
    if dataset_config is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Initialize processor
    processor = get_processor(request)
    
    # Check cache unless refresh requested
    if not refresh:
        cached_data = db.get_dataset(experiment_id, dataset_name)
        if cached_data is not None:
            return {"data": cached_data, "source": "cache"}
    
    # Fetch fresh data using processor
    try:
        data = processor.fetch_dataset(experiment_id, dataset_config)
        
        # Update cache
        if data:
            db.store_dataset(experiment_id, dataset_name, data)
        
        return {"data": data, "source": "datasource"}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch dataset: {str(e)}"
        )


@router.delete("/{dataset_name}", status_code=204)
async def delete_dataset(experiment_id: str, dataset_name: str, request: Request):
    """Delete a dataset and its data."""
    db = DSTDatabase()
    
    # Get experiment from database
    experiment_data = db.get_experiment(experiment_id)
    if experiment_data is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    experiment = ExperimentConfig(**experiment_data)
    
    # Find dataset
    dataset_index = None
    for i, ds in enumerate(experiment.datasets):
        if ds.name == dataset_name:
            dataset_index = i
            break
    
    if dataset_index is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Remove dataset from experiment
    experiment.datasets.pop(dataset_index)
    db.store_experiment(experiment.model_dump())
    
    # Delete dataset data
    db.delete_dataset(experiment_id, dataset_name)
    
    return None
