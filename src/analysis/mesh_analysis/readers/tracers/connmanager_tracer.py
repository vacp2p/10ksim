import logging
from typing import List, Self

import pandas as pd

from src.analysis.mesh_analysis.readers.tracers.message_tracer import (
    MessageTracer,
    PatternGroup,
    TracePair,
)

logger = logging.getLogger(__name__)


class ConnManagerTracer(MessageTracer):
    def with_extra_fields(self, extra_fields: List[str]) -> Self:
        self.extra_fields = extra_fields
        return self

    def with_stored_muxer_pattern(self) -> Self:
        self.patterns.append(
            PatternGroup(
                name="stored_muxer",
                trace_pairs=[
                    TracePair(
                        regex=r"Stored muxer.*?muxer=(?P<peer_id>\w+\S+?):\S+\s+direction=(?P<direction>\w+)\s+peers=(?P<peers>\d+)",
                        convert=self._trace_stored_muxer,
                    ),
                ],
                query="Stored muxer",
            )
        )
        return self

    def with_peer_started_pattern(self) -> Self:
        self.patterns.append(
            PatternGroup(
                name="peer_started",
                trace_pairs=[
                    TracePair(
                        regex=r"(?:Peer|Hub) started.*?peerId=(?P<peer_id>\S+)",
                        convert=self._trace_peer_started,
                    ),
                ],
                query="started peerId",
            )
        )
        return self

    def with_dropping_peer_pattern(self) -> Self:
        self.patterns.append(
            PatternGroup(
                name="dropping_peer",
                trace_pairs=[
                    TracePair(
                        regex=r"Dropping peer.*?peerId=(?P<peer_id>\w+\S+)",
                        convert=self._trace_dropping_peer,
                    ),
                ],
                query="Dropping peer",
            )
        )
        return self

    def _trace_stored_muxer(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["peer_id", "direction", "peers"]
        if getattr(self, "extra_fields", None) is not None:
            columns.extend(self.extra_fields)
        df = pd.DataFrame(parsed_logs, columns=columns)
        if not df.empty:
            df["peers"] = pd.to_numeric(df["peers"], errors="coerce").fillna(0).astype(int)
        return df

    def _trace_dropping_peer(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["peer_id"]
        if getattr(self, "extra_fields", None) is not None:
            columns.extend(self.extra_fields)
        df = pd.DataFrame(parsed_logs, columns=columns)
        return df

    def _trace_peer_started(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["peer_id"]
        if getattr(self, "extra_fields", None) is not None:
            columns.extend(self.extra_fields)
        df = pd.DataFrame(parsed_logs, columns=columns)
        return df
