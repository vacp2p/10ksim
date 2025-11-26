# Python Imports
import logging
import pandas as pd
from pathlib import Path
from typing import List

# Project Imports
from concurrent.futures import ProcessPoolExecutor, as_completed
from result import Ok, Err, Result
from src.mesh_analysis.readers.builders.victoria_reader_builder import VictoriaReaderBuilder
from src.mesh_analysis.stacks.stack_analysis import StackAnalysis
from src.utils import path_utils

logger = logging.getLogger(__name__)


class VaclabStackAnalysis(StackAnalysis):
    def __init__(self, reader_builder: VictoriaReaderBuilder, **kwargs):
        super().__init__(reader_builder, **kwargs)

    def get_all_node_dataframes(self, n_jobs: int):
        dfs = []

        for stateful_set_name, num_nodes_in_stateful_set in zip(self._kwargs['stateful_sets'], self._kwargs['nodes_per_statefulset']):
            with ProcessPoolExecutor(n_jobs) as executor:
                futures = {
                    executor.submit(self._extract_dataframe_single_node, stateful_set_name, node_index):
                        node_index for node_index in range(num_nodes_in_stateful_set)}

                for i, future in enumerate(as_completed(futures)):
                    i = i + 1
                    try:
                        df = future.result()
                        dfs.append(df)
                        if i % 50 == 0 or i == num_nodes_in_stateful_set:
                            logger.info(
                                f'Processed {i}/{num_nodes_in_stateful_set} nodes in stateful set <{stateful_set_name}>')

                    except Exception as e:
                        logger.error(f'Error retrieving logs for node {futures[future]}: {e}')

        return dfs

    def _extract_dataframe_single_node(self, statefulset_name: str, node_index: int) -> List[pd.DataFrame] :
        reader = self._reader_builder.build_with_queries(statefulset_name, node_index)
        data = reader.get_dataframes()

        return data

    def _dump_logs_for_single_node(self, node: str, dump_path: Path) -> Result[Path, None]:
        reader = self._reader_builder.build_with_single_query(node)
        data = reader.make_queries()

        log_name_path = dump_path / f"{node}.log"
        result = path_utils.prepare_path_for_file(log_name_path)
        if result.is_ok():
            with open(log_name_path, 'w') as file:
                for element in data[0][0]: # We will always have 1 pattern group with 1 pattern
                    file.write(f"{element}\n")

            return Ok(log_name_path)
        else:
            return Err(None)

    def get_number_nodes(self) -> List[int]:
        num_nodes_per_stateful_set = []

        for stateful_set_prefix in self._kwargs['stateful_sets']:
            reader = self._reader_builder.build_with_single_query(stateful_set_prefix, uniq_by='|uniq by (kubernetes.pod_name)')
            result = reader.multiline_query_info()
            if result.is_ok():
                num_nodes_per_stateful_set.append(len(list(result.ok_value)))
            else:
                logger.error(result.err_value)
                exit(1)

        return num_nodes_per_stateful_set

    def dump_node_logs(self, n_jobs: int, identifiers: List[str], dump_path: Path) -> None:
        with ProcessPoolExecutor(n_jobs) as executor:
            futures_map = {
                executor.submit(
                    self._dump_logs_for_single_node, identifier, dump_path
                ): identifier for identifier in identifiers
            }

            for future in as_completed(futures_map):
                identifier = futures_map[future]
                try:
                    result = future.result()
                    match result:
                        case Ok(log_path):
                            logger.info(f'Log for {identifier} dumped successfully: {log_path}')
                        case Err(_):
                            logger.warning(f'Failed to dump logs for {identifier}: {result.err_value}')
                except Exception as e:
                    logger.error(f'Error retrieving logs for node {identifier}: {e}')

    def get_pod_logs(self, identifier: str, container_name: str) -> List[str]:
        reader = self._reader_builder.build_with_pod_identifier(identifier, container_name)
        data = reader.make_queries()

        return data
