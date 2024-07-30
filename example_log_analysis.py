# Python Imports
import pandas as pd
import src.logger.logger
from pathlib import Path
from result import Ok, Err

from src.mesh_analysis.waku_message_log_analyzer import WakuMessageLogAnalyzer
# Project Imports
from src.mesh_analysis.readers.victoria_reader import VictoriaReader
from src.mesh_analysis.tracers.waku_tracer import WakuTracer
from src.utils import file_utils


if __name__ == '__main__':
    # Timestamp of the simulation
    timestamp = "[2024-07-30T08:57:00, 2024-07-30T09:02:00]"

    log_analyzer = WakuMessageLogAnalyzer(timestamp, 'test_logs_victoria')
    log_analyzer.analyze_message_logs()
