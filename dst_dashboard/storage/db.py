"""MontyDB database client for storing experiments and datasets.

Uses MontyDB (embedded MongoDB-compatible database) as cache storage.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from montydb import MontyClient, set_storage


class DSTDatabase:
    """Database client for DST Dashboard using MontyDB."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize MontyDB client.

        Args:
            db_path: Path to database directory. Defaults to DST_DB_PATH env var or ~/.cache/dst_dashboard
        """
        if db_path is None:
            db_path_str = os.getenv("EMBEDDED_DB_PATH", str(Path.home() / ".cache" / "dst_dashboard"))
            db_path = Path(db_path_str)

        db_path.mkdir(parents=True, exist_ok=True)

        # Configure MontyDB storage
        set_storage(str(db_path), storage="sqlite")

        self.client = MontyClient(str(db_path))
        self.db = self.client.dst_dashboard

        # Collections
        self.experiments = self.db.experiments
        self.datasets = self.db.datasets
        self.panels = self.db.panels

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
