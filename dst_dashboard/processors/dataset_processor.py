"""Dataset processor - fetches data using 10ksim classes.

Skeleton implementation.
"""
import logging

logger = logging.getLogger(__name__)


class DatasetProcessor:
    """Fetches datasets using DataPuller or Scrapper."""

    def __init__(self, experiment_config, datasources):
        self.experiment_config = experiment_config
        self.datasources = datasources

    def fetch_dataset(self, dataset_config):
        """
        TODO: 
        - Use DataPuller for VictoriaLogs
        - Use Scrapper for Prometheus
        """
        logger.warning(f"fetch_dataset not implemented: {dataset_config.name}")
        return []
