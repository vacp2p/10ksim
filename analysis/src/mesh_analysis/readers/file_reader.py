# Python Imports
import logging
import multiprocessing
import re
from pathlib import Path
from typing import List

from src.mesh_analysis.readers.reader import Reader

# Project Imports
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer
from src.utils import file_utils

logger = logging.getLogger(__name__)


class FileReader(Reader):

    def __init__(self, folder: Path, tracer: MessageTracer, n_jobs: int):
        self._folder_path = folder
        self._tracer = tracer
        self._n_jobs = n_jobs

    def get_dataframes(self) -> List:
        logger.info(f"Reading {self._folder_path}")
        files_result = file_utils.get_files_from_folder_path(self._folder_path, extension="*.log")

        if files_result.is_err():
            logger.error(f"Could not read {self._folder_path}")
            exit()

        parsed_logs = self._read_files(files_result.ok_value)
        logger.info(f"Tracing {self._folder_path}")

        def merge_sublists(biglist):
            transposed = list(zip(*biglist))
            merged = [[item for sublist in sublists for item in sublist] for sublists in transposed]

            return merged

        test = merge_sublists(parsed_logs)
        dfs = self._tracer.trace(test)

        return dfs

    def _read_files(self, files: List) -> List:
        with multiprocessing.Pool(processes=self._n_jobs) as pool:
            parsed_logs = pool.map(self._read_file_patterns, files)

        return parsed_logs

    def _read_file_patterns(self, file: str) -> List:
        results = [[] for p in self._tracer.patterns]

        with open(Path(self._folder_path) / file) as log_file:
            lines = log_file.readlines()

        for i, patterns in enumerate(self._tracer.patterns):
            query_results = [[] for _ in patterns]

            for line in lines:
                for j, pattern in enumerate(patterns):
                    match = re.search(pattern, line)
                    if match:
                        match_as_list = list(match.groups())
                        match_as_list.append(file)
                        query_results[j].append(match_as_list)
                        break

            results[i].extend(query_results)

        return results
