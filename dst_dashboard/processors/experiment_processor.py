"""Experiment processor - processes complete experiments with datasets and panels."""
import logging
import uuid
from typing import Dict, List, Any, Optional

from dst_dashboard.config.data_structures import (
    ExperimentConfig,
    DatasetConfig,
    DashboardFullConfig
)
from dst_dashboard.storage.db import DSTDatabase
from dst_dashboard.processors.panel_processor import PanelProcessor

logger = logging.getLogger(__name__)


class ExperimentProcessor(PanelProcessor):
    """
    Experiment processor - top-level processor.
    """

    def __init__(self, config: DashboardFullConfig, db: DSTDatabase):
        """
        Initialize experiment processor.
        
        Args:
            config: Dashboard configuration
            db: Database instance
        """
        super().__init__(config, db)

    def _ensure_experiment_id(self, experiment: ExperimentConfig) -> str:
        """
        Ensure experiment has a valid ID, generate UUID if missing.
        
        Args:
            experiment: Experiment configuration
            
        Returns:
            Experiment ID (existing or newly generated)
        """
        if not experiment.id or experiment.id.strip() == "":
            # Generate UUID for experiment
            generated_id = str(uuid.uuid4())
            logger.info(f"Generated UUID for experiment '{experiment.title}': {generated_id}")
            experiment.id = generated_id
        
        return experiment.id

    def process_dataset(
        self, 
        experiment_id: str, 
        dataset_config: DatasetConfig
    ) -> bool:
        """
        Process a single dataset - fetch and store if needed.
        
        Args:
            experiment_id: Experiment ID
            dataset_config: Dataset configuration
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Processing dataset: {dataset_config.name}")
        
        # Check if dataset already exists
        existing_data = self.db.get_dataset(experiment_id, dataset_config.name)
        
        # Determine if we need to fetch data
        should_fetch = existing_data is None
        
        if not should_fetch:
            logger.info(
                f"Dataset '{dataset_config.name}' already exists with {len(existing_data)} rows, skipping fetch"
            )
            return True
        
        # Fetch and store dataset
        try:
            logger.info(f"Fetching dataset '{dataset_config.name}' from {dataset_config.datasource}")
            data = self.fetch_dataset(experiment_id, dataset_config)
            
            if data:
                self.db.store_dataset(experiment_id, dataset_config.name, data)
                logger.info(f"Stored {len(data)} rows for dataset '{dataset_config.name}'")
                return True
            else:
                logger.warning(f"No data fetched for dataset '{dataset_config.name}'")
                # Store empty dataset to mark it as attempted
                self.db.store_dataset(experiment_id, dataset_config.name, [])
                return False
                
        except Exception as e:
            logger.error(f"Failed to fetch dataset '{dataset_config.name}': {e}")
            # Store empty dataset to mark it as processed but failed
            self.db.store_dataset(experiment_id, dataset_config.name, [])
            return False

    def process_experiment_datasets(
        self, 
        experiment: ExperimentConfig,
        max_workers: int = 1  # Sequential to avoid SQLite threading issues
    ) -> int:
        """
        Process all datasets for an experiment sequentially.
        
        Args:
            experiment: Experiment configuration
            max_workers: Number of workers (always 1 for sequential processing)
            
        Returns:
            Number of successfully processed datasets
        """
        if not experiment.datasets:
            return 0
        
        # Process datasets sequentially to avoid SQLite threading issues
        success_count = 0
        for dataset_config in experiment.datasets:
            if self.process_dataset(experiment.id, dataset_config):
                success_count += 1
        
        return success_count

    def process_experiment(self, experiment: ExperimentConfig) -> str:
        """
        Process a complete experiment - store experiment, fetch datasets, store panels.
        
        Args:
            experiment: Experiment configuration
            
        Returns:
            Experiment ID
        """
        # Ensure experiment has an ID (generate UUID if missing)
        experiment_id = self._ensure_experiment_id(experiment)
        
        logger.info(f"Processing experiment: {experiment_id} - {experiment.title}")
        
        # 1. Store experiment in database
        experiment_dict = experiment.model_dump()
        existing_exp = self.db.get_experiment(experiment_id)
        
        if existing_exp:
            logger.info(f"Experiment '{experiment_id}' already exists in database, updating...")
        else:
            logger.info(f"Storing new experiment '{experiment_id}' in database")
        
        self.db.store_experiment(experiment_dict)
        
        # 2. Process datasets (datasets depend on datasources)
        dataset_count = self.process_experiment_datasets(experiment)
        logger.info(f"Processed {dataset_count}/{len(experiment.datasets)} datasets for experiment '{experiment_id}'")
        
        # 3. Process panels (panels depend on datasets)
        panel_count = self.process_experiment_panels(experiment)
        logger.info(f"Processed {panel_count}/{len(experiment.panels)} panels for experiment '{experiment_id}'")
        
        return experiment_id

    def process_all_experiments(self) -> Dict[str, Any]:
        """
        Process all experiments from configuration.
        
        Returns:
            Summary dictionary with processing results
        """
        results = {
            "total_experiments": len(self.config.experiments),
            "processed_experiments": [],
            "failed_experiments": []
        }
        
        for experiment in self.config.experiments:
            try:
                experiment_id = self.process_experiment(experiment)
                results["processed_experiments"].append(experiment_id)
            except Exception as e:
                logger.error(f"Failed to process experiment '{experiment.title}': {e}", exc_info=True)
                results["failed_experiments"].append({
                    "title": experiment.title,
                    "error": str(e)
                })
        
        return results
