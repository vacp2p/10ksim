"""Utility functions for API routes."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import HTTPException, Request

from dst_dashboard.processors.experiment_processor import ExperimentProcessor
from dst_dashboard.processors.panel_processor import PanelProcessor
from dst_dashboard.storage.db import DSTDatabase

logger = logging.getLogger(__name__)


def get_processor(request: Request) -> ExperimentProcessor:
    """
    Get experiment processor from app state.
    The processor needs config for datasources (DB is source of truth for experiments).
    """
    config = getattr(request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=500, detail="Config is not initialized")
    db = DSTDatabase()
    return ExperimentProcessor(config, db)


def get_panel_processor(request: Request) -> PanelProcessor:
    """
    Get panel processor from app state.
    The processor needs config for datasources.
    """
    config = getattr(request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=500, detail="Config is not initialized")
    db = DSTDatabase()
    return PanelProcessor(config, db)


def needs_reprocessing(db: DSTDatabase, experiment) -> bool:
    """
    Check if experiment needs reprocessing (missing datasets or panels).
    
    Args:
        db: Database instance
        experiment: ExperimentConfig instance
        
    Returns:
        True if reprocessing needed, False otherwise
    """
    # Check if all datasets have data
    for dataset_config in experiment.datasets:
        data = db.get_dataset(experiment.id, dataset_config.name)
        if data is None:
            return True
    
    # Check if all panels have been processed
    for panel_config in experiment.panels:
        panel_data = db.get_panel_data(experiment.id, panel_config.name)
        if panel_data is None:
            return True
    
    return False


def process_experiments(experiments, db, processor, experiment_ids_tracker=None, max_workers=4):
    """
    Process a list of experiments in parallel.
    
    Args:
        experiments: List of ExperimentConfig instances
        db: Database instance (used for reference only)
        processor: ExperimentProcessor instance (used for config reference)
        experiment_ids_tracker: Optional set to track processed experiment IDs
        max_workers: Maximum number of parallel workers (default: 4)
        
    Returns:
        Dict with processing statistics
    """
    stats = {"processed": 0, "failed": 0, "failed_list": []}
    
    def process_single_experiment(experiment):
        """Process a single experiment and return result. Creates thread-local DB connection."""
        try:
            # Create thread-local database and processor instances
            # SQLite requires connections to be created in the same thread they're used
            thread_db = DSTDatabase()
            thread_processor = ExperimentProcessor(processor.config, thread_db)
            
            # Store experiment in database
            thread_db.store_experiment(experiment.model_dump())
            
            if experiment_ids_tracker is not None:
                experiment_ids_tracker.add(experiment.id)
            
            # Check if needs reprocessing
            if needs_reprocessing(thread_db, experiment):
                logger.info(f"Processing '{experiment.id}' (missing data)")
                thread_processor.process_experiment(experiment)
            else:
                logger.info(f"Skipping '{experiment.id}' (data complete)")
            
            return {"success": True, "id": experiment.id}
            
        except Exception as e:
            logger.error(f"Failed to process '{experiment.title}': {e}", exc_info=True)
            return {
                "success": False,
                "id": experiment.id,
                "title": experiment.title,
                "error": str(e)
            }
    
    # Process experiments in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_exp = {
            executor.submit(process_single_experiment, exp): exp 
            for exp in experiments
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_exp):
            result = future.result()
            if result["success"]:
                stats["processed"] += 1
            else:
                stats["failed"] += 1
                stats["failed_list"].append({
                    "title": result["title"],
                    "error": result["error"]
                })
    
    return stats
