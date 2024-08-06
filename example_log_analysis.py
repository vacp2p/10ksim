# Python Imports

# Project Imports
import src.logger.logger
from src.mesh_analysis.waku_message_log_analyzer import WakuMessageLogAnalyzer


if __name__ == '__main__':
    # Timestamp of the simulation
    timestamp = "[2024-08-05T15:45:00, 2024-08-05T15:49:00]"
    # Example of data analysis from cluster
    # log_analyzer = WakuMessageLogAnalyzer(timestamp, dump_analysis_dir='test_logs_victoria')
    # Example of data analysis from local
    log_analyzer = WakuMessageLogAnalyzer(local_folder_to_analyze='data', dump_analysis_dir='test_logs_victoria')

    log_analyzer.analyze_message_logs()
    log_analyzer.analyze_message_timestamps(time_difference_threshold=2)
