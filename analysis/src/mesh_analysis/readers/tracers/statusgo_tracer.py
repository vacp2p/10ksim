from typing import List

import numpy as np
import pandas as pd
from src.mesh_analysis.tracers.message_tracer import MessageTracer


class StatusgoTracer(MessageTracer):

    def __init__(self):
        super().__init__()
        self._patterns = []
        self._tracings = []

    def with_message_pattern(self):
        patterns = [
            r'"messages":\[\{[^}]*?"id":"(?P<id>[^"]+?)"[^}]*?"from":"(?P<from>[^"]+?)"[^}]*?"text":"[^"]*?(?P<timestamp_value>\d+\.\d+)[^"]*?"[^}]*?"chatId":"(?P<chat_id>[^"]+?)"'
        ]
        tracers = [self._trace_message_in_logs]
        self._patterns.append(patterns)
        self._tracings.append(tracers)

    def _trace_message_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        df = pd.DataFrame(
            parsed_logs,
            columns=[
                "message_id",
                "from_peer",
                "created_timestamp",
                "received_timestamp",
                "chat_id",
                "pod-name",
                "kubernetes-worker",
            ],
        )
        df["created_timestamp"] = df["created_timestamp"].astype(np.uint64)
        df["created_timestamp"] = pd.to_datetime(df["created_timestamp"], unit="ns")
        df["received_timestamp"] = df["received_timestamp"].astype(np.uint64)
        df["received_timestamp"] = pd.to_datetime(df["received_timestamp"], unit="ns")

        return df

    def trace(self, parsed_logs: List) -> List:
        return [
            [tracer(log) for tracer, log in zip(tracers, log_group)]
            for tracers, log_group in zip(self._tracings, parsed_logs)
        ]
