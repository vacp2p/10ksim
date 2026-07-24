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
        """
        Log example: NTC 2026-07-02 15:51:34.010+00:00 starting interest for service topics="service-disco discoverer"
            tid=1 serviceId=key:936997257CBAD579BDB4590B1BE8B4D990AD3F81A6EE4162DCB399A6925F7107

        """
        self.patterns.append(
            PatternGroup(
                name="start_discovery",
                trace_pairs=[
                    TracePair(
                        regex=r'^NTC\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2}).*?\bserviceId=([^\s]+)',
                        convert=self._extract_starting_discovery_time,
                    ),
                ],
                query="starting interest for",
            )
        )
        return self

    def _extract_starting_discovery_time(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["starting_time", "serviceId"]
        if getattr(self, "extra_fields", None) is not None:
            columns.extend(self.extra_fields)
        df = pd.DataFrame(parsed_logs, columns=columns)
        df["starting_time"] = pd.to_datetime(df["starting_time"], utc=True)

        return df

    def with_found_peer_discovery_pattern(self) -> Self:
        """
        Log example: NTC 2026-07-02 15:51:34.015+00:00 found peer offering service topics="service-disco discoverer"
            tid=1 peerId=12D*a3Ub1R serviceId=key:936997257CBAD579BDB4590B1BE8B4D990AD3F81A6EE4162DCB399A6925F7107

        """
        self.patterns.append(
            PatternGroup(
                name="found_advertiser",
                trace_pairs=[
                    TracePair(
                        regex=r'^NTC\s+(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2})(?=.*\bpeerId=(?P<peerId>\S+))(?=.*\bserviceId=(?P<serviceId>\S+))',
                        convert=self._extract_found_peer_discovery_time,
                    ),
                ],
                query="found peer offering",
            )
        )
        return self

    def _extract_found_peer_discovery_time(self, parsed_logs: List) -> pd.DataFrame:
        columns = ["found_time", "peerId", "serviceId"]
        if getattr(self, "extra_fields", None) is not None:
            columns.extend(self.extra_fields)
        df = pd.DataFrame(parsed_logs, columns=columns)
        df["found_time"] = pd.to_datetime(df["found_time"], utc=True)

        return (
            df.sort_values("found_time", kind="mergesort")
            .drop_duplicates(subset=["peerId", "serviceId"], keep="first")
            .reset_index(drop=True)
        )
