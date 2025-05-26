# Python Imports
import logging
import pandas as pd
from typing import List

# Project Imports
from concurrent.futures import ProcessPoolExecutor, as_completed
from src.mesh_analysis.readers.tracers.waku_tracer import WakuTracer
from src.mesh_analysis.readers.victoria_reader import VictoriaReader
from src.mesh_analysis.stacks.stack_analysis import StackAnalysis

logger = logging.getLogger(__name__)

# Class in charge of obtaining Dataframes
# As it is Vaclab, we know it uses Victoria
class VaclabStackAnalysis(StackAnalysis):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def get_reliability_data(self, n_jobs:int, **kwargs):
        dfs = []
        num_nodes = self._get_number_nodes()

        for stateful_set_name, num_nodes_in_stateful_set in zip(self._kwargs['stateful_sets'], num_nodes):
            with ProcessPoolExecutor(n_jobs) as executor:
                futures = {executor.submit(self._read_logs_for_single_node, stateful_set_name, node_index):
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

    def dump_logs(self):
        pass

    def _read_logs_for_single_node(self, stateful_set_name: str, node_index: int) -> List[pd.DataFrame]:
        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()

        reader = VictoriaReader(waku_tracer)
        victoria_config_query =  {"url": self._kwargs['url'],
                    "headers": {"Content-Type": "application/json"},
                    "params": [
                        {
                            "query": f"kubernetes.container_name:waku AND kubernetes.pod_name:{stateful_set_name}-{node_index} AND (received relay message OR  handling lightpush request) AND _time:[{self._kwargs['start_time']}, {self._kwargs['end_time']}]"},
                        {
                            "query": f"kubernetes.container_name:waku AND kubernetes.pod_name:{stateful_set_name}-{node_index} AND sent relay message AND _time:[{self._kwargs['start_time']}, {self._kwargs['end_time']}]"}]
                    }
        data = reader.read_logs(victoria_config_query)

        logger.debug(f'{stateful_set_name}-{node_index} analyzed')

        return data

    def _get_number_nodes(self) -> List[int]:
        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()
        reader = VictoriaReader(waku_tracer)

        num_nodes_per_stateful_set = []

        for stateful_set in self._kwargs['stateful_sets']:
            victoria_config_query = {"url": self._kwargs['url'],
                               "headers": {"Content-Type": "application/json"},
                               "params": {
                                   "query": f"kubernetes.container_name:container-0 AND kubernetes.pod_name:{stateful_set} AND _time:[{self._kwargs['start_time']}, {self._kwargs['end_time']}] | uniq by (kubernetes.pod_name)"}
                               }

            result = reader.multi_query_info(victoria_config_query)
            if result.is_ok():
                num_nodes_per_stateful_set.append(len(list(result.ok_value)))
            else:
                logger.error(result.err_value)
                exit(1)

        return num_nodes_per_stateful_set