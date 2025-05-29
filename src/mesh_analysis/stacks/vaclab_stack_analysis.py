# Python Imports
import logging
import pandas as pd
from pathlib import Path
from typing import List

# Project Imports
from concurrent.futures import ProcessPoolExecutor, as_completed
from result import Ok, Err, Result
from src.mesh_analysis.readers.builders.victoria_reader_builder import VictoriaReaderBuilder
from src.mesh_analysis.readers.tracers.waku_tracer import WakuTracer
from src.mesh_analysis.readers.victoria_reader import VictoriaReader
from src.mesh_analysis.stacks.stack_analysis import StackAnalysis

logger = logging.getLogger(__name__)


# Class in charge of obtaining Dataframes
# As it is Vaclab, we know it uses Victoria
class VaclabStackAnalysis(StackAnalysis):
    def __init__(self, reader_builder: VictoriaReaderBuilder, **kwargs):
        super().__init__(reader_builder, **kwargs)

    def get_node_logs(self, n_jobs: int, **kwargs):
        dfs = []

        # TODO check nº of nodes match with given in kwargs
        num_nodes = self._get_number_nodes(self._kwargs['container_name'])

        for stateful_set_name, num_nodes_in_stateful_set in zip(self._kwargs['stateful_sets'], self._kwargs['nodes_per_statefulset']):
            with ProcessPoolExecutor(n_jobs) as executor:
                futures = {
                    executor.submit(self._read_logs_for_single_node, stateful_set_name, node_index):
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

    def _read_logs_for_single_node(self, statefulset_name: str, node_index: int) -> pd.DataFrame:
        reader = self._reader_builder.build(statefulset_name, node_index)
        data = reader.read_logs()

        return data

    def _get_number_nodes(self, container_name: str) -> List[int]:
        waku_tracer = WakuTracer(msg_field='_msg')
        waku_tracer.with_received_group_pattern()
        waku_tracer.with_sent_pattern_group()

        num_nodes_per_stateful_set = []

        for stateful_set in self._kwargs['stateful_sets']:
            victoria_config_query = {"url": self._kwargs['url'],
                                     "headers": {"Content-Type": "application/json"},
                                     "params": {
                                         "query": f"kubernetes.container_name:{container_name} AND kubernetes.pod_name:{stateful_set} AND _time:[{self._kwargs['start_time']}, {self._kwargs['end_time']}] | uniq by (kubernetes.pod_name)"}
                                     }
            reader = VictoriaReader(waku_tracer, victoria_config_query)
            result = reader.multi_query_info()
            if result.is_ok():
                num_nodes_per_stateful_set.append(len(list(result.ok_value)))
            else:
                logger.error(result.err_value)
                exit(1)

        logger.info(f'Found {num_nodes_per_stateful_set} nodes')

        return num_nodes_per_stateful_set

    def dump_node_logs(self, identifiers: List[str], dump_analysis_dir: str) -> None:
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(self._get_affected_node_log, identifier, dump_analysis_dir): identifier for identifier in
                       identifiers}

            for future in as_completed(futures):
                try:
                    result = future.result()
                    match result:
                        case Ok(log_path):
                            logger.info(f'{log_path} dumped')
                        case Err(_):
                            logger.warning(result.err_value)
                except Exception as e:
                    logger.error(f'Error retrieving logs for node {futures[future]}: {e}')

    def _get_affected_node_pod(self, data_file: str) -> Result[str, str]:
        peer_id = data_file.split('.')[0]
        victoria_config = {"url": self._kwargs['url'],
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes.container_name:waku AND 'my_peer_id=16U*{peer_id}' AND _time:[{self._kwargs['start_time']}, {self._kwargs['end_time']}] | limit 1"}}


        reader = VictoriaReader(None, victoria_config, ['kubernetes.pod_name'])
        result = reader.single_query_info()

        if result.is_ok():
            pod_name = result.unwrap()['kubernetes.pod_name']
            logger.debug(f'Pod name for peer id {peer_id} is {pod_name}')
            return Ok(pod_name)

        return Err(f'Unable to obtain pod name from {peer_id}')

    def _get_affected_node_log(self, identifier: str, dump_analysis_dir: str) -> Result[Path, str]:
        result = self._get_affected_node_pod(identifier)
        if result.is_err():
            return Err(result.err_value)

        victoria_config = {"url": self._kwargs['url'],
                           "headers": {"Content-Type": "application/json"},
                           "params": [{
                               "query": f"kubernetes.pod_name:{result.ok_value} AND _time:[{self._kwargs['start_time']}, {self._kwargs['end_time']}] | sort by (_time)"}]}

        waku_tracer = WakuTracer()
        waku_tracer.with_wildcard_pattern()
        reader = VictoriaReader(waku_tracer, victoria_config)
        pod_log = reader.read_logs()

        log_lines = [inner_list[0] for inner_list in pod_log[0]]
        log_name_path = Path(dump_analysis_dir) / f"{identifier.split('.')[0]}.log"
        with open(log_name_path, 'w') as file:
            for element in log_lines:
                file.write(f"{element}\n")

        return Ok(log_name_path)
