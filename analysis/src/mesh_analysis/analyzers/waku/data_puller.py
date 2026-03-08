# Python Imports
from functools import partial
import ast
import base64
import json
import logging
import traceback
import pandas as pd
from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt
import seaborn as sns
from pathlib import Path
from typing import Callable, ClassVar, Dict, List, Literal, Self, Tuple, Optional, Type
from result import Ok, Err, Result

# Project Imports
from src.mesh_analysis.stacks.file_stack_analysis import FileStack
from src.mesh_analysis.readers.reader import Reader
from src.mesh_analysis.readers.tracers.message_tracer import MessageTracer
from src.mesh_analysis.stacks.stack_analysis import StackAnalysis
from src.mesh_analysis.readers.builders.victoria_reader_builder import (
    VictoriaReaderBuilder,
)
from src.mesh_analysis.readers.file_reader import FileReader
from src.mesh_analysis.readers.tracers.waku_tracer import (
    NewTracer,
    NewWakuTracer,
    WakuTracer,
)
from src.mesh_analysis.stacks.vaclab_stack_analysis import VaclabStackAnalysis
from src.utils import file_utils, path_utils, list_utils

logger = logging.getLogger(__name__)
sns.set_theme()



class DataPuller(BaseModel):
    kwargs: dict = Field(default_factory=lambda: {})
    _reader_builder_cls: ClassVar[Type[Reader]]
    _stack_cls: ClassVar[Type[StackAnalysis]]
    _source_type: str
    _local_folder: Optional[str] = None
    _jobs: PositiveInt = 6

    def with_local(self, folder: str) -> Self:
        self._local_folder = folder
        self._source_type = "local"
        return self

    def is_local(self) -> bool:
        return self._source_type == "local"

    def with_kwargs(self, kwargs: dict) -> Self:
        self.kwargs = kwargs
        if "url" in kwargs.keys():
            self._source_type = "victoria"
        elif "local_folder" in kwargs.keys():
            self.with_local(kwargs["local_folder"])
        return self

    def with_source_type(self, source: Literal["victoria", "local"]) -> Self:
        self._source_type = source
        return self

    def _make_stack_new(self, tracer: NewTracer) -> StackAnalysis:
        queries = [pattern.query for pattern in tracer.patterns]
        # TODO: Change to only pass tracer and make VictoriaReaderBuilder use tracer.pattern queries itself.
        reader_builder = VictoriaReaderBuilder(
            tracer=tracer,
            queries=queries,
            kwargs=self.kwargs,
            extra_fields=self.kwargs["extra_fields"],
        )
        return VaclabStackAnalysis(reader_builder)

    def _make_stack(self, tracer: MessageTracer, queries) -> StackAnalysis:
        _reader_builder_cls = VictoriaReaderBuilder
        _stack_cls = VaclabStackAnalysis
        if isinstance(queries, str):
            queries = [queries]
        reader_builder = _reader_builder_cls(
            tracer=tracer, queries=queries, kwargs=self.kwargs
        )
        return _stack_cls(reader_builder)

    def get_all_node_dataframes_new(
        self,
        tracer: NewTracer,
        # TODO: put in DataPuller as var, but exclude from ss_check (has pull settings that clash with that check)
        stateful_sets: List[str],
        nodes_per_ss: List[NonNegativeInt],
    ) -> dict:
        if self._source_type == "victoria":
            stack = self._make_stack_new(tracer)
            return stack.get_all_node_dataframes(
                stateful_sets, nodes_per_ss, self._jobs
            )
        elif self._source_type == "local":
            puller = FileReader(self._local_folder, tracer, self._jobs)
            dfs = puller.get_dataframes()
            return dfs
        raise NotImplementedError()

    def get_all_node_dataframes(
        self, tracer: MessageTracer, queries: Optional[str] = None
    ):
        if self._source_type == "victoria":
            stack = self._make_stack(tracer, queries)
            return stack.get_all_node_dataframes(self._jobs)
        elif self._source_type == "local":
            puller = FileReader(self._local_folder, tracer, self._jobs)
            return puller.get_dataframes()
        raise NotImplementedError()

    def get_pod_logs(self, tracer, pod_identifier: str, query: str):
        if self._source_type == "victoria":
            stack = self._make_stack(tracer, query)
            return stack.get_all_node_dataframes(self._jobs)
        raise NotImplementedError()

    def get_number_nodes(self, stateful_sets: List[str]) -> List[int]:
        if self._source_type == "victoria":
            tracer = WakuTracer().with_wildcard_pattern()
            stack = self._make_stack(tracer, "*")
            return stack.get_number_nodes(stateful_sets)
        elif self._source_type == "local":
            tracer = WakuTracer().with_wildcard_pattern()
            puller = FileReader(self._local_folder, tracer, self._jobs)
            stack = FileStack(reader=puller)
            return stack.get_number_nodes(stateful_sets)
        raise NotImplementedError()