# Python Imports
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Tuple
from result import Ok, Err

# Project Imports
from src.mesh_analysis.tracers.message_tracer import MessageTracer
from src.utils import path_utils

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
        patterns = [
            r'received relay message.*?my_peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?from_peer_id=([\w*]+).*?receivedTime=(\d+)',
            r'handling lightpush request.*?my_peer_id=([\w*]+).*?peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?receivedTime=(\d+)']
        tracers = [self._trace_received_in_logs,
                   self._trace_lightpush_in_logs]
        self._patterns.append(patterns)
        self._tracings.append(tracers)

    def with_sent_pattern(self):
        patterns = [
            r'sent relay message.*?my_peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?to_peer_id=([\w*]+).*?sentTime=(\d+)']
        tracers = [self._trace_sent_in_logs]
        self._patterns.append(patterns)
        self._tracings.append(tracers)

    def with_wildcard_pattern(self):
        self._patterns.append(r'(.*)')
        self._tracings.append(self._trace_all_logs)

    def trace(self, parsed_logs: List[List]) -> List[List]:
        return [[tracer(log) for tracer, log in zip(tracers, log_group)]
                for tracers, log_group in zip(self._tracings, parsed_logs)]

    def _trace_received_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        df = pd.DataFrame(parsed_logs,
                          columns=['receiver_peer_id', 'msg_hash', 'sender_peer_id', 'timestamp', 'pod-name',
                                   'kubernetes-worker'])
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')

        return df

    def _trace_sent_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        df = pd.DataFrame(parsed_logs,
                          columns=['sender_peer_id', 'msg_hash', 'receiver_peer_id', 'timestamp', 'pod-name',
                                   'kubernetes-worker'])
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')

        return df

    def _trace_lightpush_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        df = pd.DataFrame(parsed_logs, columns=['receiver_peer_id', 'sender_peer_id', 'msg_hash', 'timestamp',
                                                'pod-name', 'kubernetes-worker'])

        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')

        return df

    def _trace_all_logs(self, parsed_logs: List) -> List:
        return parsed_logs

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

                self._log_received_messages(pivot_df, unique_messages)

        return all_peers_missed_messages, all_missing_messages

    def _log_received_messages(self, df: pd.DataFrame, unique_messages: int):
        column_sums = df.sum()
        filtered_sums = column_sums[column_sums != unique_messages]
        result_list = list(filtered_sums.items())
        for result in result_list:
            peer_id, count = result
            missing_hashes = df[df[peer_id] == 0].index.tolist()
            missing_hashes.extend(df[df[peer_id].isna()].index.tolist())
            logger.warning(f'Peer {result[0]} {result[1]}/{unique_messages}: {missing_hashes}')

    def check_if_msg_has_been_sent(self, peers: List, missed_messages: List, sent_df: pd.DataFrame) -> List:
        messages_sent_to_peer = []
        for peer in peers:
            try:
                filtered_df = sent_df.loc[(slice(None), missed_messages), :]
                filtered_df = filtered_df[filtered_df['receiver_peer_id'] == peer]
                messages_sent_to_peer.append((peer, filtered_df))
            except KeyError as _:
                logger.warning(f'Message {missed_messages} has not ben sent to {peer} by any other node.')

        return messages_sent_to_peer

    def has_message_reliability_issues(self, shard_identifier: str, msg_identifier: str, peer_identifier: str,
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
