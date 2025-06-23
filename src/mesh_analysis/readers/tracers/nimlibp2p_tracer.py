# Python Imports
import logging
import numpy as np
import pandas as pd
from typing import List, Optional, Self

# Project Imports
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer

logger = logging.getLogger(__name__)


class Nimlibp2pTracer(MessageTracer):

    def __init__(self, extra_fields: Optional[List[str]] = None):
        super().__init__(extra_fields)
        self._patterns = []
        self._tracings = []

    @property
    def patterns(self) -> List[List[str]]:
        return self._patterns

    def get_extra_fields(self) -> List[str]:
        return self._extra_fields

    def get_num_patterns_group(self) -> int:
        return len(self._patterns)

    def get_patterns(self) -> List[List[str]]:
        return self._patterns

    def with_received_pattern_group(self) -> Self:
        patterns = [
            r'Received message.*?msgId=([\w*]+).*?sentAt=([\w*]+).*?current=([\w*]+).*?delayMs=([\w*]+)'
        ]

        tracers = [
            self._trace_received_in_logs,
        ]

        self._patterns.append(patterns)
        self._tracings.append(tracers)

        return self

    def with_sent_pattern_group(self) -> Self:
        patterns = [
            r'Publishing message.*?msgId=([\w*]+).*?timestamp=([\w*]+)'
        ]
        tracers = [
            self._trace_sent_in_logs,
        ]
        self._patterns.append(patterns)
        self._tracings.append(tracers)

        return self

    def with_mix_pattern_group(self):
        patterns = [
            r'Sender.*?msgid=([\w*]+).*?fromPeerID=([\w*]+).*?toPeerID=([\w*]+).*?myPeerId=([\w*]+).*?orig=([\w*]+).*?current=([\w*]+).*?procDelay=([\w*]+)',
            r'Intermediate.*?msgid=([\w*]+).*?fromPeerID=([\w*]+).*?toPeerID=([\w*]+).*?myPeerId=([\w*]+).*?orig=([\w*]+).*?current=([\w*]+).*?procDelay=([\w*]+)',
            r'Exit.*?msgid=([\w*]+).*?fromPeerID=([\w*]+).*?toPeerID=([\w*]+).*?myPeerId=([\w*]+).*?orig=([\w*]+).*?current=([\w*]+).*?procDelay=([\w*]+)'
        ]
        tracers = [
            self._trace_sender_mix_in_logs,
            self._trace_intermediate_mix_in_logs,
            self._trace_exit_mix_in_logs
            ]

        self._patterns.append(patterns)
        self._tracings.append(tracers)

        return self

    def with_wildcard_pattern(self) -> Self:
        self._patterns.append(r'(.*)')
        self._tracings.append(self._trace_all_logs)

        return Self

    def trace(self, parsed_logs: List[List]) -> List[List]:
        """Returns one Dataframe per pattern string. ie: received patterns (2) and sent patterns (2), will
        return a List with 2 positions (received + send patterns). Inside each position, it will have as
        many Dataframes as string patterns there are. In total, 4 Dataframes.
        """
        return [[tracer(log) for tracer, log in zip(tracers, log_group)]
                for tracers, log_group in zip(self._tracings, parsed_logs)]

    def _trace_received_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['msgId', 'sentAt', 'current', 'delayMs']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df['msgId'] = pd.to_numeric(df['msgId'], errors='coerce').fillna(-1).astype(int)
        df['sentAt'] = df['sentAt'].astype(np.uint64)
        df['sentAt'] = pd.to_datetime(df['sentAt'], unit='ns')
        df['current'] = df['current'].astype(np.uint64)
        df['current'] = pd.to_datetime(df['current'], unit='ns')

        return df

    def _trace_sent_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['msgId', 'timestamp']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df['msgId'] = pd.to_numeric(df['msgId'], errors='coerce').fillna(-1).astype(int)
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')

        return df

    def _trace_sender_mix_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['msgId', 'fromPeerID', 'toPeerID', 'myPeerID', 'orig', 'current', 'procDelay']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df['msgId'] = pd.to_numeric(df['msgId'], errors='coerce').fillna(-1).astype(int)
        df['orig'] = df['orig'].astype(np.uint64)
        df['orig'] = pd.to_datetime(df['orig'], unit='ns')
        df['current'] = df['current'].astype(np.uint64)
        df['current'] = pd.to_datetime(df['current'], unit='ns')
        df['procDelay'] = pd.to_numeric(df['procDelay'], errors='coerce').fillna(-1).astype(float)
        df['moment'] = 'Sender'

        return df

    def _trace_intermediate_mix_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['msgId', 'fromPeerID', 'toPeerID', 'myPeerID', 'orig', 'current', 'procDelay']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df['msgId'] = pd.to_numeric(df['msgId'], errors='coerce').fillna(-1).astype(int)
        df['orig'] = df['orig'].astype(np.uint64)
        df['orig'] = pd.to_datetime(df['orig'], unit='ns')
        df['current'] = df['current'].astype(np.uint64)
        df['current'] = pd.to_datetime(df['current'], unit='ns')
        df['procDelay'] = pd.to_numeric(df['procDelay'], errors='coerce').fillna(-1).astype(float)
        df['moment'] = 'Intermediate'

        return df

    def _trace_exit_mix_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['msgId', 'fromPeerID', 'toPeerID', 'myPeerID', 'orig', 'current', 'procDelay']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df['msgId'] = pd.to_numeric(df['msgId'], errors='coerce').fillna(-1).astype(int)
        df['orig'] = df['orig'].astype(np.uint64)
        df['orig'] = pd.to_datetime(df['orig'], unit='ns')
        df['current'] = df['current'].astype(np.uint64)
        df['current'] = pd.to_datetime(df['current'], unit='ns')
        df['procDelay'] = pd.to_numeric(df['procDelay'], errors='coerce').fillna(-1).astype(float)
        df['moment'] = 'Exit'

        return df

    def _trace_all_logs(self, parsed_logs: List) -> List:
        return parsed_logs
