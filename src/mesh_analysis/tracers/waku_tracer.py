# Python Imports
import logging
import numpy as np
import pandas as pd
from typing import List, Tuple

# Project Imports
from src.mesh_analysis.tracers.message_tracer import MessageTracer

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
        self._patterns.append(r'received relay message.*?my_peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?from_peer_id=([\w*]+).*?receivedTime=(\d+)')
        self._tracings.append(self._trace_received_in_logs)

    def with_sent_pattern(self):
        self._patterns.append(r'sent relay message.*?my_peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?to_peer_id=([\w*]+).*?sentTime=(\d+)')
        self._tracings.append(self._trace_sent_in_logs)

    def with_wildcard_pattern(self):
        self._patterns.append(r'(.*)')
        self._tracings.append(self._trace_all_logs)

    def trace(self, parsed_logs: List) -> List:
        dfs = []
        for i, trace in enumerate(self._tracings):
            if trace is not None:
                dfs.append(trace(parsed_logs[i]))

        return dfs

    def _trace_received_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        df = pd.DataFrame(parsed_logs, columns=['receiver_peer_id', 'msg_hash', 'sender_peer_id', 'timestamp', 'pod-name'])
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')
        df.set_index(['msg_hash', 'timestamp'], inplace=True)
        df.sort_index(inplace=True)

        return df

    def _trace_sent_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        df = pd.DataFrame(parsed_logs, columns=['sender_peer_id', 'msg_hash', 'receiver_peer_id', 'timestamp', 'pod-name'])
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')
        df.set_index(['msg_hash', 'timestamp'], inplace=True)
        df.sort_index(inplace=True)

        return df

    def _trace_all_logs(self, parsed_logs: List) -> List:
        return parsed_logs

    def _get_peers_missed_messages(self, msg_identifier: str, peer_identifier: str, df: pd.DataFrame) -> Tuple[List, List]:
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

        return peers_missed_msg, missing_messages

    def check_if_msg_has_been_sent(self, peers: List, missed_messages: List, sent_df: pd.DataFrame):
        messages_sent_to_peer = []
        for peer in peers:
            filtered_df = sent_df.loc[missed_messages]
            filtered_df = filtered_df[filtered_df['receiver_peer_id'] == peer]
            messages_sent_to_peer.append((peer, filtered_df))

        return messages_sent_to_peer

    def message_reliability(self, msg_identifier: str, peer_identifier: str, received_df: pd.DataFrame,
                            sent_df: pd.DataFrame):
        logger.info(f'Nº of Peers: {len(received_df["receiver_peer_id"].unique())}')
        logger.info(f'Nº of unique messages: {len(received_df.index.get_level_values(0).unique())}')

        peers_missed_messages, missed_messages = self._get_peers_missed_messages(msg_identifier, peer_identifier, received_df)

        return peers_missed_messages, missed_messages
