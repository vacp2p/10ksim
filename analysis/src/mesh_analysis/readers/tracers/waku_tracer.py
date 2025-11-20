# Python Imports
import logging
import numpy as np
import pandas as pd
from typing import List, Self, Optional

# Project Imports
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer


logger = logging.getLogger(__name__)


class WakuTracer(MessageTracer):

    unknown_sender_str = "Unknown"

    def __init__(self, extra_fields: Optional[List[str]] = None):
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

    def with_received_pattern_group(self) -> Self:
        patterns = [
            r'received relay message.*?my_peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?from_peer_id=([\w*]+).*?receivedTime=(\d+)',

            # Legacy lightpush
            # Example from jswaku:
            # NTC 2025-11-20 13:50:35.376+00:00 handling lightpush request topics="waku lightpush legacy" tid=7 file=protocol.nim:48 peer_id=12D*YCde2H requestId=46e649c7-f0db-409c-afed-c34f17e2ff7b pubsubTopic=/waku/2/rs/2/0 msg_hash=0x1441e3e14e6f957d2a45332378cda900e066022412d6a1c47c95e587d82e6eb2 receivedTime=1763646635380167168
            r'handling lightpush request.*?topics="waku lightpush legacy".*?peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?receivedTime=(\d+)',

            # Example from nwaku:
            # NTC 2025-11-20 13:06:16.015+00:00 handling lightpush request topics="waku lightpush" tid=7 file=protocol.nim:79 my_peer_id=16U*GiNg1a peer_id=16U*wJXtuH requestId=db01d1a6519de2145f10 pubsubTopic="some(\"/waku/2/rs/2/0\")" msg_hash=0x17cfd30767acac9b86c18333ba918abef93cc23f65b6c98c845c682584f92583 receivedTime=1763643976019361536
            r'handling lightpush request.*?my_peer_id=([\w*]+).*?peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?receivedTime=(\d+)',

        ]

        tracers = [self._trace_received_in_logs,
                   self._trace_legacy_lightpush_in_logs,
                   self._trace_lightpush_in_logs,
                   ]

        self._patterns.append(patterns)
        self._tracings.append(tracers)

        return self

    def with_sent_pattern_group(self) -> Self:
        patterns = [
            r'sent relay message.*?my_peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?to_peer_id=([\w*]+).*?sentTime=(\d+)',
            r'publishWithConn.*?my_peer_id=([\w*]+).*?peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?sentTime=(\d+)',
        ]
        tracers = [self._trace_sent_in_logs,
                   self._trace_mixnet_in_logs,
                   ]
        self._patterns.append(patterns)
        self._tracings.append(tracers)

        return self

    def with_wildcard_pattern(self) -> Self:
        self._patterns.append([r'(.*)'])
        self._tracings.append(self._trace_all_logs)

        return self

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

        df = self._create_dataframe_with_timestamp(parsed_logs, columns)

        return df

    def _trace_sent_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['sender_peer_id', 'msg_hash', 'receiver_peer_id', 'timestamp']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = self._create_dataframe_with_timestamp(parsed_logs, columns)

        return df

    def _trace_mixnet_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['sender_peer_id', 'receiver_peer_id', 'msg_hash', 'timestamp']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = self._create_dataframe_with_timestamp(parsed_logs, columns)

        return df

    def _trace_lightpush_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['receiver_peer_id', 'sender_peer_id', 'msg_hash', 'timestamp']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        df = self._create_dataframe_with_timestamp(parsed_logs, columns)

        return df

    def _trace_legacy_lightpush_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ['receiver_peer_id', 'sender_peer_id', 'msg_hash', 'timestamp']
        if self._extra_fields is not None:
            columns.extend(self._extra_fields)

        parsed_logs = [[self.__class__.unknown_sender_str] + row for row in parsed_logs if row]
        df = self._create_dataframe_with_timestamp(parsed_logs, columns)

        return df

    def _trace_all_logs(self, parsed_logs: List) -> List:
        return parsed_logs

    def _create_dataframe_with_timestamp(self, parsed_logs: List[str], columns: List[str]):
        df = pd.DataFrame(parsed_logs, columns=columns)
        df['timestamp'] = df['timestamp'].astype(np.uint64)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns')

        return df
