import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List

import pandas as pd

from src.mesh_analysis.readers.victoria_reader import VictoriaReader
from src.mesh_analysis.tracers.statusgo_tracer import StatusgoTracer

logger = logging.getLogger(__name__)


class StatusgoMessageLogAnalyzer:
    def __init__(self, stateful_sets: List[str], timestamp_to_analyze: str = None,
                 dump_analysis_dir: str = None, local_folder_to_analyze: str = None):
        self._stateful_sets = stateful_sets
        self._timestamp = timestamp_to_analyze
        self._num_nodes: List[int] = []

    def _get_victoria_config_parallel(self, stateful_set_name: str, node_index: int) -> Dict:
        return {"url": "https://vmselect.riff.cc/select/logsql/query",
                "headers": {"Content-Type": "application/json"},
                "params": [
                    {
                        "query": f"Test message* AND kubernetes.pod_name:{stateful_set_name}-{node_index} AND kubernetes.container_name:status-subscriber AND _time:{self._timestamp}"}]
                }

    def _get_number_nodes(self) -> List[int]:
        num_nodes_per_stateful_set = []

        for stateful_set in self._stateful_sets:
            victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                               "headers": {"Content-Type": "application/json"},
                               "params": {
                                   "query": f"kubernetes.container_name:status-subscriber AND kubernetes.pod_name:{stateful_set} AND _time:{self._timestamp} | uniq by (kubernetes.pod_name)"}
                               }

            reader = VictoriaReader(victoria_config, None)
            result = reader.multi_query_info()
            if result.is_ok():
                num_nodes_per_stateful_set.append(len(list(result.ok_value)))
            else:
                logger.error(result.err_value)
                exit(1)

        return num_nodes_per_stateful_set

    def _read_logs_for_node(self, stateful_set_name: str, node_index: int, victoria_config_func) -> List[pd.DataFrame]:
        statusgo_tracer = StatusgoTracer()
        statusgo_tracer.with_message_pattern()

        config = victoria_config_func(stateful_set_name, node_index)
        reader = VictoriaReader(config, statusgo_tracer)
        data = reader.read()
        logger.debug(f'{stateful_set_name}-{node_index} analyzed')

        return data

    def _read_logs_concurrently(self) -> List[pd.DataFrame]:
        dfs = []
        for stateful_set_name, num_nodes_in_stateful_set in zip(self._stateful_sets, self._num_nodes):
            with ProcessPoolExecutor(8) as executor:
                futures = {executor.submit(self._read_logs_for_node, stateful_set_name, node_index,
                                           self._get_victoria_config_parallel):
                               node_index for node_index in range(num_nodes_in_stateful_set)}

                for i, future in enumerate(as_completed(futures)):
                    i = i + 1
                    try:
                        df = future.result()
                        dfs.append(df)
                        if i % 50 == 0 or i == num_nodes_in_stateful_set:
                            logger.info(f'Processed {i}/{num_nodes_in_stateful_set} nodes in stateful set <{stateful_set_name}>')

                    except Exception as e:
                        logger.error(f'Error retrieving logs for node {futures[future]}: {e}')

        return dfs

    def analyze_subscription_performance(self):
        logger.info('Analyzing from server')
        self._num_nodes = self._get_number_nodes()
        logger.info(f'Detected {self._num_nodes} pods in {self._stateful_sets}')

