# Python Imports
import ast
import base64
import logging
import pandas as pd
import seaborn as sns
from pathlib import Path
from typing import List, Tuple, Optional
from result import Ok, Err, Result

# Project Imports
from src.mesh_analysis.readers.builders.victoria_reader_builder import VictoriaReaderBuilder
from src.mesh_analysis.readers.file_reader import FileReader
from src.mesh_analysis.readers.tracers.waku_tracer import WakuTracer
from src.mesh_analysis.stacks.vaclab_stack_analysis import VaclabStackAnalysis
from src.utils import file_utils, log_utils, path_utils, list_utils

logger = logging.getLogger(__name__)
sns.set_theme()


class WakuAnalyzer:
    """
    Handles the analysis of Waku message reliability from either local log files or online data.

    The class ensures that every Waku node received every expected message. It facilitates both local
    and online analysis of message reliability, merging and processing dataframes, and dumping results.
    In cases of missed messages, the class logs details and optionally dumps relevant node logs. It
    supports parallel processing to improve analysis efficiency.

    :ivar _dump_analysis_path: Path where analysis results are dumped.
    :ivar _local_path_to_analyze: Path to the folder containing local logs for analysis.
    :ivar _kwargs: Additional settings and configurations for analysis.
    :ivar _message_hashes: List of message hashes analyzed.
    """
    def __init__(self, dump_analysis_dir: str = None, local_folder_to_analyze: str = None, **kwargs):
        self._set_up_paths(dump_analysis_dir, local_folder_to_analyze)
        self._kwargs = kwargs
        self._message_hashes = []

    def _set_up_paths(self, dump_analysis_dir: str, local_folder_to_analyze: str):
        self._dump_analysis_path = Path(dump_analysis_dir) if dump_analysis_dir else None
        self._local_path_to_analyze = Path(local_folder_to_analyze) if local_folder_to_analyze else None
        result = path_utils.prepare_path_for_folder(self._dump_analysis_path)
        if result.is_err():
            logger.error(result.err_value)
            exit(1)

    def _analyze_reliability_local(self, n_jobs: int):
        waku_tracer = WakuTracer(['file'])
        waku_tracer.with_received_pattern_group()
        waku_tracer.with_sent_pattern_group()

        reader = FileReader(self._local_path_to_analyze, waku_tracer, n_jobs)
        dfs = reader.get_dataframes()
        dfs = self._merge_dfs_local(dfs)

        received_df = dfs[0].assign(shard=0)
        received_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = dfs[1].assign(shard=0)
        sent_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        sent_df.sort_index(inplace=True)

        result = self._dump_dfs([received_df, sent_df])
        if result.is_err():
            logger.warning(f'Issue dumping message summary. {result.err_value}')
            exit(1)

        self._has_message_reliability_issues('shard', 'msg_hash', 'kubernetes.pod-name', received_df, sent_df,
                                             self._dump_analysis_path)

    def _merge_dfs(self, dfs: List[List[pd.DataFrame]]) -> List[pd.DataFrame]:
        logger.info("Merging and sorting information")

        received_df = pd.concat([pd.concat(group[0], ignore_index=True) for group in dfs], ignore_index=True)
        received_df = received_df.assign(shard=received_df['kubernetes.pod_name'].str.extract(r'.*-(\d+)-').astype(int))
        received_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = pd.concat([pd.concat(group[1], ignore_index=True) for group in dfs], ignore_index=True)
        sent_df = sent_df.assign(shard=sent_df['kubernetes.pod_name'].str.extract(r'.*-(\d+)-').astype(int))
        sent_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        sent_df.sort_index(inplace=True)

        return [received_df, sent_df]

    def _merge_dfs_local(self, dfs: List[List[pd.DataFrame]]) -> List[pd.DataFrame]:
        """
        TODO currently shard information is picked in the pod's name during the experiment. If you are working with
        local logs, make sure that each node has it's own log file, named like <node>-<shard>-<node_index>.
        """
        logger.info("Merging and sorting information")

        received_df = pd.concat(dfs[0], ignore_index=True)
        received_df = received_df.assign(shard=received_df['file'].str.extract(r'.*-(\d+)-').astype(int))
        received_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = pd.concat(dfs[1], ignore_index=True)
        sent_df = sent_df.assign(shard=sent_df['file'].str.extract(r'.*-(\d+)-').astype(int))
        sent_df.set_index(['shard', 'msg_hash', 'timestamp'], inplace=True)
        sent_df.sort_index(inplace=True)

        return [received_df, sent_df]

    def _dump_dfs(self, dfs: List[pd.DataFrame]) -> Result:
        received = dfs[0].reset_index()
        received = received.astype(str)
        logger.info("Dumping received information")
        result = file_utils.dump_df_as_csv(received, self._dump_analysis_path / 'summary' / 'received.csv', False)
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        sent = dfs[1].reset_index()
        sent = sent.astype(str)
        logger.info("Dumping sent information")
        result = file_utils.dump_df_as_csv(sent, self._dump_analysis_path / 'summary' / 'sent.csv', False)
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        return Ok(None)

    def _assert_num_nodes(self) -> Result[str, str]:
        tracer = WakuTracer().with_wildcard_pattern()
        query = '*'

        reader_builder = VictoriaReaderBuilder(tracer, query, **self._kwargs)
        stack_analysis = VaclabStackAnalysis(reader_builder, **self._kwargs)

        num_nodes_per_ss = stack_analysis.get_number_nodes()
        for i, num_nodes in enumerate(num_nodes_per_ss):
            if num_nodes != self._kwargs['nodes_per_statefulset'][i]:
                return Err(f'Number of nodes in cluster {num_nodes_per_ss} doesnt match'
                             f'with provided {self._kwargs["nodes_per_statefulset"]} data.')

        return Ok(f'Found {num_nodes_per_ss} nodes')

    def _dump_logs(self, nodes_with_issues: List[str]):
        tracer = WakuTracer().with_wildcard_pattern()
        vreader = VictoriaReaderBuilder(tracer, '*', **self._kwargs)
        stack = VaclabStackAnalysis(vreader, **self._kwargs)
        stack.dump_node_logs(8, nodes_with_issues, self._dump_analysis_path)

    def _analyze_reliability_cluster(self, n_jobs: int):
        result = self._assert_num_nodes()
        if result.is_ok():
            logger.info(result.ok_value)
        else:
            logger.error(result.err_value)
            exit(1)

        tracer = WakuTracer(extra_fields=self._kwargs['extra_fields']) \
            .with_received_pattern_group() \
            .with_sent_pattern_group()

        queries = ['(received relay message OR  handling lightpush request)', 'sent relay message']
        reader_builder = VictoriaReaderBuilder(tracer, queries, **self._kwargs)
        stack_analysis = VaclabStackAnalysis(reader_builder, **self._kwargs)

        dfs = stack_analysis.get_all_node_dataframes(n_jobs)
        dfs = self._merge_dfs(dfs)

        result = self._dump_dfs(dfs)
        if result.is_err():
            logger.warning(f'Issue dumping message summary. {result.err_value}')
            exit(1)

        nodes_with_issues = self._has_message_reliability_issues('shard', 'msg_hash', 'kubernetes.pod_name', dfs[0], dfs[1],
                                                                 self._dump_analysis_path)
        if nodes_with_issues:
            logger.info('Dumping logs from nodes with issues')
            self._dump_logs(nodes_with_issues)


    def analyze_reliability(self, n_jobs: int):
        """
        This function automatically assumes two scenarios, analysis from online data, and analysis from local data.

        Online: It will search in the logs tracked in the used monitoring system. It makes sure that every waku node
        received every message. It will create a summary folder in dump_analysis_dir, with 2 csv files gathering all
        the information from the received messages and sent messages. If it detects that a waku node missed messages,
        it will log the information, and also dump the logs of that node into a <node>.log file.

        Local: It will read the logs provided in local_folder_to_analyze. It makes sure that every waku node received
        every message. It will create a summary folder IN dump_analysis_dir, with 2 csv files gathering all the
        information from the received messages and sent messages.

        :param n_jobs: The number of parallel jobs to use for the analysis.
        :type n_jobs: int
        :return: None
        """
        if self._local_path_to_analyze is None:
            self._analyze_reliability_cluster(n_jobs)
        else:
            self._analyze_reliability_local(n_jobs)

    def _has_message_reliability_issues(self, shard_identifier: str, msg_identifier: str, peer_identifier: str,
                                        received_df: pd.DataFrame, sent_df: pd.DataFrame,
                                        issue_dump_location: Path) -> Optional[List[str]]:
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
            for data in msg_sent_data:
                peer_id = data[0].split('*')[-1]
                logger.info(f'Peer {peer_id} message information dumped in {issue_dump_location}')
                match path_utils.prepare_path_for_file(issue_dump_location / f"{data[0].split('*')[-1]}.csv"):
                    case Ok(location_path):
                        data[1].to_csv(location_path)
                    case Err(err):
                        logger.error(err)
                        exit(1)
            return peers_missed_messages

        return None

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
                logger.warning(f'Nodes missed messages on shard {shard}')
                logger.warning(f'Nodes who missed messages: {peers_missed_msg}')
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
            pod_name, count = result
            missing_hashes = df[df[pod_name] == 0].index.tolist()
            missing_hashes.extend(df[df[pod_name].isna()].index.tolist())
            pod_name = complete_df[complete_df["kubernetes.pod_name"] == result[0]]["receiver_peer_id"].iloc[0][0]
            logger.warning(f'Node {result[0]} ({pod_name}) {result[1]}/{unique_messages}: {missing_hashes}')

    def check_store_messages(self):
        """
        It checks that the messages obtained by get-store-messages pod are the same messages detected in
        analyze_reliability. This is used to detect if the store nodes can retrieve all messages.
        It has to be used after analyze_reliability, and this function only makes sense if there were store nodes
        in the experiment.
        :return:
        """
        waku_tracer = WakuTracer().with_wildcard_pattern()
        reader = VictoriaReaderBuilder(waku_tracer, '*', **self._kwargs)
        stack = VaclabStackAnalysis(reader, **self._kwargs)
        data = stack.get_pod_logs('get-store-messages', 'container')

        log_list = data[0][0]  # We will always have 1 pattern group with 1 pattern
        messages_list = ast.literal_eval(log_list[-1]) # Last line in get-store-messages
        # TODO: Probably issue here

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

        result = list_utils.dump_list_to_file(messages_list, self._dump_analysis_path / 'store_messages.txt')
        if result.is_ok():
            logger.info(f'Messages from store saved in {result.ok_value}')

    def check_filter_messages(self):
        """
        It checks that the messages obtained by get-filter-messages pod are the same messages detected in
        analyze_reliability. This is used to detect if the filter nodes received all messages.
        It has to be used after analyze_reliability, and this function only makes sense if there were filter nodes
        in the experiment.
        :return:
        """
        waku_tracer = WakuTracer().with_wildcard_pattern()
        reader = VictoriaReaderBuilder(waku_tracer, '*', **self._kwargs)
        stack = VaclabStackAnalysis(reader, **self._kwargs)
        data = stack.get_pod_logs('get-filter-messages', 'container')

        log_list = data[0][0]  # We will always have 1 pattern group with 1 pattern
        all_ok = ast.literal_eval(log_list[0][0]) # Last line in get-filter-messages
        # Todo: check multiple std's

        if all_ok:
            logger.info("Messages from filter match in length.")
        else:
            logger.error("Messages from filter do not match.")
