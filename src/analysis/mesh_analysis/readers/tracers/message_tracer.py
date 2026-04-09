# Python Imports
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Self, Tuple

import pandas as pd
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


@dataclass
class TracePair:
    regex: str
    convert: Callable[[List[str]], pd.DataFrame]


@dataclass
class PatternGroup:
    name: str
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
                "wildcard",
                [TracePair(regex="(.*)", convert=self._trace_all_logs)],
                query="*",
            )
        )
        return self

    def trace(self, parsed_logs: List[List[Tuple]]) -> Dict[str, List[pd.DataFrame]]:
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
