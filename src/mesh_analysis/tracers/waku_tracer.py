# Python Imports
import re
import numpy as np
import pandas as pd
from typing import List

# Project Imports
from src.mesh_analysis.tracers.message_tracer import MessageTracer


class WakuTracer(MessageTracer):

    def __init__(self):
        # TODO: Improve patterns as:
        # - Different patterns (received, sent, dropped)
        # - Once one pattern search is completed, stop search for it in the logs (ie: Announce Address)
        super().__init__()
        self._patterns = [r'my_peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?from_peer_id=([\w*]+).*?receivedTime=(\d+)']

    def trace(self, parsed_logs: List) -> pd.DataFrame:
        df = self._trace_message_in_logs(parsed_logs)

        return df

    def _trace_message_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        parsed_logs = (log for log in parsed_logs if len(log[0]) > 0)
        res = (message for node in parsed_logs for message in node[0])

        df = pd.DataFrame(res, columns=['receiver_peer_id', 'msg_hash', 'sender_peer_id', 'timestamp'])
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')
        df.set_index(['msg_hash', 'timestamp'], inplace=True)
        df.sort_index(inplace=True)

        return df
