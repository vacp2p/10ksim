# Python Imports
import logging
import numpy as np
import pandas as pd
from typing import List

# Project Imports
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer


logger = logging.getLogger(__name__)


class WakuTracer(MessageTracer):

    def __init__(self, extra_fields: List[str]):
        super().__init__(extra_fields)
        self._patterns = []
        self._tracings = []

    def get_extra_fields(self) -> List[str]:
        return self._extra_fields

    def get_num_patterns_group(self) -> int:
        return len(self._patterns)

    @property
    def patterns(self) -> List[List[str]]:
        return self._patterns

    def with_received_group_pattern(self):
        patterns = [
            r'received relay message.*?my_peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?from_peer_id=([\w*]+).*?receivedTime=(\d+)',
            r'handling lightpush request.*?my_peer_id=([\w*]+).*?peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?receivedTime=(\d+)'
        ]

        tracers = [self._trace_received_in_logs,
                   self._trace_lightpush_in_logs
                   ]

        self._patterns.append(patterns)
        self._tracings.append(tracers)

    def with_sent_pattern_group(self):
        patterns = [
            r'sent relay message.*?my_peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?to_peer_id=([\w*]+).*?sentTime=(\d+)',
            r'publishWithConn.*?my_peer_id=([\w*]+).*?peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?sentTime=(\d+)',
        ]
        tracers = [self._trace_sent_in_logs,
                   self._trace_mixnet_in_logs,
                   ]
        self._patterns.append(patterns)
        self._tracings.append(tracers)

    def with_wildcard_pattern(self):
        self._patterns.append(r'(.*)')
        self._tracings.append(self._trace_all_logs)

    def trace(self, parsed_logs: List[List]) -> List[List]:
        """Returns one Dataframe per pattern string. ie: received patterns (2) and sent patterns (2), will
        return a List with 2 positions (received + send patterns). Inside each position, it will have as 
        many Dataframes as string patterns there are. In total, 4 Dataframes.
        """
        return [[tracer(log) for tracer, log in zip(tracers, log_group)]
                for tracers, log_group in zip(self._tracings, parsed_logs)]

    def _trace_received_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['receiver_peer_id', 'msg_hash', 'sender_peer_id', 'timestamp']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')

        return df

    def _trace_sent_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['sender_peer_id', 'msg_hash', 'receiver_peer_id', 'timestamp']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')

        return df

    def _trace_mixnet_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['sender_peer_id', 'receiver_peer_id', 'msg_hash', 'timestamp']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')

        return df

    def _trace_lightpush_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['receiver_peer_id', 'sender_peer_id', 'msg_hash', 'timestamp']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')

        return df

    def _trace_all_logs(self, parsed_logs: List) -> List:
        return parsed_logs
