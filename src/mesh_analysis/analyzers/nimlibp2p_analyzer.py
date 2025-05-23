# Python Imports
import logging
from typing import Optional

# Project Imports
from src.mesh_analysis.monitoring_clients.monitoring_client import MonitoringClient
from src.mesh_analysis.tracers.waku_tracer import WakuTracer
from src.mesh_analysis.stacks.stack_analysis import StackAnalysis
from src.mesh_analysis.stacks.vaclab_stack_analysis import VaclabStackAnalysis

logger = logging.getLogger(__name__)


class Nimlibp2pAnalyzer:
    def __init__(self, dump_analysis_dir: str = None, local_folder_to_analyze: str = None, **kwargs):
        # self._set_up_paths(dump_analysis_dir, local_folder_to_analyze)
        self._kwargs = kwargs
        self._stack: Optional[StackAnalysis] = self._set_up_stack()


    def _set_up_stack(self):
        if self._kwargs is None:
            return None

        dispatch = {
            'vaclab': VaclabStackAnalysis,
            # 'local': LocalStackAnalaysis # TODO
        }

        return dispatch[type](**self._kwargs)