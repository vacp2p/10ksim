# Python Imports
from pathlib import Path

# Project Imports
import src.logger.logger
from src.mesh_analysis.analyzers.nimlibp2p_analyzer import Nimlibp2pAnalyzer
from src.mesh_analysis.analyzers.waku import waku_plots
from src.mesh_analysis.analyzers.waku.waku_analyzer import WakuAnalyzer



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
    log_analyzer = WakuAnalyzer(dump_analysis_dir='local_data/simulations_data/refactor_nimlibp2p/',
                                # local_folder_to_analyze='local_data/simulations_data/waku_simu3/log/',
                                **stack)
    log_analyzer.analyze_reliability(n_jobs=4)
    log_analyzer.check_store_messages()
    log_analyzer.check_filter_messages()

    waku_plots.plot_message_distribution(Path('local_data/simulations_data/refactor/summary/received.csv'),
                                         'Title',
                                         Path('local_data/simulations_data/refactor/plot.png'))
    stack = {'type': 'vaclab',
             'url': 'https://vmselect.riff.cc/select/logsql/query',
             'start_time': '2025-06-04T17:10:00',
             'end_time': '2025-06-04T17:30:00',
             'reader': 'victoria',
             'stateful_sets': ['pod'],
             'nodes_per_statefulset': [10],
             'container_name': 'container-0',
             'extra_fields': ['kubernetes.pod_name', 'kubernetes.pod_node_name']
             }
    log_analyzer = Nimlibp2pAnalyzer(dump_analysis_dir='local_data/simulations_data/refactor_nimlibp2p/',
                                # local_folder_to_analyze='local_data/simulations_data/waku_simu3/log/',
                                **stack)
    log_analyzer.analyze_reliability(n_jobs=4)
    waku_plots.plot_message_distribution_libp2pmix(Path('local_data/simulations_data/refactor_nimlibp2p/summary/received.csv'),
                                         'Title',
                                         Path('local_data/simulations_data/refactor_nimlibp2p/plot.png'))
