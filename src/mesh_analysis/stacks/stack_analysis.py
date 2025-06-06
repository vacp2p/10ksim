# Python Imports
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

# Project Imports
from src.mesh_analysis.readers.builders.victoria_reader_builder import VictoriaReaderBuilder



class StackAnalysis(ABC):

    def __init__(self, reader_builder: VictoriaReaderBuilder, **kwargs):
        self._reader_builder = reader_builder
        self._kwargs = kwargs

    @abstractmethod
    def get_all_node_dataframes(self, n_jobs: int):
        pass

    @abstractmethod
    def dump_node_logs(self,  n_jobs: int, identifiers: List[str], dump_path: Path):
        pass