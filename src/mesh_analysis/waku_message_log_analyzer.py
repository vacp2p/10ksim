# Python Imports
import logging
from pathlib import Path
from typing import List
from result import Ok, Err

# Project Imports
from src.mesh_analysis.readers.victoria_reader import VictoriaReader
from src.mesh_analysis.tracers.waku_tracer import WakuTracer
from src.utils import file_utils

logger = logging.getLogger(__name__)


class WakuMessageLogAnalyzer:
    def __init__(self, timestamp: str, log_analysis_dir: str):
        self._timestamp = timestamp
        self._set_victoria_config()
        self._log_analysis_dir = log_analysis_dir

    def _set_victoria_config(self):
        self._victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                                 "headers": {"Content-Type": "application/json"},
                                 "params": [
                                     {
                                         "query": f"kubernetes_container_name:waku AND received relay message AND _time:{self._timestamp}  | sort by (_time)"},
                                     {
                                         "query": f"kubernetes_container_name:waku AND sent relay message AND _time:{self._timestamp}  | sort by (_time)"}]
                                 }

    def _get_affected_node_pod(self, data_file) -> str:
        peer_id = data_file.split('.')[0]
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes_container_name:waku AND 'my_peer_id=16U*{peer_id}' AND _time:{self._timestamp} | limit 1"}}

        reader = VictoriaReader(victoria_config, None)
        data = reader.single_query_info()

        return data['kubernetes_pod_name']

    def _get_affected_node_log(self, data_file: str):
        pod_name = self._get_affected_node_pod(data_file)
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": [{
                               "query": f"kubernetes_pod_name:{pod_name} AND _time:{self._timestamp} | sort by (_time)"}]}

        wakuTracer = WakuTracer()
        wakuTracer.with_wildcard_pattern()
        reader = VictoriaReader(victoria_config, wakuTracer)
        pod_log = reader.read()

        log_lines = [inner_list[0] for inner_list in pod_log[0]]
        with open(f'{self._log_analysis_dir}/{pod_log[0][0][1]}.txt', 'w') as file:
            for element in log_lines:
                file.write(f"{element}\n")

    def _dump_information(self, data_files: List[str]):
        for data_file in data_files:
            logger.info(f'Dumping information for {data_file}')
            self._get_affected_node_log(data_file)

    def _has_issues(self) -> bool:
        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()
        reader = VictoriaReader(self._victoria_config, waku_tracer)
        dfs = reader.read()

        has_issues = waku_tracer.has_message_reliability_issues('msg_hash', 'receiver_peer_id', dfs[0], dfs[1],
                                                                self._log_analysis_dir)

        return has_issues

    def analyze_message_logs(self):
        has_issues = self._has_issues()

        if has_issues:
            match file_utils.get_files_from_folder_path(Path(self._log_analysis_dir)):
                case Ok(data_files_names):
                    self._dump_information(data_files_names)
                case Err(error):
                    logger.error(error)
