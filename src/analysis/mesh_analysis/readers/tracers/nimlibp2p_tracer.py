import logging
from typing import ClassVar, List, Literal, Self

import numpy as np
import pandas as pd

from src.analysis.mesh_analysis.readers.tracers.message_tracer import (
    MessageTracer,
    PatternGroup,
    TracePair,
)

logger = logging.getLogger(__name__)


class Nimlibp2pTracer(MessageTracer):
    unknown_sender_str: ClassVar[str] = "Unknown"
    log_field_prefix: str = "log."

    def with_extra_fields(self, extra_fields: List[str]) -> Self:
        self.extra_fields = extra_fields
        return self

    def _prefix_fields(self, fields: List[str]) -> List[str]:
        return [f"{self.log_field_prefix}{field}" for field in fields]

    def with_received_pattern_group(self, log_format: Literal["TEXT", "JSON"]) -> Self:
        received_fields = (
            self._prefix_fields(["msgId", "sentAt", "timestamp", "delayMs"])
            if log_format == "JSON"
            else ["_msg"]
        )
        regex = (
            r"Received message.*?msgId=([\w*]+).*?sentAt=([\w*]+).*?current=([\w*]+).*?delayMs=(-?[\w*]+)"
            if log_format == "TEXT"
            else None
        )
        self.patterns.append(
            PatternGroup(
                name="received",
                fields=received_fields,
                trace_pairs=[TracePair(regex=regex, convert=self._trace_received_in_logs)],
                query="Received message",
            )
        )
        return self

    def with_sent_pattern_group(self, log_format: Literal["TEXT", "JSON"]) -> Self:
        sent_fields = (
            self._prefix_fields(["msgId", "timestamp"]) if log_format == "JSON" else ["_msg"]
        )
        regex = (
            r"Sent message.*?msgId=([\w*]+).*?timestamp=([\w*]+)" if log_format == "TEXT" else None
        )
        self.patterns.append(
            PatternGroup(
                name="sent",
                fields=sent_fields,
                trace_pairs=[TracePair(regex=regex, convert=self._trace_sent_in_logs)],
                query="Sent message",
            )
        )
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
        self._warn_about_negative_delays(df)

        return df

    @staticmethod
    def _warn_about_negative_delays(df: pd.DataFrame) -> int:
        """Report deliveries whose measured delay is negative. Returns how many.

        delayMs is the receiver's clock minus the sender's, read on two machines, so it
        goes negative when the receiver's host clock trails the sender's by more than the
        transit time. The delivery is real; the latency is not measurable on that pair.
        """
        delays = pd.to_numeric(df["delayMs"], errors="coerce")
        negative = delays < 0
        count = int(negative.sum())
        if not count:
            return 0

        logger.warning(
            f"{count} of {len(df)} deliveries ({count / len(df):.2%}) have a negative measured "
            f"delay, down to {delays[negative].min()}ms: the receiving hosts' clocks trail the "
            f"senders'. The deliveries are counted, but their latency is not trustworthy."
        )
        return count

    def _trace_sent_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["msgId", "timestamp"]
        if self.extra_fields is not None:
            columns.extend(self.extra_fields)

        df = pd.DataFrame(parsed_logs, columns=columns)
        df["msgId"] = pd.to_numeric(df["msgId"], errors="coerce").fillna(-1).astype(int)
        df["timestamp"] = df["timestamp"].astype(np.uint64)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ns")
        return df
