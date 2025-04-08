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

    def __init__(self, folder: Path, tracer: MessageTracer):
        self._folder_path = folder
        self._tracer = tracer

    def read(self) -> List:
        logger.info(f'Reading {self._folder_path}')
        files_result = file_utils.get_files_from_folder_path(self._folder_path)

        if files_result.is_err():
            logger.error(f'Could not read {self._folder_path}')
            exit()

        parsed_logs = self._read_files(files_result.ok_value)
        logger.info(f'Tracing {self._folder_path}')

        def merge_sublists(biglist):
            transposed = list(zip(*biglist))
            merged = [[item for sublist in sublists for item in sublist] for sublists in transposed]

            return merged

        merged_lists = merge_sublists(parsed_logs)

        dfs = self._tracer.trace(merged_lists)

        merged_list = []

        consistent_columns = ["msg_hash", "timestamp", "receiver_peer_id", "sender_peer_id", "pod-name", "kubernetes-worker"]  # Assume df1 has the desired column order

        for inner_list in dfs:
            reordered_dfs = [df[consistent_columns] for df in inner_list]
            merged_df = pd.concat(reordered_dfs, ignore_index=True)
            merged_list.append(merged_df)

        return merged_list

    def _read_files(self, files: List) -> List:
        # TODO: set this as a parameter?
        num_processes = multiprocessing.cpu_count()
        with multiprocessing.Pool(processes=2) as pool:
            parsed_logs = pool.map(self._read_file_patterns, files)

        return parsed_logs

    def _read_file_patterns(self, file: str) -> List:
        results = [
            [[] for _ in query]
            for query in self._tracer.patterns
        ]

        with open(Path(self._folder_path) / file) as log_file:
            for line in log_file:
                for i, query in enumerate(self._tracer.patterns):
                    for j, pattern in enumerate(query):
                        match = re.search(pattern, line)
                        if match:
                            match_as_list = list(match.groups())
                            match_as_list.append(None) # Pod name
                            match_as_list.append(None) # Kubernetes worker
                            results[i][j].append(match_as_list)
                            break

        return results
