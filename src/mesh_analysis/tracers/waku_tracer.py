# Python Imports
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Tuple
from result import Ok, Err

# Project Imports
from src.mesh_analysis.tracers.message_tracer import MessageTracer
from src.utils import path_utils, file_utils

logger = logging.getLogger(__name__)


class WakuTracer(MessageTracer):

    def __init__(self):
        # TODO: Improve patterns as:
        # - Different patterns (received, sent, dropped)
        # - Once one pattern search is completed, stop search for it in the logs (ie: Announce Address)
        super().__init__()
        self._patterns = []
        self._tracings = []

    def with_received_pattern(self):
        self._patterns.append(
            r'received relay message.*?my_peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?from_peer_id=([\w*]+).*?receivedTime=(\d+)')
        self._tracings.append(self._trace_received_in_logs)

    def with_sent_pattern(self):
        self._patterns.append(
            r'sent relay message.*?my_peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?to_peer_id=([\w*]+).*?sentTime=(\d+)')
        self._tracings.append(self._trace_sent_in_logs)

    def with_wildcard_pattern(self):
        self._patterns.append(r'(.*)')
        self._tracings.append(self._trace_all_logs)

    def trace(self, parsed_logs: List) -> List[pd.DataFrame]:
        dfs = [trace(parsed_logs[i]) for i, trace in enumerate(self._tracings) if trace is not None]

        return dfs

    def _trace_received_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        df = pd.DataFrame(parsed_logs,
                          columns=['receiver_peer_id', 'msg_hash', 'sender_peer_id', 'timestamp', 'pod-name'])
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')
        df.set_index(['msg_hash', 'timestamp'], inplace=True)
        df.sort_index(inplace=True)

        return df

    def _trace_sent_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        df = pd.DataFrame(parsed_logs,
                          columns=['sender_peer_id', 'msg_hash', 'receiver_peer_id', 'timestamp', 'pod-name'])
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')
        df.set_index(['msg_hash', 'timestamp'], inplace=True)
        df.sort_index(inplace=True)

        return df

    def _trace_all_logs(self, parsed_logs: List) -> List:
        return parsed_logs

    def _get_peers_missed_messages(self, msg_identifier: str, peer_identifier: str, df: pd.DataFrame) -> Tuple[
        List, List]:
        unique_messages = len(df.index.get_level_values(0).unique())
        grouped = df.groupby([msg_identifier, peer_identifier]).size().reset_index(name='count')
        pivot_df = grouped.pivot_table(index=msg_identifier, columns=peer_identifier, values='count',
                                       fill_value=0)

        peers_missed_msg = pivot_df.loc[:, pivot_df.sum() != unique_messages].columns.to_list()
        missing_messages = pivot_df.index[pivot_df.eq(0).any(axis=1)].tolist()

        if not peers_missed_msg:
            logger.info(f'All peers received all messages')
        else:
            logger.warning(f'Some peers missed messages: {peers_missed_msg}')
            logger.warning(f'Missing messages: {missing_messages}')
            self._log_received_messages(pivot_df, unique_messages)

        return peers_missed_msg, missing_messages

    def _log_received_messages(self, df: pd.DataFrame, unique_messages: int):
        column_sums = df.sum()
        filtered_sums = column_sums[column_sums != unique_messages]
        result_list = list(filtered_sums.items())
        for result in result_list:
            logger.warning(f'Peer {result[0]} {result[1]}/{unique_messages} messages received')

    def check_if_msg_has_been_sent(self, peers: List, missed_messages: List, sent_df: pd.DataFrame) -> List:
        messages_sent_to_peer = []
        for peer in peers:
            filtered_df = sent_df.loc[missed_messages]
            filtered_df = filtered_df[filtered_df['receiver_peer_id'] == peer]
            messages_sent_to_peer.append((peer, filtered_df))

        return messages_sent_to_peer

    def has_message_reliability_issues(self, msg_identifier: str, peer_identifier: str, received_df: pd.DataFrame,
                                       sent_df: pd.DataFrame, issue_dump_location: Path) -> bool:
        logger.info(f'Nº of Peers: {len(received_df["receiver_peer_id"].unique())}')
        logger.info(f'Nº of unique messages: {len(received_df.index.get_level_values(0).unique())}')

        peers_missed_messages, missed_messages = self._get_peers_missed_messages(msg_identifier, peer_identifier,
                                                                                 received_df)

        # TODO add result check
        received = received_df.reset_index()
        received = received.astype(str)
        logger.info("Dumping received information")
        result = file_utils.dump_df_as_csv(received, 'received.csv', False)

        sent = sent_df.reset_index()
        sent = sent.astype(str)
        logger.info("Dumping sent information")
        result = file_utils.dump_df_as_csv(sent, 'sent.csv', False)

        if peers_missed_messages:
            msg_sent_data = self.check_if_msg_has_been_sent(peers_missed_messages, missed_messages, sent_df)
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
