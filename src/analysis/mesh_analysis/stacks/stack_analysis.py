# Python Imports
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List

import pandas as pd
from pydantic import NonNegativeInt

# Project Imports
from src.analysis.mesh_analysis.readers.builders.victoria_reader_builder import (
    VictoriaReaderBuilder,
)


class StackAnalysis(ABC):

    def __init__(self, reader_builder: VictoriaReaderBuilder, **kwargs):
        self._reader_builder = reader_builder
        self._kwargs = kwargs

    @abstractmethod
    def get_all_node_dataframes(
        self, stateful_sets: List[str], nodes_per_stateful_set: List[NonNegativeInt], n_jobs: int
    ) -> List[Dict[str, List[pd.DataFrame]]]:
        pass

    @abstractmethod
    def dump_node_logs(self, n_jobs: int, identifiers: List[str], dump_path: Path):
        pass
