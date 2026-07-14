"""Dataset API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request

from dst_dashboard.auth import require_admin_token
from dst_dashboard.config.data_structures import DatasetConfig, ExperimentConfig
from dst_dashboard.storage.db import DSTDatabase

router = APIRouter(prefix="/experiments/{experiment_id}/datasets", tags=["datasets"])


@router.get("")
def get_experiment_datasets(experiment_id: str, request: Request):
    """Get all datasets for an experiment with their data."""
    db = DSTDatabase()

    # Get experiment from database (source of truth)
    experiment_data = db.get_experiment(experiment_id)
    if experiment_data is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    experiment = ExperimentConfig(**experiment_data)

    # Get all datasets with their data
    datasets = []
    for dataset_config in experiment.datasets:
        cached_data = db.get_dataset(experiment_id, dataset_config.name)

        datasets.append(
            {
                "name": dataset_config.name,
                "datasource": dataset_config.datasource,
                "timeRange": {
                    "start": dataset_config.timeRange.start.isoformat(),
                    "end": dataset_config.timeRange.end.isoformat(),
                },
                "schema": [{"name": f.name, "type": f.type} for f in dataset_config.schema],
                "rowCount": len(cached_data) if cached_data else 0,
                "data": cached_data if cached_data else [],
            }
        )

    return {"experiment_id": experiment_id, "datasets": datasets}


@router.get("/{dataset_name}", response_model=DatasetConfig)
def get_dataset(experiment_id: str, dataset_name: str, request: Request):
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
def get_dataset_data(experiment_id: str, dataset_name: str, request: Request):
    """Get cached dataset data.

    This endpoints always serves from mongodb.
    To refresh, use POST /admin/experiments/{experiment_id}/reprocess, 
    which keeps datasets and their derived panels in sync.
    """
    db = DSTDatabase()

    # Get experiment from database
    experiment_data = db.get_experiment(experiment_id)
    if experiment_data is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    experiment = ExperimentConfig(**experiment_data)

    if not any(dataset.name == dataset_name for dataset in experiment.datasets):
        raise HTTPException(status_code=404, detail="Dataset not found")

    cached_data = db.get_dataset(experiment_id, dataset_name)
    if cached_data is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Dataset '{dataset_name}' has not been processed yet. "
                f"POST /admin/experiments/{experiment_id}/reprocess to fetch it."
            ),
        )

    return {"data": cached_data, "source": "cache"}


@router.delete("/{dataset_name}", status_code=204)
def delete_dataset(
    experiment_id: str,
    dataset_name: str,
    request: Request,
    _: None = Depends(require_admin_token),
):
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
