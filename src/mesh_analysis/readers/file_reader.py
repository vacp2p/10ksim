# Python Imports
import re
import logging
import multiprocessing
import pandas as pd
from typing import List
from pathlib import Path

# Project Imports
from src.utils import file_utils
from src.mesh_analysis.readers.reader import Reader
from src.mesh_analysis.tracers.message_tracer import MessageTracer


logger = logging.getLogger(__name__)


class FileReader(Reader):

    def __init__(self, folder: str, tracer: MessageTracer):
        self._folder = folder
        self._tracer = tracer

    def read(self) -> pd.DataFrame:
        logger.info(f'Reading {self._folder}')
        files_result = file_utils.get_files_from_folder_path(Path(self._folder))

        if files_result.is_err():
            logger.error(f'Could not read {self._folder}')
            exit()

        parsed_logs = self._read_files(files_result.ok_value)
        logger.info(f'Tracing {self._folder}')
        df = self._tracer.trace(parsed_logs)

        return df

    def _read_files(self, files: List) -> List:
        # TODO: set this as a parameter?
        num_processes = multiprocessing.cpu_count()
        with multiprocessing.Pool(processes=4) as pool:
            parsed_logs = pool.map(self._read_file_patterns, files)

        return parsed_logs

    def _read_file_patterns(self, file: str) -> List:
        results = [[] for p in self._tracer.patterns]

        with open(Path(self._folder + file)) as log_file:
            for line in log_file:
                for i, pattern in enumerate(self._tracer.patterns):
                    match = re.search(pattern, line)
                    if match:
                        results[i].append(match.groups())
                        break

        return results
