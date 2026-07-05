"""Admin API routes for configuration and data management."""

from fastapi import APIRouter, Request, HTTPException
import logging

from dst_dashboard.config.utils import LoadConfig
from dst_dashboard.storage.db import DSTDatabase
from dst_dashboard.processors.experiment_processor import ExperimentProcessor

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.post("/reload")
async def reload_config(request: Request):
    """
    Reload configuration from file and re-process all experiments.
    
    This will:
    1. Reload the config file
    2. Clear and re-insert datasources
    3. Re-process all experiments (fetch datasets, store panels)
    
    Returns:
        Summary of reloaded data
    """
    try:
        logger.info("Reloading configuration...")
        
        # Load and validate configuration
        config = LoadConfig().WithValidateDatasources()
        logger.info(
            f"Reloaded configuration with {len(config.datasources)} datasources "
            f"and {len(config.experiments)} experiments"
        )
        
        # Update app state
        request.app.state.config = config
        request.app.state.datasources = config.datasources
        
        # Initialize database
        db = DSTDatabase()
        
        # Clear and re-insert datasources
        db.datasources.delete_many({})
        db.insert_datasource_list(config.datasources)
        logger.info(f"Re-inserted {len(config.datasources)} datasources")
        
        # Initialize experiment processor
        processor = ExperimentProcessor(config, db)
        
        # Process all experiments
        results = processor.process_all_experiments()
        
        logger.info(
            f"Configuration reload completed: "
            f"{len(results['processed_experiments'])}/{results['total_experiments']} experiments processed"
        )
        
        return {
            "status": "success",
            "message": "Configuration reloaded successfully",
            "summary": {
                "datasources": len(config.datasources),
                "experiments_total": results['total_experiments'],
                "experiments_processed": len(results['processed_experiments']),
                "experiments_failed": len(results['failed_experiments']),
            },
            "details": results
        }
        
    except Exception as e:
        logger.error(f"Failed to reload configuration: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload configuration: {str(e)}"
        )


@router.delete("/datasets/{experiment_id}/{dataset_name}")
async def clear_dataset(experiment_id: str, dataset_name: str):
    """
    Clear cached dataset data to force re-fetch on next request.
    
    Args:
        experiment_id: Experiment ID
        dataset_name: Dataset name
        
    Returns:
        Deletion confirmation
    """
    try:
        db = DSTDatabase()
        dataset_id = f"{experiment_id}:{dataset_name}"
        
        result = db.datasets.delete_one({"id": dataset_id})
        
        if result.deleted_count > 0:
            logger.info(f"Cleared dataset: {dataset_id}")
            return {
                "status": "success",
                "message": f"Dataset '{dataset_name}' cleared successfully"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset '{dataset_name}' not found"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to clear dataset: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear dataset: {str(e)}"
        )


@router.delete("/datasets")
async def clear_all_datasets():
    """
    Clear all cached dataset data to force re-fetch.
    
    Returns:
        Deletion confirmation
    """
    try:
        db = DSTDatabase()
        result = db.datasets.delete_many({})
        
        logger.info(f"Cleared {result.deleted_count} datasets")
        
        return {
            "status": "success",
            "message": f"Cleared {result.deleted_count} datasets successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to clear datasets: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear datasets: {str(e)}"
        )


@router.post("/experiments/{experiment_id}/reprocess")
async def reprocess_experiment(experiment_id: str, request: Request):
    """
    Reprocess a single experiment - fetch datasets and regenerate panels.
    
    This will:
    1. Get experiment config from database
    2. Fetch all datasets
    3. Transform and store all panels
    
    Args:
        experiment_id: Experiment ID to reprocess
        
    Returns:
        Reprocessing results
    """
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
                "panels_count": len(experiment.panels)
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to reprocess experiment '{experiment_id}'"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reprocess experiment: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reprocess experiment: {str(e)}"
        )
