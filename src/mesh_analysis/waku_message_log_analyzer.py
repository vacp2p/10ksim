# Python Imports
import logging
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict
from result import Ok, Err, Result

# Project Imports
from src.mesh_analysis.readers.file_reader import FileReader
from src.mesh_analysis.readers.victoria_reader import VictoriaReader
from src.mesh_analysis.tracers.waku_tracer import WakuTracer
from src.utils import file_utils, log_utils

logger = logging.getLogger(__name__)


class WakuMessageLogAnalyzer:
    def __init__(self, timestamp_to_analyze: str = None, dump_analysis_dir: str = None,
                 local_folder_to_analyze: str = None):
        self._validate_analysis_location(timestamp_to_analyze, local_folder_to_analyze)
        self._set_up_paths(dump_analysis_dir, local_folder_to_analyze)
        self._timestamp = timestamp_to_analyze
        # self._set_victoria_config()

    def _validate_analysis_location(self, timestamp_to_analyze: str, local_folder_to_analyze: str):
        if timestamp_to_analyze is None and local_folder_to_analyze is None:
            logger.error('No timestamp or local folder specified')
            exit(1)

    def _set_up_paths(self, dump_analysis_dir: str, local_folder_to_analyze: str):
        self._folder_path = Path(dump_analysis_dir) if dump_analysis_dir else Path(local_folder_to_analyze)

    def _get_victoria_config_parallel(self, pod_name: str) -> Dict:
        return {"url": "https://vmselect.riff.cc/select/logsql/query",
                "headers": {"Content-Type": "application/json"},
                "params": [
                    {
                        "query": f"kubernetes_container_name:waku AND kubernetes_pod_name:{pod_name} AND received relay message AND _time:{self._timestamp}"},
                    {
                        "query": f"kubernetes_container_name:waku AND kubernetes_pod_name:{pod_name} AND sent relay message AND _time:{self._timestamp}"}]
                }

    def _get_victoria_config_single(self) -> Dict:
        return {"url": "https://vmselect.riff.cc/select/logsql/query",
                "headers": {"Content-Type": "application/json"},
                "params": [
                    {
                        "query": f"kubernetes_container_name:waku AND received relay message AND _time:{self._timestamp}"},
                    {
                        "query": f"kubernetes_container_name:waku AND sent relay message AND _time:{self._timestamp}"}]
                }

    def _get_affected_node_pod(self, data_file: str) -> Result[str, str]:
        peer_id = data_file.split('.')[0]
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes_container_name:waku AND 'my_peer_id=16U*{peer_id}' AND _time:{self._timestamp} | limit 1"}}

        reader = VictoriaReader(victoria_config, None)
        result = reader.single_query_info()

        if result.is_ok():
            pod_name = result.unwrap()['kubernetes_pod_name']
            logger.debug(f'Pod name for peer id {peer_id} is {pod_name}')
            return Ok(pod_name)

        return Err(f'Unable to obtain pod name from {peer_id}')

    def _get_affected_node_log(self, data_file: str) -> Result[Path, str]:
        result = self._get_affected_node_pod(data_file)
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": [{
                               "query": f"kubernetes_pod_name:{result.ok_value} AND _time:{self._timestamp} | sort by (_time)"}]}

        waku_tracer = WakuTracer()
        waku_tracer.with_wildcard_pattern()
        reader = VictoriaReader(victoria_config, waku_tracer)
        pod_log = reader.read()

        log_lines = [inner_list[0] for inner_list in pod_log[0]]
        log_name_path = self._folder_path / f'{pod_log[0][0][1]}.log'
        with open(log_name_path, 'w') as file:
            for element in log_lines:
                file.write(f"{element}\n")

        return Ok(log_name_path)

    def _dump_information(self, data_files: List[str]):
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(self._get_affected_node_log, data_file): data_file for data_file in data_files}

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

    def _has_issues_in_local(self) -> bool:
        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()
        reader = FileReader(self._folder_path, waku_tracer)
        dfs = reader.read()

        has_issues = waku_tracer.has_message_reliability_issues('msg_hash', 'receiver_peer_id', dfs[0], dfs[1],
                                                                self._folder_path)

        return has_issues

    def _has_issues_in_cluster_single(self) -> bool:
        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()
        reader = VictoriaReader(self._get_victoria_config_single(), waku_tracer)
        dfs = reader.read()

        has_issues = waku_tracer.has_message_reliability_issues('msg_hash', 'receiver_peer_id', dfs[0], dfs[1],
                                                                self._folder_path)

        return has_issues

    def _read_logs_for_node(self, node_index, victoria_config_func) -> List[pd.DataFrame]:
        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()

        config = victoria_config_func(node_index)
        reader = VictoriaReader(config, waku_tracer)
        data = reader.read()
        logger.debug(f'Nodes-{node_index} analyzed')

        return data

    def _read_logs_concurrently(self, n_nodes: int) -> List[pd.DataFrame]:
        dfs = []
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(self._read_logs_for_node, i, self._get_victoria_config_parallel): i
                       for i in range(n_nodes)}

            i = 0
            for future in as_completed(futures):
                try:
                    df = future.result()
                    dfs.append(df)
                    i = i + 1
                    if i % 50 == 0:
                        logger.info(f'Processed {i}/{n_nodes} nodes')

                except Exception as e:
                    logger.error(f'Error retrieving logs for node {futures[future]}: {e}')

        return dfs

    def _has_issues_in_cluster_parallel(self, n_nodes: int) -> bool:
        dfs = self._read_logs_concurrently(n_nodes)
        dfs = self._merge_dfs(dfs)

        result = self._dump_dfs(dfs)
        if result.is_err():
            logger.warning(f'Issue dumping message summary. {result.err_value}')
            exit(1)

        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()
        has_issues = waku_tracer.has_message_reliability_issues('msg_hash', 'receiver_peer_id', dfs[0], dfs[1],
                                                                self._folder_path)

        return has_issues

    def _merge_dfs(self, dfs: List[pd.DataFrame]) -> List[pd.DataFrame]:
        dfs = list(zip(*dfs))
        dfs = [pd.concat(tup, axis=0) for tup in dfs]

        return dfs

    def _dump_dfs(self, dfs: List[pd.DataFrame]) -> Result:
        result = file_utils.dump_df_as_csv(dfs[0], self._folder_path / 'summary' / 'received.csv')
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        result = file_utils.dump_df_as_csv(dfs[1], self._folder_path / 'summary' / 'sent.csv')
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        return Ok(None)

    def _get_number_nodes(self) -> int:
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes_container_name:waku AND _time:{self._timestamp} AND kubernetes_pod_name:nodes | uniq by (kubernetes_pod_name)"}
                           }

        reader = VictoriaReader(victoria_config, None)
        result = reader.multi_query_info()
        n_nodes = len(list(result.ok_value))

        return n_nodes

    def analyze_message_logs(self, parallel=False):
        if self._timestamp is not None:
            logger.info('Analyzing from server')
            n_nodes = self._get_number_nodes()
            logger.info(f'Detected {n_nodes} pods')
            has_issues = self._has_issues_in_cluster_parallel(
                n_nodes) if parallel else self._has_issues_in_cluster_single()
            if has_issues:
                match file_utils.get_files_from_folder_path(Path(self._folder_path), extension="csv"):
                    case Ok(data_files_names):
                        self._dump_information(data_files_names)
                    case Err(error):
                        logger.error(error)
        else:
            logger.info('Analyzing from local')
            _ = self._has_issues_in_local()

    def analyze_message_timestamps(self, time_difference_threshold: int):
        """
        Note that this function assumes that analyze_message_logs has been called, since timestamps will be checked
        from logs.
        """
        file_logs = file_utils.get_files_from_folder_path(self._folder_path, '*.log')
        if file_logs.is_err():
            logger.error(file_logs.err_value)
            return

        logger.info(f'Analyzing timestamps from {len(file_logs.ok_value)} files')
        for file in file_logs.ok_value:
            logger.debug(f'Analyzing timestamps for {file}')
            time_jumps = log_utils.find_time_jumps(self._folder_path / file, time_difference_threshold)

            for jump in time_jumps:
                logger.info(f'{jump[0]} to {jump[1]} -> {jump[2]}')
