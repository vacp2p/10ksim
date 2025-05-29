# Python Imports
import logging
import pandas as pd
from typing import List

# Project Imports
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer


logger = logging.getLogger(__name__)


class Nimlibp2pTracer(MessageTracer):

    def __init__(self):
        super().__init__()
        self._patterns = []
        self._tracings = []

    def get_num_patterns_group(self) -> int:
        return len(self._patterns)

    def get_patterns(self) -> List[List[str]]:
        return self._patterns

    def with_received_pattern(self):
        patterns = [
            r'Received message.*?msgId=([\w*]+).*?sentAt=([\w*]+).*?delayMs=([\w*]+)'
        ]

        tracers = [self._trace_received_in_logs,
                   # self._trace_recv_mixlibp2p_in_logs
                   ]

        self._patterns.append(patterns)
        self._tracings.append(tracers)

    def with_sent_pattern(self):
        patterns = [
            r'Publishing message.*?msgId=([\w*]+).*?timestamp=([\w*]+)'
        ]
        tracers = [self._trace_sent_in_logs,
                   #self._trace_sent_mixlibp2p_in_logs
                   ]
        self._patterns.append(patterns)
        self._tracings.append(tracers)

    def with_wildcard_pattern(self):
        self._patterns.append(r'(.*)')
        self._tracings.append(self._trace_all_logs)

    def trace(self, parsed_logs: List[List]) -> List[List]:
        return [[tracer(log) for tracer, log in zip(tracers, log_group)]
                for tracers, log_group in zip(self._tracings, parsed_logs)]

    def _trace_received_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        raise NotImplemented

    def _trace_sent_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        raise NotImplemented

    def _trace_mixnet_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        raise NotImplemented

    def _trace_recv_mixlibp2p_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        raise NotImplemented

    def _trace_sent_mixlibp2p_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        raise NotImplemented

    def _trace_all_logs(self, parsed_logs: List) -> List:
        return parsed_logs
