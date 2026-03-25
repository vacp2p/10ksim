import logging
from typing import ClassVar, List, Self

import numpy as np
import pandas as pd
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer, PatternGroup, TracePair

logger = logging.getLogger(__name__)


class Nimlibp2pTracer(MessageTracer):
    unknown_sender_str: ClassVar[str] = "Unknown"

    def with_extra_fields(self, extra_fields: List[str]) -> Self:
        self.extra_fields = extra_fields
        return self

    def with_received_pattern_group(self) -> Self:
        self.patterns.append(
            PatternGroup(
                "received",
                trace_pairs=[
                    TracePair(
                        regex=r"Received message.*?msgId=([\w*]+).*?sentAt=([\w*]+).*?current=([\w*]+).*?delayMs=([\w*]+)",
                        convert=self._trace_received_in_logs,
                    ),
                ],
                query="Received message",
            )
        )
        return self

    def with_sent_pattern_group(self) -> Self:
        sent_pattern_group = PatternGroup(
            name="sent",
            trace_pairs=[
                TracePair(
                    regex=r"Sent message.*?msgId=([\w*]+).*?timestamp=([\w*]+)",
                    convert=self._trace_sent_in_logs,
                ),
            ],
            query="Sent message",
        )
        self.patterns.append(sent_pattern_group)
        return self

    def _trace_received_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["msgId", "sentAt", "timestamp", "delayMs"]
        if self.extra_fields is not None:
            columns.extend(self.extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df["msgId"] = pd.to_numeric(df["msgId"], errors="coerce").fillna(-1).astype(int)
        df["sentAt"] = df["sentAt"].astype(np.uint64)
        df["sentAt"] = pd.to_datetime(df["sentAt"], unit="ns")
        df["timestamp"] = df["timestamp"].astype(np.uint64)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ns")

        return df

    def _trace_sent_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["msgId", "timestamp"]
        if self.extra_fields is not None:
            columns.extend(self.extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df["msgId"] = pd.to_numeric(df["msgId"], errors="coerce").fillna(-1).astype(int)
        df["timestamp"] = df["timestamp"].astype(np.uint64)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ns")

        return df

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
