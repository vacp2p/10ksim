# Python Imports
import re
import pandas as pd
from typing import List

# Project Imports
from src.mesh_analysis.tracers.message_tracer import MessageTracer


class WakuTracer(MessageTracer):

    def __init__(self):
        # TODO: Improve patterns as:
        # - Different patterns (received, sent, dropped)
        # - Once one pattern search is completed, stop search for it in the logs (ie: Announce Address)
        self._patterns = [re.compile(
            r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+\d{2}:\d{2}) .* msg_hash=([a-fA-F0-9x]+) .* sender_peer_id=([A-Za-z0-9]+)$'),
            re.compile(r'.* Announcing addresses .*\[([^]]+)\]$')]

    def trace(self, parsed_logs: List) -> pd.DataFrame:
        df = self._trace_message_in_logs(parsed_logs)

        return df

    def _trace_message_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        parsed_logs = (log for log in parsed_logs if len(log[0]) > 0)

        # Merge received message info + own ID
        res = (message + node[1][0] for node in parsed_logs for message in node[0])

        df = pd.DataFrame(res, columns=['timestamp', 'msg_hash', 'sender_peer_id', 'receiver_peer_id'])
        df['receiver_peer_id'] = df['receiver_peer_id'].apply(lambda x: x.split('/')[-1])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index(['msg_hash', 'timestamp'], inplace=True)
        df.sort_index(inplace=True)

        return df
