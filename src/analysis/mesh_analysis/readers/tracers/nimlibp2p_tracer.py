import logging
from typing import ClassVar, List, Self

import numpy as np
import pandas as pd

# Project Imports
from src.analysis.mesh_analysis.readers.tracers.message_tracer import (
    MessageTracer,
    PatternGroup,
    TracePair,
)

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

    def with_kad_dht_pattern(self) -> Self:
        self.patterns.append(
            PatternGroup(
                name="kad_dht",
                trace_pairs=[
                    TracePair(
                        regex=r'target=(?P<target>\S+)\s+duration_ms=(?P<duration_ms>\d+)\s+peers="(?P<peers>\[.*\])"$',
                        convert=self._trace_kad_dht_in_logs,
                    ),
                ],
                query="Lookup finished"
            )
        )
        return self

    def with_node_started_pattern(self) -> Self:
        self.patterns.append(
            PatternGroup(
                name="node_started",
                trace_pairs=[
                    TracePair(
                        regex=r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+\d{2}:\d{2}) Node started",
                        convert=self._trace_warmup_event_in_logs,
                    ),
                ],
                query="Node started"
            )
        )
        return self

    def with_peer_id_pattern(self) -> Self:
        self.patterns.append(
            PatternGroup(
                name="peer_id",
                trace_pairs=[
                    TracePair(
                        regex=r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+\d{2}:\d{2}) Node started.*?peerId=([a-zA-Z0-9]+)",
                        convert=self._trace_peer_id_in_logs,
                    ),
                ],
                query="Node started"
            )
        )
        return self

    def with_probe_target_pattern(self) -> Self:
        self.patterns.append(
            PatternGroup(
                name="probe_target",
                trace_pairs=[
                    TracePair(
                        regex=r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+\d{2}:\d{2}) Probe: Finding node.*?target=([a-zA-Z0-9]+)",
                        convert=self._trace_probe_target_in_logs,
                    ),
                ],
                query="Probe: Finding node"
            )
        )
        return self

    def with_warmup_pattern(self) -> Self:
        self.patterns.append(
            PatternGroup(
                name="warmup",
                trace_pairs=[
                    TracePair(
                        regex=r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+\d{2}:\d{2}) Connected to bootstrap",
                        convert=self._trace_warmup_event_in_logs,
                    ),
                    TracePair(
                        regex=r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+\+\d{2}:\d{2}) Warmup complete",
                        convert=self._trace_warmup_event_in_logs,
                    )
                ],
                query="Connected to bootstrap OR Warmup complete"
            )
        )
        return self

    def _trace_kad_dht_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["target", "duration_ms", "peers"]
        if getattr(self, "extra_fields", None) is not None:
            columns.extend(self.extra_fields)
        df = pd.DataFrame(parsed_logs, columns=columns)
        df["duration_ms"] = pd.to_numeric(df["duration_ms"], errors="coerce").fillna(-1).astype(int)
        return df

    def _trace_warmup_event_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["timestamp"]
        if getattr(self, "extra_fields", None) is not None:
            columns.extend(self.extra_fields)
        df = pd.DataFrame(parsed_logs, columns=columns)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df

    def _trace_peer_id_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["timestamp", "peerId"]
        if getattr(self, "extra_fields", None) is not None:
            columns.extend(self.extra_fields)
        df = pd.DataFrame(parsed_logs, columns=columns)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df

    def _trace_probe_target_in_logs(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["timestamp", "probe_target"]
        if getattr(self, "extra_fields", None) is not None:
            columns.extend(self.extra_fields)
        df = pd.DataFrame(parsed_logs, columns=columns)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df
