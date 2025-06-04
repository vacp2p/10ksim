# Python Imports
from pathlib import Path

# Project Imports
import src.logger.logger
from src.mesh_analysis.analyzers.waku import waku_plots
from src.mesh_analysis.analyzers.waku.waku_analyzer import WakuAnalyzer
from src.mesh_analysis.analyzers.waku.waku_plots import plot_message_distribution


if __name__ == '__main__':
    stack = {'type': 'vaclab',
             'url': 'https://vmselect.riff.cc/select/logsql/query',
             'start_time': '2025-05-26T13:10:00',
             'end_time': '2025-05-26T13:15:00',
             'reader': 'victoria',
             'stateful_sets': ['nodes-0'],
             'nodes_per_statefulset': [50],
             'container_name': 'waku',
             'extra_fields': ['kubernetes.pod_name', 'kubernetes.pod_node_name']
             }
    log_analyzer = WakuAnalyzer(dump_analysis_dir='local_data/simulations_data/refactor/',
                                # local_folder_to_analyze='local_data/simulations_data/waku_simu3/log/',
                                **stack)

    log_analyzer.analyze_reliability(n_jobs=4)
    log_analyzer.check_store_messages()
    log_analyzer.check_filter_messages()

    waku_plots.plot_message_distribution(Path('local_data/simulations_data/refactor/summary/received.csv'),
                                         'Title',
                                         Path('local_data/simulations_data/refactor/plot.png'))

