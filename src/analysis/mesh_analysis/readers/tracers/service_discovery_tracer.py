# Python Imports
from typing import List, Self

import pandas as pd

# Project Imports
from src.analysis.mesh_analysis.readers.tracers.message_tracer import MessageTracer, PatternGroup, TracePair


class ServiceDiscoveryTracer(MessageTracer):
    def with_extra_fields(self, extra_fields: List[str]) -> Self:
        self.extra_fields = extra_fields
        return self

    def with_starting_discovery_pattern(self) -> Self:
        self.patterns.append(
            PatternGroup(
                name="discovering_service",
                trace_pairs=[
                    TracePair(
                        regex=r'^NTC\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\+\d{2}:\d{2}).*?\bservice=([^\s]+)',
                        convert=self._extract_starting_discovery_time,
                    ),
                ],
                query="Lookup completed",
            )
        )
        return self

    def _extract_starting_discovery_time(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["starting_time", "service"]
        if getattr(self, "extra_fields", None) is not None:
            columns.extend(self.extra_fields)
        df = pd.DataFrame(parsed_logs, columns=columns)
        df["starting_time"] = pd.to_datetime(df["starting_time"], utc=True)

        return df
