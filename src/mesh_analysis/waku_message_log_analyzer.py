# Python Imports
import logging
from pathlib import Path
from typing import List
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
        self._set_victoria_config()

    def _validate_analysis_location(self, timestamp_to_analyze: str, local_folder_to_analyze: str):
        if timestamp_to_analyze is None and local_folder_to_analyze is None:
            logger.error('No timestamp or local folder specified')
            exit(1)

    def _set_up_paths(self, dump_analysis_dir: str, local_folder_to_analyze: str):
        self._dump_analysis_dir_path = Path(dump_analysis_dir) if dump_analysis_dir else None
        self._local_folder_to_analyze_path = Path(local_folder_to_analyze) if local_folder_to_analyze else None

    def _set_victoria_config(self):
        self._victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                                 "headers": {"Content-Type": "application/json"},
                                 "params": [
                                     {
                                         "query": f"kubernetes_container_name:waku AND received relay message AND _time:{self._timestamp}  | sort by (_time)"},
                                     {
                                         "query": f"kubernetes_container_name:waku AND sent relay message AND _time:{self._timestamp}  | sort by (_time)"}]
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
            return Ok(result.unwrap()['kubernetes_pod_name'])

        return Err(f'Unable to obtain pod name from {peer_id}')

    def _get_affected_node_log(self, data_file: str):
        result = self._get_affected_node_pod(data_file)
        if result.is_err():
            logger.warning(result.err_value)
            return

        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": [{
                               "query": f"kubernetes_pod_name:{result.ok_value} AND _time:{self._timestamp} | sort by (_time)"}]}

        waku_tracer = WakuTracer()
        waku_tracer.with_wildcard_pattern()
        reader = VictoriaReader(victoria_config, waku_tracer)
        pod_log = reader.read()

        log_lines = [inner_list[0] for inner_list in pod_log[0]]
        with open(self._dump_analysis_dir_path / f'{pod_log[0][0][1]}.log', 'w') as file:
            for element in log_lines:
                file.write(f"{element}\n")

    def _dump_information(self, data_files: List[str]):
        for data_file in data_files:
            logger.info(f'Dumping information for {data_file}')
            self._get_affected_node_log(data_file)

    def _has_issues_in_local(self) -> bool:
        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()
        reader = FileReader(self._local_folder_to_analyze_path, waku_tracer)
        dfs = reader.read()

        has_issues = waku_tracer.has_message_reliability_issues('msg_hash', 'receiver_peer_id', dfs[0], dfs[1],
                                                                self._dump_analysis_dir_path)

        return has_issues

    def _has_issues_in_cluster(self) -> bool:
        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()
        reader = VictoriaReader(self._victoria_config, waku_tracer)
        dfs = reader.read()

        has_issues = waku_tracer.has_message_reliability_issues('msg_hash', 'receiver_peer_id', dfs[0], dfs[1],
                                                                self._dump_analysis_dir_path)

        return has_issues

    def _get_number_nodes(self) -> int:
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes_container_name:waku AND _time:{self._timestamp} AND kubernetes_pod_name:nodes | uniq by (_stream)"}
                           }

        reader = VictoriaReader(victoria_config, None)
        result = reader.multi_query_info()
        n_nodes = len(list(result.ok_value))

        return n_nodes

    def analyze_message_logs(self):
        if self._timestamp is not None:
            n_nodes = self._get_number_nodes()
            has_issues = self._has_issues_in_cluster()
            if has_issues:
                match file_utils.get_files_from_folder_path(Path(self._dump_analysis_dir_path)):
                    case Ok(data_files_names):
                        self._dump_information(data_files_names)
                    case Err(error):
                        logger.error(error)
        else:
            _ = self._has_issues_in_local()

    def analyze_message_timestamps(self, time_difference_threshold: int):
        """
        Note that this function assumes that analyze_message_logs has been called, since timestamps will be checked
        from logs.
        """
        folder_path = self._local_folder_to_analyze_path or self._dump_analysis_dir_path
        file_logs = file_utils.get_files_from_folder_path(folder_path, '*.log')
        if file_logs.is_err():
            logger.error(file_logs.err_value)
            return

        logger.info(f'Analyzing timestamps from {len(file_logs.ok_value)} files')
        for file in file_logs.ok_value:
            logger.debug(f'Analyzing timestamps for {file}')
            time_jumps = log_utils.find_time_jumps(folder_path / file, time_difference_threshold)

            for jump in time_jumps:
                logger.info(f'{jump[0]} to {jump[1]} -> {jump[2]}')
