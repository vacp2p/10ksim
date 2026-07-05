"""MontyDB database client for storing experiments and datasets.

Uses MontyDB (embedded MongoDB-compatible database) as cache storage.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import threading

from montydb import MontyClient, set_storage

from dst_dashboard.config.constants import Constants
from dst_dashboard.config.data_structures import DataSourceConfig


# Thread-local storage to track if storage has been configured for this thread
_storage_configured = threading.local()

# Global lock for database initialization (table creation, etc.)
_db_init_lock = threading.Lock()


class DSTDatabase:
    """Database client for DST Dashboard using MontyDB."""

    @staticmethod
    def _configure_storage(db_path: Path):
        """
        Configure MontyDB storage for the current thread.
        Thread-safe - can be called multiple times.
        
        Args:
            db_path: Path to database directory
        """
        # Check if already configured for this thread
        if getattr(_storage_configured, 'configured', False):
            return
        
        # Configure MontyDB with SQLite + WAL mode for concurrent access
        # WAL mode allows multiple readers + one writer simultaneously
        set_storage(
            str(db_path), 
            storage="sqlite",
            journal_mode="WAL",  # Write-Ahead Logging for concurrent access
            check_same_thread=False,  # Allow multi-threaded access
            use_bson=False  # Use MontyDB's built-in BSON implementation
        )
        
        # Mark as configured for this thread
        _storage_configured.configured = True

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize MontyDB client.

        Args:
            db_path: Path to database directory. Defaults to `DST_DB_PATH` env var or ~/.cache/dst_dashboard
        """
        if db_path is None:
            db_path = Path(Constants.DST_DB_PATH).expanduser()

        db_path.mkdir(parents=True, exist_ok=True)

        # Configure storage for this thread
        self._configure_storage(db_path)

        # Use lock for initial client/database creation to avoid race conditions
        with _db_init_lock:
            self.client = MontyClient(str(db_path))
            self.db = self.client.dst_dashboard

        # Collections
        self.experiments = self.db.experiments
        self.datasets = self.db.datasets
        self.panels = self.db.panels
        self.datasources = self.db.datasources

    def store_experiment(self, experiment: Dict[str, Any]) -> str:
        """Store experiment configuration.

        Args:
            experiment: Experiment config dict

        Returns:
            Experiment ID
        """
        result = self.experiments.update_one(
            {"id": experiment["id"]}, {"$set": experiment}, upsert=True
        )
        return experiment["id"]

    def get_experiment(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """Get experiment by ID.

        Args:
            experiment_id: Experiment ID

        Returns:
            Experiment dict or None
        """
        return self.experiments.find_one({"id": experiment_id}, {"_id": 0})

    def list_experiments(self) -> List[Dict[str, Any]]:
        """List all experiments.

        Returns:
            List of experiment dicts
        """
        return list(self.experiments.find({}, {"_id": 0}))

    def store_dataset(
        self, experiment_id: str, dataset_name: str, data: List[Dict[str, Any]]
    ) -> str:
        """Store dataset data.

        Args:
            experiment_id: Experiment ID
            dataset_name: Dataset name
            data: List of data rows

        Returns:
            Dataset ID
        """
        dataset_id = f"{experiment_id}:{dataset_name}"
        dataset_doc = {
            "id": dataset_id,
            "experiment_id": experiment_id,
            "name": dataset_name,
            "data": data,
            "row_count": len(data),
        }
        self.datasets.update_one({"id": dataset_id}, {"$set": dataset_doc}, upsert=True)
        return dataset_id

    def get_dataset(
        self, experiment_id: str, dataset_name: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Get dataset data.

        Args:
            experiment_id: Experiment ID
            dataset_name: Dataset name

        Returns:
            List of data rows or None
        """
        dataset_id = f"{experiment_id}:{dataset_name}"
        doc = self.datasets.find_one({"id": dataset_id}, {"_id": 0})
        return doc["data"] if doc else None

    def list_panels(self, experiment_id: str) -> List[Dict[str, Any]]:
        """List stored panel metadata for an experiment.

        Args:
            experiment_id: Experiment ID

        Returns:
            List of panel metadata dicts
        """
        docs = list(self.panels.find({"experiment_id": experiment_id}, {"_id": 0}))
        return [
            {
                "id": doc["id"],
                "experiment_id": doc["experiment_id"],
                "name": doc["name"],
            }
            for doc in docs
        ]

    def store_panel_data(
        self, experiment_id: str, panel_name: str, data: Dict[str, Any]
    ) -> str:
        """Store transformed panel data.

        Args:
            experiment_id: Experiment ID
            panel_name: Panel name
            data: Transformed data for frontend

        Returns:
            Panel data ID
        """
        panel_id = f"{experiment_id}:{panel_name}"
        panel_doc = {
            "id": panel_id,
            "experiment_id": experiment_id,
            "name": panel_name,
            "data": data,
        }
        self.panels.update_one({"id": panel_id}, {"$set": panel_doc}, upsert=True)
        return panel_id

    def get_panel_data(
        self, experiment_id: str, panel_name: str
    ) -> Optional[Dict[str, Any]]:
        """Get transformed panel data.

        Args:
            experiment_id: Experiment ID
            panel_name: Panel name

        Returns:
            Panel data dict or None
        """
        panel_id = f"{experiment_id}:{panel_name}"
        doc = self.panels.find_one({"id": panel_id}, {"_id": 0})
        return doc["data"] if doc else None
    
    def insert_datasource(self, datasource: DataSourceConfig) -> DataSourceConfig:
        """Store datasource configuration.

        Args:
            datasource: Datasource config

        Returns:
            Datasource
        """
        data = datasource.model_dump()
        self.datasources.update_one(
            {"name": data["name"]}, {"$set": data}, upsert=True
        )
        return datasource
    
    def insert_datasource_list(self, datasources: List[DataSourceConfig]) -> List[DataSourceConfig]:
        """Store a list of datasource configurations.

        Args:
            datasources: List of datasource configs

        Returns:
            List of Datasources
        """
        for datasource in datasources:
            self.insert_datasource(datasource)
        return datasources
    
    def dataset_exists(self, experiment_id: str, dataset_name: str) -> bool:
        """Check if dataset exists in database.

        Args:
            experiment_id: Experiment ID
            dataset_name: Dataset name

        Returns:
            True if dataset exists, False otherwise
        """
        dataset_id = f"{experiment_id}:{dataset_name}"
        doc = self.datasets.find_one({"id": dataset_id}, {"_id": 0})
        return doc is not None
    
    def get_dataset_metadata(self, experiment_id: str, dataset_name: str) -> Optional[Dict[str, Any]]:
        """Get dataset metadata without data rows.

        Args:
            experiment_id: Experiment ID
            dataset_name: Dataset name

        Returns:
            Dataset metadata dict or None
        """
        dataset_id = f"{experiment_id}:{dataset_name}"
        doc = self.datasets.find_one(
            {"id": dataset_id}, 
            {"_id": 0, "id": 1, "experiment_id": 1, "name": 1, "row_count": 1}
        )
        return doc

    def delete_experiment(self, experiment_id: str) -> bool:
        """Delete an experiment and all its associated data.

        Args:
            experiment_id: Experiment ID

        Returns:
            True if deleted, False if not found
        """
        # Delete experiment
        result = self.experiments.delete_one({"id": experiment_id})
        
        # Delete all datasets for this experiment
        self.datasets.delete_many({"experiment_id": experiment_id})
        
        # Delete all panels for this experiment
        self.panels.delete_many({"experiment_id": experiment_id})
        
        return result.deleted_count > 0

    def delete_dataset(self, experiment_id: str, dataset_name: str) -> bool:
        """Delete a dataset.

        Args:
            experiment_id: Experiment ID
            dataset_name: Dataset name

        Returns:
            True if deleted, False if not found
        """
        dataset_id = f"{experiment_id}:{dataset_name}"
        result = self.datasets.delete_one({"id": dataset_id})
        return result.deleted_count > 0

    def delete_panel(self, experiment_id: str, panel_name: str) -> bool:
        """Delete a panel.

        Args:
            experiment_id: Experiment ID
            panel_name: Panel name

        Returns:
            True if deleted, False if not found
        """
        panel_id = f"{experiment_id}:{panel_name}"
        result = self.panels.delete_one({"id": panel_id})
        return result.deleted_count > 0
