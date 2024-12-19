# Python Imports
import ast
import base64
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
from src.utils import file_utils, log_utils, path_utils, list_utils

logger = logging.getLogger(__name__)


class WakuMessageLogAnalyzer:
    def __init__(self, num_shards: int, timestamp_to_analyze: str = None, dump_analysis_dir: str = None,
                 local_folder_to_analyze: str = None):
        self._num_shards = num_shards
        self._num_nodes = None
        self._validate_analysis_location(timestamp_to_analyze, local_folder_to_analyze)
        self._set_up_paths(dump_analysis_dir, local_folder_to_analyze)
        self._timestamp = timestamp_to_analyze
        self._message_hashes = []

    def _validate_analysis_location(self, timestamp_to_analyze: str, local_folder_to_analyze: str):
        if timestamp_to_analyze is None and local_folder_to_analyze is None:
            logger.error('No timestamp or local folder specified')
            exit(1)

    def _set_up_paths(self, dump_analysis_dir: str, local_folder_to_analyze: str):
        self._dump_analysis_dir = Path(dump_analysis_dir) if dump_analysis_dir else None
        self._local_path_to_analyze = Path(local_folder_to_analyze) if local_folder_to_analyze else None
        result = path_utils.prepare_path_for_folder(self._dump_analysis_dir)
        if result.is_err():
            logger.error(result.err_value)
            exit(1)

    def _get_victoria_config_parallel(self, node_index: int, num_nodes: int, num_shards: int) -> Dict:
        shard = int(node_index // (num_nodes / num_shards))
        return {"url": "https://vmselect.riff.cc/select/logsql/query",
                "headers": {"Content-Type": "application/json"},
                "params": [
                    {
                        "query": f"kubernetes_container_name:waku AND kubernetes_pod_name:nodes-{shard}-{node_index} AND received relay message AND _time:{self._timestamp}"},
                    {
                        "query": f"kubernetes_container_name:waku AND kubernetes_pod_name:nodes-{shard}-{node_index} AND sent relay message AND _time:{self._timestamp}"}]
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
                               "query": f"kubernetes_pod_name:nodes AND kubernetes_container_name:waku AND 'my_peer_id=16U*{peer_id}' AND _time:{self._timestamp} | limit 1"}}

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
        log_name_path = self._dump_analysis_dir / f"{data_file.split('.')[0]}.log"
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
        reader = FileReader(self._local_path_to_analyze, waku_tracer)
        dfs = reader.read()

        has_issues = waku_tracer.has_message_reliability_issues('msg_hash', 'receiver_peer_id', dfs[0], dfs[1],
                                                                self._dump_analysis_dir)

        return has_issues

    def _has_issues_in_cluster_single(self) -> bool:
        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()
        reader = VictoriaReader(self._get_victoria_config_single(), waku_tracer)
        dfs = reader.read()

        has_issues = waku_tracer.has_message_reliability_issues('msg_hash', 'receiver_peer_id', dfs[0], dfs[1],
                                                                self._dump_analysis_dir)

        return has_issues

    def _read_logs_for_node(self, node_index, victoria_config_func) -> List[pd.DataFrame]:
        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()

        config = victoria_config_func(node_index, self._num_nodes, self._num_shards)
        reader = VictoriaReader(config, waku_tracer)
        data = reader.read()
        logger.debug(f'Nodes-{node_index} analyzed')

        return data

    def _read_logs_concurrently(self) -> List[pd.DataFrame]:
        dfs = []
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(self._read_logs_for_node, i, self._get_victoria_config_parallel): i
                       for i in range(self._num_nodes)}

            for i, future in enumerate(as_completed(futures)):
                i = i + 1
                try:
                    df = future.result()
                    dfs.append(df)
                    if i % 50 == 0:
                        logger.info(f'Processed {i}/{self._num_nodes} nodes')

                except Exception as e:
                    logger.error(f'Error retrieving logs for node {futures[future]}: {e}')

        return dfs

    def _has_issues_in_cluster_parallel(self) -> bool:
        dfs = self._read_logs_concurrently()
        dfs = self._merge_dfs(dfs)

        self._message_hashes = dfs[0].index.get_level_values(1).unique().tolist()

        result = self._dump_dfs(dfs)
        if result.is_err():
            logger.warning(f'Issue dumping message summary. {result.err_value}')
            exit(1)

        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()
        has_issues = waku_tracer.has_message_reliability_issues('shard', 'msg_hash', 'receiver_peer_id', dfs[0], dfs[1],
                                                                self._dump_analysis_dir)

        return has_issues

    def _merge_dfs(self, dfs: List[pd.DataFrame]) -> List[pd.DataFrame]:
        logger.info("Merging and sorting information")
        dfs = list(zip(*dfs))
        dfs = [pd.concat(tup, axis=0) for tup in dfs]

        dfs = [df.assign(shard=df['pod-name'].str.extract(r'nodes-(\d+)-').astype(int))
               .set_index(['shard', 'msg_hash', 'timestamp'])
               .sort_index()
               for df in dfs]

        return dfs

    def _dump_dfs(self, dfs: List[pd.DataFrame]) -> Result:
        received = dfs[0].reset_index()
        received = received.astype(str)
        logger.info("Dumping received information")
        result = file_utils.dump_df_as_csv(received, self._dump_analysis_dir / 'summary' / 'received.csv', False)
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        sent = dfs[1].reset_index()
        sent = sent.astype(str)
        logger.info("Dumping sent information")
        result = file_utils.dump_df_as_csv(sent, self._dump_analysis_dir / 'summary' / 'sent.csv', False)
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        return Ok(None)

    def _get_number_nodes(self) -> int:
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes_pod_name:nodes AND kubernetes_container_name:waku AND _time:{self._timestamp} | uniq by (kubernetes_pod_name)"}
                           }

        reader = VictoriaReader(victoria_config, None)
        result = reader.multi_query_info()
        if result.is_ok():
            return len(list(result.ok_value))
        else:
            logger.error(result.err_value)
            exit(1)

    def analyze_message_logs(self, parallel=False):
        if self._timestamp is not None:
            logger.info('Analyzing from server')
            self._num_nodes = self._get_number_nodes()
            logger.info(f'Detected {self._num_nodes} pods')
            has_issues = self._has_issues_in_cluster_parallel() if parallel else self._has_issues_in_cluster_single()
            if has_issues:
                match file_utils.get_files_from_folder_path(Path(self._dump_analysis_dir), extension="csv"):
                    case Ok(data_files_names):
                        self._dump_information(data_files_names)
                    case Err(error):
                        logger.error(error)
        else:
            logger.info('Analyzing from local')
            _ = self._has_issues_in_local()

    def check_store_messages(self):
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes_pod_name:get-store-messages AND _time:{self._timestamp} | sort by (_time) desc | limit 1"}
                           }

        reader = VictoriaReader(victoria_config, None)
        result = reader.single_query_info()

        if result.is_ok():
            messages_string = result.unwrap()['_msg']
            messages_list = ast.literal_eval(messages_string)
            messages_list = ['0x'+base64.b64decode(msg).hex() for msg in messages_list]
            logger.debug(f'Messages from store: {messages_list}')

            if len(self._message_hashes) != len(messages_list):
                logger.error('Number of messages does not match')
            elif set(self._message_hashes) == set(messages_list):
                logger.info('Messages from store match with received messages')
            else:
                logger.error('Messages from store does not match with received messages')
                logger.error(f'Received messages: {self._message_hashes}')
                logger.error(f'Store messages: {messages_list}')

            result = list_utils.dump_list_to_file(messages_list, self._dump_analysis_dir / 'store_messages.txt')
            if result.is_ok():
                logger.info(f'Messages from store saved in {result.ok_value}')

    def check_filter_messages(self):
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes_pod_name:get-filter-messages AND _time:{self._timestamp} | sort by (_time) desc | limit 1"}
                           }

        reader = VictoriaReader(victoria_config, None)
        result = reader.single_query_info()

        if result.is_ok():
            messages_string = result.unwrap()['_msg']
            all_ok = ast.literal_eval(messages_string)
            if all_ok:
                logger.info("Messages from filter match in length.")
            else:
                logger.error("Messages from filter do not match.")

    def analyze_message_timestamps(self, time_difference_threshold: int):
        """
        Note that this function assumes that analyze_message_logs has been called, since timestamps will be checked
        from logs.
        """
        file_logs = file_utils.get_files_from_folder_path(self._local_path_to_analyze, extension='*.log')
        if file_logs.is_err():
            logger.error(file_logs.err_value)
            return

        logger.info(f'Analyzing timestamps from {len(file_logs.ok_value)} files')
        for file in file_logs.ok_value:
            logger.debug(f'Analyzing timestamps for {file}')
            time_jumps = log_utils.find_time_jumps(self._local_path_to_analyze / file, time_difference_threshold)

            for jump in time_jumps:
                logger.info(f'{file}: {jump[0]} to {jump[1]} -> {jump[2]}')
