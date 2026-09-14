import logging
from typing import Callable, ClassVar, List, Literal, Self

import numpy as np
import pandas as pd

# Project Imports
from src.analysis.mesh_analysis.readers.tracers.message_tracer import (
    MessageTracer,
    PatternGroup,
    TracePair,
)

logger = logging.getLogger(__name__)


class WakuTracer(MessageTracer):
    unknown_sender_str: ClassVar[str] = "Unknown"
    log_field_prefix: ClassVar[str] = "log."

    def with_extra_fields(self, extra_fields: List[str]) -> Self:
        self.extra_fields = extra_fields
        return self

    def _prefix_fields(self, fields: List[str]) -> List[str]:
        return [f"{self.log_field_prefix}{field}" for field in fields]

    def _append_pattern_group(
        self,
        *,
        name: str,
        query: str,
        log_format: Literal["TEXT", "JSON"],
        fields: List[str],
        text_regex: str,
        convert: Callable[[List], pd.DataFrame],
    ) -> None:
        self.patterns.append(
            PatternGroup(
                name=name,
                fields=fields if log_format == "JSON" else ["_msg"],
                trace_pairs=[
                    TracePair(
                        regex=text_regex if log_format == "TEXT" else None,
                        convert=convert,
                    ),
                ],
                query=query,
            )
        )

    def with_received_pattern_group(self, log_format: Literal["TEXT", "JSON"]) -> Self:
        self._append_pattern_group(
            name="received_relay",
            query="received relay message",
            log_format=log_format,
            fields=self._prefix_fields(
                [
                    "my_peer_id",
                    "msg_hash",
                    "from_peer_id",
                    "receivedTime",
                ]
            ),
            text_regex=(
                r"received relay message.*?my_peer_id[\s\":=]+([\w*]+).*?"
                r"msg_hash[\s\":=]+(0x[\da-f]+).*?from_peer_id[\s\":=]+([\w*]+).*?"
                r"receivedTime[\s\":=]+(\d+)"
            ),
            convert=self._trace_received_in_logs,
        )

        self._append_pattern_group(
            name="received_lightpush",
            query='"handling lightpush request" AND NOT "waku lightpush legacy"',
            log_format=log_format,
            fields=self._prefix_fields(
                [
                    "my_peer_id",
                    "peer_id",
                    "msg_hash",
                    "receivedTime",
                ]
            ),
            text_regex=(
                # Example from nwaku:
                # NTC 2025-11-20 13:06:16.015+00:00 handling lightpush request topics="waku lightpush" tid=7 file=protocol.nim:79 my_peer_id=16U*GiNg1a peer_id=16U*wJXtuH requestId=db01d1a6519de2145f10 pubsubTopic="some(\"/waku/2/rs/2/0\")" msg_hash=0x17cfd30767acac9b86c18333ba918abef93cc23f65b6c98c845c682584f92583 receivedTime=1763643976019361536
                r"handling lightpush request.*?my_peer_id=([\w*]+).*?"
                r"peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?receivedTime=(\d+)"
            ),
            convert=self._trace_lightpush_in_logs,
        )

        self._append_pattern_group(
            name="received_legacy_lightpush",
            query='"handling lightpush request" AND "waku lightpush legacy"',
            log_format=log_format,
            fields=self._prefix_fields(
                [
                    "peer_id",
                    "msg_hash",
                    "receivedTime",
                ]
            ),
            text_regex=(
                # Legacy lightpush
                # Example from jswaku:
                # NTC 2025-11-20 13:50:35.376+00:00 handling lightpush request topics="waku lightpush legacy" tid=7 file=protocol.nim:48 peer_id=12D*YCde2H requestId=46e649c7-f0db-409c-afed-c34f17e2ff7b pubsubTopic=/waku/2/rs/2/0 msg_hash=0x1441e3e14e6f957d2a45332378cda900e066022412d6a1c47c95e587d82e6eb2 receivedTime=1763646635380167168
                r'handling lightpush request.*?topics="waku lightpush legacy".*?'
                r"peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?receivedTime=(\d+)"
            ),
            convert=self._trace_legacy_lightpush_in_logs,
        )

        return self

    def with_sent_pattern_group(self, log_format: Literal["TEXT", "JSON"]) -> Self:
        self._append_pattern_group(
            name="sent",
            query='"sent relay message" AND NOT publishWithConn',
            log_format=log_format,
            fields=self._prefix_fields(
                [
                    "my_peer_id",
                    "msg_hash",
                    "to_peer_id",
                    "sentTime",
                ]
            ),
            text_regex=(
                r"sent relay message.*?my_peer_id=([\w*]+).*?"
                r"msg_hash=(0x[\da-f]+).*?to_peer_id=([\w*]+).*?sentTime=(\d+)"
            ),
            convert=self._trace_sent_in_logs,
        )

        self._append_pattern_group(
            name="mix sent",
            query='"sent relay message" AND publishWithConn',
            log_format=log_format,
            fields=self._prefix_fields(
                [
                    "my_peer_id",
                    "peer_id",
                    "msg_hash",
                    "sentTime",
                ]
            ),
            text_regex=(
                r"publishWithConn.*?my_peer_id=([\w*]+).*?"
                r"peer_id=([\w*]+).*?msg_hash=(0x[\da-f]+).*?sentTime=(\d+)"
            ),
            convert=self._trace_mixnet_in_logs,
        )

        return self

    def _trace_received_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        # parsed_logs: [my_peer_id, msg_hash, from_peer_id, receivedTime, *extra_fields]
        columns = ["receiver_peer_id", "msg_hash", "sender_peer_id", "timestamp"]
        columns.extend(self.extra_fields)

        rows = []
        for row in parsed_logs:
            my_peer_id, msg_hash, from_peer_id, receivedTime, *extras = row
            rows.append([my_peer_id, msg_hash, from_peer_id, receivedTime, *extras])

        df = self._create_dataframe_with_timestamp(rows, columns)
        return df

    def _trace_sent_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        # parsed_logs: [my_peer_id, msg_hash, to_peer_id, sentTime, *extra_fields]
        columns = ["sender_peer_id", "msg_hash", "receiver_peer_id", "timestamp"]
        columns.extend(self.extra_fields)

        rows = []
        for row in parsed_logs:
            my_peer_id, msg_hash, to_peer_id, sentTime, *extras = row
            rows.append([my_peer_id, msg_hash, to_peer_id, sentTime, *extras])

        df = self._create_dataframe_with_timestamp(rows, columns)
        return df

    def _trace_mixnet_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        # parsed_logs: [my_peer_id, peer_id, msg_hash, sentTime, *extra_fields]
        columns = ["sender_peer_id", "receiver_peer_id", "msg_hash", "timestamp"]
        columns.extend(self.extra_fields)

        rows = []
        for row in parsed_logs:
            my_peer_id, peer_id, msg_hash, sentTime, *extras = row
            rows.append([my_peer_id, peer_id, msg_hash, sentTime, *extras])

        df = self._create_dataframe_with_timestamp(rows, columns)
        return df

    def _trace_lightpush_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        # parsed_logs: [my_peer_id, peer_id, msg_hash, receivedTime, *extra_fields]
        columns = ["receiver_peer_id", "sender_peer_id", "msg_hash", "timestamp"]
        columns.extend(self.extra_fields)

        rows = []
        for row in parsed_logs:
            my_peer_id, peer_id, msg_hash, receivedTime, *extras = row
            rows.append([my_peer_id, peer_id, msg_hash, receivedTime, *extras])

        df = self._create_dataframe_with_timestamp(rows, columns)
        return df

    def _trace_legacy_lightpush_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        # parsed_logs: [peer_id, msg_hash, receivedTime, *extra_fields]
        columns = ["receiver_peer_id", "sender_peer_id", "msg_hash", "timestamp"]
        columns.extend(self.extra_fields)

        rows = []
        for row in parsed_logs:
            peer_id, msg_hash, receivedTime, *extras = row
            rows.append([self.unknown_sender_str, peer_id, msg_hash, receivedTime, *extras])

        df = self._create_dataframe_with_timestamp(rows, columns)
        return df

    def _trace_all_logs(self, parsed_logs: List) -> List:
        return parsed_logs

    def _create_dataframe_with_timestamp(self, parsed_logs: List[str], columns: List[str]):
        try:
            df = pd.DataFrame(parsed_logs, columns=columns)
            df["timestamp"] = df["timestamp"].astype(np.uint64)
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ns")
        except ValueError as e:
            lines = len(parsed_logs)
            try:
                logs_columns = len(parsed_logs[0])
            except IndexError:
                logs_columns = "N/A"
            raise ValueError(
                f"Failed to create dataframe from parsed logs.\n"
                f"parsed_logs has {logs_columns} columns and {lines} entries\n"
                f"expected {len(columns)} columns: {columns}"
            ) from e

        return df
