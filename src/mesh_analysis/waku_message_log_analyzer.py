# Python Imports
import ast
import base64
import logging
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
import numpy as np
import seaborn as sns
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Optional
from result import Ok, Err, Result

# Project Imports
from src.mesh_analysis.readers.file_reader import FileReader
from src.mesh_analysis.readers.victoria_reader import VictoriaReader
from src.mesh_analysis.tracers.waku_tracer import WakuTracer
from src.utils.plot_utils import add_boxplot_stat_labels
from src.utils import file_utils, log_utils, path_utils, list_utils
from src.utils.path_utils import check_params_path_exists_by_position, check_params_path_exists_by_position_or_kwargs

logger = logging.getLogger(__name__)
sns.set_theme()

class WakuMessageLogAnalyzer:
    def __init__(self, stateful_sets: List[str], timestamp_to_analyze: str = None,
                 dump_analysis_dir: str = None, local_folder_to_analyze: str = None):
        self._stateful_sets = stateful_sets
        self._num_nodes: List[int] = []
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

    def _get_victoria_config_parallel(self, stateful_set_name: str, node_index: int) -> Dict:
        return {"url": "https://vmselect.riff.cc/select/logsql/query",
                "headers": {"Content-Type": "application/json"},
                "params": [
                    {
                        "query": f"kubernetes.container_name:waku AND kubernetes.pod_name:{stateful_set_name}-{node_index} AND (received relay message OR  handling lightpush request) AND _time:{self._timestamp}"},
                    {
                        "query": f"kubernetes.container_name:waku AND kubernetes.pod_name:{stateful_set_name}-{node_index} AND sent relay message AND _time:{self._timestamp}"}]
                }

    def _get_victoria_config_single(self) -> Dict:
        return {"url": "https://vmselect.riff.cc/select/logsql/query",
                "headers": {"Content-Type": "application/json"},
                "params": [
                    {
                        "query": f"kubernetes.container_name:waku AND received relay message AND _time:{self._timestamp}"},
                    {
                        "query": f"kubernetes.container_name:waku AND sent relay message AND _time:{self._timestamp}"}]
                }

    def _get_affected_node_pod(self, data_file: str) -> Result[str, str]:
        peer_id = data_file.split('.')[0]
        victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                           "headers": {"Content-Type": "application/json"},
                           "params": {
                               "query": f"kubernetes.container_name:waku AND 'my_peer_id=16U*{peer_id}' AND _time:{self._timestamp} | limit 1"}}

        reader = VictoriaReader(victoria_config, None)
        result = reader.single_query_info()

        if result.is_ok():
            pod_name = result.unwrap()['kubernetes.pod_name']
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
                               "query": f"kubernetes.pod_name:{result.ok_value} AND _time:{self._timestamp} | sort by (_time)"}]}

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

        has_issues = waku_tracer.has_message_reliability_issues('shard', 'msg_hash', 'receiver_peer_id', dfs[0], dfs[1],
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

    def _read_logs_for_node(self, stateful_set_name: str, node_index: int, victoria_config_func) -> List[pd.DataFrame]:
        waku_tracer = WakuTracer()
        waku_tracer.with_received_pattern()
        waku_tracer.with_sent_pattern()

        config = victoria_config_func(stateful_set_name, node_index)
        reader = VictoriaReader(config, waku_tracer)
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

    def _merge_dfs(self, dfs: List[List[pd.DataFrame]]) -> List[pd.DataFrame]:
        logger.info("Merging and sorting information")

        received_df = pd.concat([pd.concat(group[0], ignore_index=True) for group in dfs], ignore_index=True)
        received_df = received_df.assign(shard=received_df['pod-name'].str.extract(r'.*-(\d+)-').astype(int))
        received_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = pd.concat([pd.concat(group[1], ignore_index=True) for group in dfs], ignore_index=True)
        sent_df = sent_df.assign(shard=sent_df['pod-name'].str.extract(r'.*-(\d+)-').astype(int))
        sent_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        sent_df.sort_index(inplace=True)

        return [received_df, sent_df]

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

    def _get_number_nodes(self) -> List[int]:
        num_nodes_per_stateful_set = []

        for stateful_set in self._stateful_sets:
            victoria_config = {"url": "https://vmselect.riff.cc/select/logsql/query",
                               "headers": {"Content-Type": "application/json"},
                               "params": {
                                   "query": f"kubernetes.container_name:waku AND kubernetes.pod_name:{stateful_set} AND _time:{self._timestamp} | uniq by (kubernetes.pod_name)"}
                               }

            reader = VictoriaReader(victoria_config, None)
            result = reader.multi_query_info()
            if result.is_ok():
                num_nodes_per_stateful_set.append(len(list(result.ok_value)))
            else:
                logger.error(result.err_value)
                exit(1)

        return num_nodes_per_stateful_set

    def analyze_message_logs(self, parallel: bool = False):
        if self._timestamp is not None:
            logger.info('Analyzing from server')
            self._num_nodes = self._get_number_nodes()
            logger.info(f'Detected {self._num_nodes} pods in {self._stateful_sets}')
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
                               "query": f"kubernetes.pod_name:get-store-messages AND _time:{self._timestamp} | sort by (_time) desc | limit 1"}
                           }

        reader = VictoriaReader(victoria_config, None)
        result = reader.single_query_info()

        if result.is_ok():
            messages_string = result.unwrap()['_msg']
            messages_list = ast.literal_eval(messages_string)
            messages_list = ['0x' + base64.b64decode(msg).hex() for msg in messages_list]
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
                               "query": f"kubernetes.pod_name:get-filter-messages AND _time:{self._timestamp} | sort by (_time) desc | limit 1"}
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


    def plot_message_distribution(self, received_summary_path: Path, plot_title: str, dump_path: Path) -> Result[None, str]:
        """
        Note that this function assumes that analyze_message_logs has been called, since timestamps will be checked
        from logs.
        """
        if not received_summary_path.exists():
            error = f'Received summary file {received_summary_path} does not exist'
            logger.error(error)
            return Err(error)

        sns.set_theme()

        df = pd.read_csv(received_summary_path, parse_dates=['timestamp'])
        df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)

        time_ranges = df.groupby(level='msg_hash').apply(
            lambda x: (x.index.get_level_values('timestamp').max() - x.index.get_level_values(
                'timestamp').min()).total_seconds()
        )

        time_ranges_df = time_ranges.reset_index(name='time_to_reach')

        plt.figure(figsize=(12, 6))
        ax = sns.boxplot(x='time_to_reach', data=time_ranges_df, color='skyblue', whis=(0,100))

        add_boxplot_stat_labels(ax, value_type="min", scale_by=0.001)
        add_boxplot_stat_labels(ax, value_type="max", scale_by=0.001)
        add_boxplot_stat_labels(ax, value_type="median", scale_by=0.001)

        q1 = np.percentile(time_ranges_df['time_to_reach'], 25)
        q3 = np.percentile(time_ranges_df['time_to_reach'], 75)

        text = ax.text(y=-0.1, x=q1, s=f'{q1:.3f}', ha='center', va='center',
                       fontweight='bold', color='white', size=10)
        text.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground=ax.get_lines()[0].get_color()),
            path_effects.Normal(),
        ])
        text = ax.text(y=-0.1, x=q3, s=f'{q3:.3f}', ha='center', va='center',
                       fontweight='bold', color='white', size=10)
        text.set_path_effects([
            path_effects.Stroke(linewidth=3, foreground=ax.get_lines()[0].get_color()),
            path_effects.Normal(),
        ])

        plt.xlabel('Time to Reach All Nodes (seconds)')
        plt.title(plot_title)

        plt.savefig(dump_path)
        plt.show()

        return Ok(None)


    @check_params_path_exists_by_position()
    @check_params_path_exists_by_position_or_kwargs(1, 'file_path_2')
    def check_time_to_reach_value_plot(
            self,
            file_path_1: Path,
            file_path_2: Optional[Path] = None,
            dump_path: Optional[Path] = None,
            threshold_value: Optional[int] = None,
            value_name: Optional[str] = None
    ) -> Result[None, str]:
        """
        Plot the distribution of a variable to reach a target value for one or two datasets.
        Index column should be a timestamp.

        Parameters:
            file_path_1 (Path): Path to the first CSV file containing data.
            file_path_2 (Optional[Path]): Path to the second CSV file containing data (if any).
            dump_path (Path): Path to save the generated plot.
            threshold_value (Optional[int]): Target value threshold to reach.
            value_name (Optional[str]): Name of the value for plot title.
        """

        def calculate_time_to_target(file_path: Path, threshold_value: float) -> pd.Series:
            """Calculate time to reach the target value for a given dataset."""
            df = pd.read_csv(file_path)
            df['Time'] = pd.to_datetime(df['Time'])
            df.set_index('Time', inplace=True)

            mask = df >= threshold_value
            first_reach = mask.idxmax()
            first_reach[~mask.any()] = pd.NaT  # Set to NaT if the target is never reached
            time_to_target = (first_reach - df.index[0]).dt.total_seconds()
            if time_to_target.isna().any():
                logger.warning(f'There are values in {file_path} that never reach {threshold_value}.')

            return time_to_target.dropna()

        time_to_target_1 = calculate_time_to_target(file_path_1, threshold_value)
        df_1 = pd.DataFrame({
            'Time to Target': time_to_target_1,
            'Dataset': [file_path_1.name] * len(time_to_target_1)
        })

        if file_path_2:
            time_to_target_2 = calculate_time_to_target(file_path_2, threshold_value)
            df_2 = pd.DataFrame({
                'Time to Target': time_to_target_2,
                'Dataset': [file_path_2.name] * len(time_to_target_2)
            })
            df = pd.concat([df_1, df_2])
        else:
            df = df_1

        plt.figure()
        if file_path_2:
            sns.violinplot(x=['Data']*len(df), y="Time to Target", data=df, hue="Dataset", split=True, inner="quart")
        else:
            sns.boxplot(x=['Data']*len(df), y="Time to Target", data=df)
        plt.title(f'Time to Reach Target Value: {value_name or "Target Value"}')
        plt.ylabel('Time to Reach Target (seconds)')
        plt.tight_layout()

        if dump_path:
            plt.savefig(dump_path)
        plt.show()

        return Ok(None)
