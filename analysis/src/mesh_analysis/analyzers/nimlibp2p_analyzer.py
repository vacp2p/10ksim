# Python Imports
import logging
from pathlib import Path

import pandas as pd
from typing import List, Optional, Tuple
from result import Result, Err, Ok

from src.mesh_analysis.readers.builders.victoria_reader_builder import VictoriaReaderBuilder
from src.mesh_analysis.readers.tracers.nimlibp2p_tracer import Nimlibp2pTracer
from src.mesh_analysis.stacks.vaclab_stack_analysis import VaclabStackAnalysis
# Project Imports
from src.utils import path_utils, file_utils

logger = logging.getLogger(__name__)


class Nimlibp2pAnalyzer:
    """
    Handles the analysis of Nimlibp2p message reliability from either local log files or online data.

    The class ensures that every Nimlibp2p node received every expected message. It facilitates both local
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

    def analyze_reliability(self, n_jobs: int):
        """
        This function automatically assumes two scenarios, analysis from online data, and analysis from local data.

        Online: It will search in the logs tracked in the used monitoring system. It makes sure that every nimlibp2p node
        received every message. It will create a summary folder in dump_analysis_dir, with 2 csv files gathering all
        the information from the received messages and sent messages. If it detects that a nimlibp2p node missed messages,
        it will log the information, and also dump the logs of that node into a <node>.log file.

        Local: It will read the logs provided in local_folder_to_analyze. It makes sure that every nimlibp2p node received
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

    def analyze_mix_trace(self, n_jobs: int):
        self._assert_num_nodes()

        tracer = Nimlibp2pTracer(extra_fields=self._kwargs['extra_fields']) \
            .with_received_pattern_group() \
            .with_sent_pattern_group() \
            .with_mix_pattern_group()

        queries = ['Received message', 'Publishing message', '("Sender " OR "Intermediate " OR "Exit ")']
        reader_builder = VictoriaReaderBuilder(tracer, queries, **self._kwargs)
        stack_analysis = VaclabStackAnalysis(reader_builder, **self._kwargs)

        dfs = stack_analysis.get_all_node_dataframes(n_jobs)
        dfs = self._merge_mix_dfs(dfs)
        result = self._dump_mix_dfs(dfs)
        if result.is_err():
            logger.error(f'Issue dumping message summary. {result.err_value}')

    def _analyze_reliability_cluster(self, n_jobs: int):
        self._assert_num_nodes()

        tracer = Nimlibp2pTracer(extra_fields=self._kwargs['extra_fields']) \
            .with_received_pattern_group() \
            .with_sent_pattern_group()

        queries = ['Received message', 'Publishing message']
        reader_builder = VictoriaReaderBuilder(tracer, queries, **self._kwargs)
        stack_analysis = VaclabStackAnalysis(reader_builder, **self._kwargs)

        dfs = stack_analysis.get_all_node_dataframes(n_jobs)
        dfs = self._merge_dfs(dfs)

        result = self._dump_dfs(dfs)
        if result.is_err():
            logger.error(f'Issue dumping message summary. {result.err_value}')
            return None

        nodes_with_issues = self._has_message_reliability_issues('msgId', 'kubernetes.pod_name', dfs[0], dfs[1],
                                                                 self._dump_analysis_path)
        if nodes_with_issues:
            logger.info('Dumping logs from nodes with issues')
            self._dump_logs(nodes_with_issues)

    def _assert_num_nodes(self) -> None:
        tracer = Nimlibp2pTracer().with_wildcard_pattern()
        query = '*'

        reader_builder = VictoriaReaderBuilder(tracer, query, **self._kwargs)
        stack_analysis = VaclabStackAnalysis(reader_builder, **self._kwargs)

        num_nodes_per_ss = stack_analysis.get_number_nodes()
        for i, num_nodes in enumerate(num_nodes_per_ss):
            assert num_nodes == self._kwargs['nodes_per_statefulset'][i], \
                f'Number of nodes in cluster {num_nodes_per_ss} doesnt match'
            f'with provided {self._kwargs["nodes_per_statefulset"]} data.'


    def _merge_dfs(self, dfs: List[List[pd.DataFrame]]) -> List[pd.DataFrame]:
        logger.info("Merging and sorting information")

        received_df = pd.concat([pd.concat(group[0], ignore_index=True) for group in dfs], ignore_index=True)
        received_df.set_index(['msgId', 'current'], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = pd.concat([pd.concat(group[1], ignore_index=True) for group in dfs], ignore_index=True)
        sent_df.set_index(['msgId', 'timestamp'], inplace=True)
        sent_df.sort_index(inplace=True)

        return [received_df, sent_df]

    def _merge_mix_dfs(self, dfs: List[List[pd.DataFrame]]) -> List[pd.DataFrame]:
        logger.info("Merging and sorting information")

        received_df = pd.concat([pd.concat(group[0], ignore_index=True) for group in dfs], ignore_index=True)
        received_df.set_index(['msgId', 'current'], inplace=True)
        received_df.sort_index(inplace=True)

        sent_df = pd.concat([pd.concat(group[1], ignore_index=True) for group in dfs], ignore_index=True)
        sent_df.set_index(['msgId', 'timestamp'], inplace=True)
        sent_df.sort_index(inplace=True)

        mix_df = pd.concat([pd.concat(group[2], ignore_index=True) for group in dfs], ignore_index=True)
        mix_df.set_index(['msgId', 'current'], inplace=True)
        mix_df.sort_index(inplace=True)

        return [received_df, sent_df, mix_df]

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

    def _dump_mix_dfs(self, dfs: List[pd.DataFrame]) -> Result:
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

        mix = dfs[2].reset_index()
        mix = mix.astype(str)
        logger.info("Dumping sent information")
        result = file_utils.dump_df_as_csv(mix, self._dump_analysis_path / 'summary' / 'mix.csv', False)
        if result.is_err():
            logger.warning(result.err_value)
            return Err(result.err_value)

        return Ok(None)

    def _has_message_reliability_issues(self, msg_identifier: str, peer_identifier: str,
                                        received_df: pd.DataFrame, sent_df: pd.DataFrame,
                                        issue_dump_location: Path) -> Optional[List[str]]:
        logger.info(f'Nº of Peers: {len(received_df["kubernetes.pod_name"].unique())}')
        logger.info(f'Nº of unique messages: {len(received_df.index.get_level_values(0).unique())}')

        peers_missed_messages, missed_messages = self._get_peers_missed_messages(msg_identifier, peer_identifier, received_df)

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

    def _get_peers_missed_messages(self, msg_identifier: str, peer_identifier: str, df: pd.DataFrame) -> Tuple[List, List]:
        all_peers_missed_messages = []
        all_missing_messages = []

        unique_messages = len(df.index.get_level_values(msg_identifier).unique())

        grouped = df.groupby([msg_identifier, peer_identifier]).size().reset_index(name='count')
        pivot_df = grouped.pivot_table(index=msg_identifier, columns=peer_identifier, values='count', fill_value=0)

        peers_missed_msg = pivot_df.columns[pivot_df.sum() != unique_messages].to_list()
        missing_messages = pivot_df.index[pivot_df.eq(0).any(axis=1)].tolist()

        if not peers_missed_msg:
            logger.info(f'All peers received all messages')
        else:
            logger.warning(f'Nodes missed messages')
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
            pod_name = complete_df[complete_df["kubernetes.pod_name"] == result[0]]["kubernetes.pod_name"].iloc[0][0]
            logger.warning(f'Node {result[0]} ({pod_name}) {result[1]}/{unique_messages}: {missing_hashes}')

    def _dump_logs(self, nodes_with_issues: List[str]):
        tracer = Nimlibp2pTracer().with_wildcard_pattern()
        vreader = VictoriaReaderBuilder(tracer, '*', **self._kwargs)
        stack = VaclabStackAnalysis(vreader, **self._kwargs)
        stack.dump_node_logs(8, nodes_with_issues, self._dump_analysis_path)

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