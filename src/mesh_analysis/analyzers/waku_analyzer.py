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
from typing import List, Optional, Tuple
from result import Ok, Err, Result

# Project Imports
from src.mesh_analysis.readers.file_reader import FileReader
from src.mesh_analysis.readers.victoria_reader import VictoriaReader
from src.mesh_analysis.stacks.stack_analysis import StackAnalysis
from src.mesh_analysis.stacks.vaclab_stack_analysis import VaclabStackAnalysis
from src.utils.plot_utils import add_boxplot_stat_labels
from src.utils import file_utils, log_utils, path_utils, list_utils
from src.utils.path_utils import check_params_path_exists_by_position, check_params_path_exists_by_position_or_kwargs

logger = logging.getLogger(__name__)
sns.set_theme()


class WakuAnalyzer:
    def __init__(self, dump_analysis_dir: str = None, local_folder_to_analyze: str = None, **kwargs):
        self._set_up_paths(dump_analysis_dir, local_folder_to_analyze)
        self._kwargs = kwargs
        self._message_hashes = []
        self._stack: Optional[StackAnalysis] = self._set_up_stack()

    def _set_up_stack(self):
        if self._kwargs is None:
            return None

        dispatch = {
            'vaclab': VaclabStackAnalysis,
            # 'local': LocalStackAnalaysis # TODO
        }

        return dispatch[type](**self._kwargs)

    def _set_up_paths(self, dump_analysis_dir: str, local_folder_to_analyze: str):
        self._dump_analysis_dir = Path(dump_analysis_dir) if dump_analysis_dir else None
        self._local_path_to_analyze = Path(local_folder_to_analyze) if local_folder_to_analyze else None
        result = path_utils.prepare_path_for_folder(self._dump_analysis_dir)
        if result.is_err():
            logger.error(result.err_value)
            exit(1)

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

        received_df = dfs[0].assign(shard=0)
        received_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df =  dfs[1].assign(shard=0)
        sent_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        sent_df.sort_index(inplace=True)

        result = self._dump_dfs([received_df, sent_df])
        if result.is_err():
            logger.warning(f'Issue dumping message summary. {result.err_value}')
            exit(1)

        has_issues = waku_tracer.has_message_reliability_issues('shard', 'msg_hash', 'receiver_peer_id', received_df, sent_df,
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

    def analyze_reliability(self, parallel: bool = False):
        dfs = self._stack.get_reliability_data(**self._kwargs)
        dfs = self._merge_dfs(dfs)

        result = self._dump_dfs(dfs)
        if result.is_err():
            logger.warning(f'Issue dumping message summary. {result.err_value}')
            exit(1)

        has_issues = self._has_message_reliability_issues('shard', 'msg_hash', 'receiver_peer_id', dfs[0], dfs[1],
                                                                self._dump_analysis_dir)

        return has_issues

    def _has_message_reliability_issues(self, shard_identifier: str, msg_identifier: str, peer_identifier: str,
                                       received_df: pd.DataFrame, sent_df: pd.DataFrame,
                                       issue_dump_location: Path) -> bool:
        logger.info(f'Nº of Peers: {len(received_df["receiver_peer_id"].unique())}')
        logger.info(f'Nº of unique messages: {len(received_df.index.get_level_values(1).unique())}')

        peers_missed_messages, missed_messages = self._get_peers_missed_messages(shard_identifier, msg_identifier,
                                                                                 peer_identifier, received_df)

        received_df = received_df.reset_index()
        shard_groups = received_df.groupby('msg_hash')['shard'].nunique()
        violations = shard_groups[shard_groups > 1]

        if violations.empty:
            logger.info("All msg_hash values appear in only one shard.")
        else:
            logger.warning("These msg_hash values appear in multiple shards:")
            logger.warning(violations)

        if peers_missed_messages:
            msg_sent_data = self._check_if_msg_has_been_sent(peers_missed_messages, missed_messages, sent_df)
            # TODO check si realmente el nodo ha recibido el mensaje
            for data in msg_sent_data:
                peer_id = data[0].split('*')[-1]
                logger.info(f'Peer {peer_id} message information dumped in {issue_dump_location}')
                match path_utils.prepare_path_for_file(issue_dump_location / f"{data[0].split('*')[-1]}.csv"):
                    case Ok(location_path):
                        data[1].to_csv(location_path)
                    case Err(err):
                        logger.error(err)
                        exit(1)
            return True

        return False

    def _check_if_msg_has_been_sent(self, peers: List, missed_messages: List, sent_df: pd.DataFrame) -> List:
        messages_sent_to_peer = []
        for peer in peers:
            try:
                filtered_df = sent_df.loc[(slice(None), missed_messages), :]
                filtered_df = filtered_df[filtered_df['receiver_peer_id'] == peer]
                messages_sent_to_peer.append((peer, filtered_df))
            except KeyError as _:
                logger.warning(f'Message {missed_messages} has not ben sent to {peer} by any other node.')

        return messages_sent_to_peer

    def _get_peers_missed_messages(self, shard_identifier: str, msg_identifier: str, peer_identifier: str,
                                   df: pd.DataFrame) -> Tuple[List, List]:
        all_peers_missed_messages = []
        all_missing_messages = []

        for shard, df_shard in df.groupby(level=shard_identifier):
            unique_messages = len(df_shard.index.get_level_values(msg_identifier).unique())

            grouped = df_shard.groupby([msg_identifier, peer_identifier]).size().reset_index(name='count')
            pivot_df = grouped.pivot_table(index=msg_identifier, columns=peer_identifier, values='count', fill_value=0)

            peers_missed_msg = pivot_df.columns[pivot_df.sum() != unique_messages].to_list()
            missing_messages = pivot_df.index[pivot_df.eq(0).any(axis=1)].tolist()

            if not peers_missed_msg:
                logger.info(f'All peers received all messages for shard {shard}')
            else:
                logger.warning(f'Peers missed messages on shard {shard}')
                logger.warning(f'Peers who missed messages: {peers_missed_msg}')
                logger.warning(f'Missing messages: {missing_messages}')

                all_peers_missed_messages.extend(peers_missed_msg)
                all_missing_messages.extend(missing_messages)

                self._log_received_messages(pivot_df, unique_messages, df)

        return all_peers_missed_messages, all_missing_messages

    def _log_received_messages(self, df: pd.DataFrame, unique_messages: int, complete_df: pd.DataFrame):
        column_sums = df.sum()
        filtered_sums = column_sums[column_sums != unique_messages]
        result_list = list(filtered_sums.items())
        for result in result_list:
            peer_id, count = result
            missing_hashes = df[df[peer_id] == 0].index.tolist()
            missing_hashes.extend(df[df[peer_id].isna()].index.tolist())
            pod_name = complete_df[complete_df["receiver_peer_id"] == result[0]]["pod-name"][0][0]
            logger.warning(f'Peer {result[0]} ({pod_name}) {result[1]}/{unique_messages}: {missing_hashes}')

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


    def plot_message_distribution_libp2pmix(self, received_summary_path: Path, sent_summary_path: Path, compare: Path, plot_title: str, dump_path: Path) -> Result[None, str]:
        if not received_summary_path.exists():
            error = f"Received summary file {received_summary_path} does not exist"
            logger.error(error)
            return Err(error)

        if not sent_summary_path.exists():
            error = f"Sent summary file {sent_summary_path} does not exist"
            logger.error(error)
            return Err(error)

        sns.set_theme()

        df = pd.read_csv(received_summary_path, parse_dates=["timestamp"])
        other_df = pd.read_csv(compare, parse_dates=["timestamp"])

        # Check unique messages and pods
        all_msgs = df['msg_id'].unique()
        all_pods = df['pod-name'].unique()

        # Create a pivot table of counts
        msg_pod_counts = df.groupby(['msg_id', 'pod-name']).size().unstack(fill_value=0)

        # Check for missing deliveries (i.e., zero counts)
        missing_deliveries = msg_pod_counts == 0

        # Report messages not received by all pods
        incomplete_msgs = missing_deliveries.any(axis=1)
        num_incomplete = incomplete_msgs.sum()
        if num_incomplete == 0:
            print(f"All nodes received all messages.")
        else:
        # Optionally list them:
            print("Messages not received by all nodes:")
            print(msg_pod_counts[incomplete_msgs])

        delays = df[['msg_id', 'delayMs']]

        # Group by msg_id to get the max delay (i.e., last node's reception time)
        #########
        # Assuming df is your DataFrame
        allowed_pods = {'pod-0', 'pod-1', 'pod-2', 'pod-3', 'pod-4', 'pod-5', 'pod-6', 'pod-7', 'pod-8', 'pod-9'}

        # Function to check if first non-zero delay pod is allowed
        def is_first_nonzero_allowed(group):
            non_zero = group[group['delayMs'] > 0]
            if non_zero.empty:
                return True  # No non-zero delay, so considered OK
            first_pod = non_zero.sort_values('delayMs').iloc[0]['pod-name']
            return first_pod in allowed_pods

        # Group by msg_id and count violations
        violations = df.groupby('msg_id').apply(lambda g: not is_first_nonzero_allowed(g))
        violation_count = violations.sum()

        print(f"Number of violations: {violation_count}")
        #########

        max_delays = delays.groupby('msg_id')['delayMs'].max()
        other_max_delays = other_df.groupby('msg_id')['delayMs'].max()

        # Plot distribution
        plt.figure(figsize=(10, 6))

        # KDE for max delays in first experiment
        sns.kdeplot(max_delays, fill=True, label='No mix', color='skyblue', alpha=0.5)

        # KDE for max delays in second experiment
        sns.kdeplot(other_max_delays, fill=True, label='Mix', color='salmon', alpha=0.5)

        plt.title("KDE of Max Message Propagation Time (ms)")
        plt.xlabel("Time until last node received the message (ms)")
        plt.ylabel("Density")
        plt.legend()
        plt.grid(True)
        plt.xlim(0, None)
        plt.tight_layout()
        plt.savefig(dump_path / "distribution_comparison_kde.png")
        plt.show()

        mixnet_prefix = "pod-"
        mixnet_range = 10
        # Identify mixnet nodes
        mixnet_nodes = {f"{mixnet_prefix}{i}" for i in range(mixnet_range)}  # Assumes order matters

        def get_mixnet_and_outside_time(group):
            mixnet_group = group[group['pod-name'].isin(mixnet_nodes)]
            non_mixnet_group = group[~group['pod-name'].isin(mixnet_nodes)]

            if non_mixnet_group.empty:
                return pd.Series({'mixnet_time': None, 'outside_time': None})

            mixnet_time = non_mixnet_group['delayMs'].min()
            total_time = group['delayMs'].max()
            outside_time = total_time - mixnet_time
            return pd.Series({'mixnet_time': mixnet_time, 'outside_time': outside_time})

        times = df.groupby('msg_id').apply(get_mixnet_and_outside_time).dropna()

        plt.figure(figsize=(10, 6))

        # KDE area plot for mixnet delay
        sns.kdeplot(times['mixnet_time'], fill=True, label='Mixnet Time', color='orange', alpha=0.6)

        # KDE area plot for outside delay
        sns.kdeplot(times['outside_time'], fill=True, label='Outside Time', color='skyblue', alpha=0.6)

        plt.title("KDE Area Plot of Mixnet vs Outside Message Delay")
        plt.xlabel("Delay (ms)")
        plt.ylabel("Density")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(dump_path / "kde.png")
        plt.show()

        return Ok(None)


    def plot_message_distribution_mixnet(self, received_summary_path: Path, sent_summary_path: Path, plot_title: str, dump_path: Path) -> Result[None, str]:
        if not received_summary_path.exists():
            error = f"Received summary file {received_summary_path} does not exist"
            logger.error(error)
            return Err(error)

        if not sent_summary_path.exists():
            error = f"Sent summary file {sent_summary_path} does not exist"
            logger.error(error)
            return Err(error)

        sns.set_theme()

        df_received = pd.read_csv(received_summary_path, parse_dates=["timestamp"])
        df_received.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)

        df_sent = pd.read_csv(sent_summary_path, parse_dates=["timestamp"])
        df_sent.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)

        ###################
        for (shard, msg_hash), group in df_sent.groupby(['shard', 'msg_hash']):
            received_group = df_received.loc[shard, msg_hash]

            for i in range(0, len(group) - 1, 2):
                receiver_id = group.iloc[i]['receiver_peer_id']
                sender_id = group.iloc[i + 1]['sender_peer_id']

                # Check if the receiver_peer_id in the current row matches the sender_peer_id in the next row
                if receiver_id != sender_id:
                    logger.error(f"Mismatch detected at shard {shard}, msg_hash {msg_hash}, timestamp {group.index[i]}: "
                          f"{receiver_id} != {sender_id}")

            # Check that the last receiver in the received group matches the last sender in the sent data
            if received_group.iloc[-1]['receiver_peer_id'] != group.iloc[-1]['receiver_peer_id']:
                logger.error(f"Final mismatch at shard {shard}, msg_hash {msg_hash}: "
                      f"{received_group.iloc[-1]['receiver_peer_id']} != {group.iloc[-1]['sender_peer_id']}")
        ###################

        latest_received = df_received.groupby(level='msg_hash').apply(
            lambda x: x.index.get_level_values('timestamp').max()
        ).rename("last_received")

        sent_times = df_sent.groupby("msg_hash").apply(lambda x: x.index.get_level_values('timestamp').min()).rename(
            "injected_at")

        merged = pd.concat([sent_times, latest_received], axis=1, join="inner")
        merged["time_to_reach"] = (merged["last_received"] - merged["injected_at"]).dt.total_seconds()

        plt.figure(figsize=(12, 6))
        ax = sns.boxplot(x="time_to_reach", data=merged.reset_index(), color="skyblue")

        plt.xlabel('Time to Reach Node (seconds)')
        plt.title(plot_title)
        plt.savefig(dump_path)
        plt.show()

        return Ok(None)


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
        ax = sns.boxplot(x='time_to_reach', data=time_ranges_df, color='skyblue')

        add_boxplot_stat_labels(ax, value_type="min")
        add_boxplot_stat_labels(ax, value_type="max")
        add_boxplot_stat_labels(ax, value_type="median")

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
