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
from src.mesh_analysis.analyzers.waku.data_puller import DataPuller
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



class AnalysisResult(BaseModel):
    name: str
    intermediates: dict
    status: Literal["passed", "failed", "skipped", "error"]

    def get_metric(self, metric) -> Optional[object]:
        return self.intermediates.get(metric, None)


OnFail = Literal["stop", "continue"]


class AnalysisStep(BaseModel):
    name: str
    action: Callable[[], AnalysisResult]
    on_fail: OnFail = "continue"
    kwargs: Optional[dict]

    def run(self) -> AnalysisResult:
        try:
            logger.info(f"Running {self.name}")
            return self.action(**self.kwargs)
        except Exception as e:
            full_trace = traceback.format_exc()
            logger.error(f"exception: {e}\n{full_trace}")
            return AnalysisResult(
                name=self.name,
                intermediates={"error": e, "trace": full_trace},
                status="error",
            )


class Analyzer(BaseModel):
    _analysis: List[AnalysisStep] = []
    data_puller: Optional[DataPuller] = None
    dump_analysis_dir: Optional[str] = None

    def run(self) -> List[AnalysisResult]:
        self._set_up_paths()
        results = []
        for analysis in self._analysis:
            result = analysis.run()
            if result.status in ["error", "fail"] and analysis.on_fail != "continue":
                dump = json.dumps(result.model_dump(indent=False), indent=2)
                raise ValueError(f"Analysis failed. {dump}")
            results.append(result)

        return results

    def _with_parameterized_check(
        self,
        func,
        *,
        name: Optional[str] = None,
        on_fail: OnFail = "continue",
        **params,
    ) -> Self:
        if name is None:
            name = func.__name__
        func = partial(func, **params)
        self._analysis.append(
            AnalysisStep(name=name, action=func, kwargs=params, on_fail=on_fail)
        )
        return self

    def with_dump_analysis_dir(self, dump_analysis_dir: str = None) -> Self:
        self.dump_analysis_dir = dump_analysis_dir
        return self

    def with_kwargs(self, kwargs: dict) -> Self:
        self._kwargs = kwargs
        return self

    def with_data_puller(self, data_puller: DataPuller) -> Self:
        self.data_puller = data_puller
        return self

    def with_test_analysis(self, params: dict, *, on_fail: OnFail = "continue") -> Self:
        # TODO: remove this - just for testing
        self._analysis.append(
            AnalysisStep(
                name="test",
                action=lambda: params["answer"] == 42,
                kwargs=params,
                on_fail=on_fail,
            )
        )
        return self

    def with_test_analysis_2(
        self, params: dict, *, on_fail: OnFail = "continue"
    ) -> Self:
        # TODO: remove this - just for testing
        self._analysis.append(
            AnalysisStep(
                name="test",
                action=lambda input: self.data_puller == 42,
                kwargs=params,
                on_fail=on_fail,
            )
        )
        return self

    def _set_up_paths(self):
        try:
            self._dump_analysis_path = (
                Path(self.dump_analysis_dir) if self.dump_analysis_dir else None
            )
            result = path_utils.prepare_path_for_folder(self._dump_analysis_path)
            if result.is_err():
                logger.error(result.err_value)
                exit(1)
        except Exception as e:
            logger.error(f"TODO: handle this: {e}")
