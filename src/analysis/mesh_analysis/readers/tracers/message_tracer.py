# Python Imports
import logging
from typing import Callable, List, Optional, Self

import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TracePair(BaseModel):
    regex: Optional[str] = None
    convert: Callable[[List[str]], pd.DataFrame]


class PatternGroup(BaseModel):
    name: str
    fields: List[str] = Field(default_factory=lambda: ["_msg"])
    trace_pairs: List[TracePair]
    query: str


class MessageTracer(BaseModel):
    patterns: List[PatternGroup] = Field(default_factory=list)
    extra_fields: List[str] = Field(default_factory=list)

    def _trace_all_logs(self, parsed_logs: List) -> List:
        return parsed_logs

    def with_wildcard_pattern(self) -> Self:
        self.patterns.append(
            PatternGroup(
                name="wildcard",
                fields=["_msg"],
                trace_pairs=[TracePair(regex="(.*)", convert=self._trace_all_logs)],
                query="*",
            )
        )
        return self

    def trace(self, parsed_logs: List[List[tuple]]) -> dict[str, list[pd.DataFrame]]:
        """
        :type parsed_logs: List[List[List]]
        :param parsed_logs: List of groups of matched patterns.
        For example, for Waku logs, you might have 2 groups (received, sent),
        each having 3 trace_pairs, each containing lists representing matched regexs.
        """

        def convert_logs(pattern_group, log_group):
            return [pattern_group.trace_pairs[i].convert(log) for i, log in enumerate(log_group)]

        result = {
            pattern_group.name: convert_logs(pattern_group, log_group)
            for pattern_group, log_group in zip(self.patterns, parsed_logs)
        }
        return result
