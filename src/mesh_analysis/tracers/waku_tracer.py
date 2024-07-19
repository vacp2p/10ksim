# Python Imports
import logging
import numpy as np
import pandas as pd
from typing import List

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
