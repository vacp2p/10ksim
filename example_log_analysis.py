# Python Imports

# Project Imports
import src.logger.logger
from src.mesh_analysis.waku_message_log_analyzer import WakuMessageLogAnalyzer


if __name__ == '__main__':
    # Timestamp of the simulation
    timestamp = "[2024-08-14T11:11:00, 2024-08-14T12:05:00]"
    # Example of data analysis from cluster
    log_analyzer = WakuMessageLogAnalyzer(2, timestamp, dump_analysis_dir='local_data/shard_tests/')
    # Example of data analysis from local
    # log_analyzer = WakuMessageLogAnalyzer(local_folder_to_analyze='lpt_duptest_debug', dump_analysis_dir='lpt_duptest_debug/notion')

    log_analyzer.analyze_message_logs(True)
    log_analyzer.check_store_messages()
    log_analyzer.analyze_message_timestamps(time_difference_threshold=2)
