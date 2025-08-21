# Python Imports
from pathlib import Path

# Project Imports
import src.logger.logger
from src.mesh_analysis.analyzers.nimlibp2p_analyzer import Nimlibp2pAnalyzer
from src.mesh_analysis.analyzers.waku import waku_plots
from src.mesh_analysis.analyzers.waku.waku_analyzer import WakuAnalyzer
from src.mesh_analysis.analyzers.waku.waku_plots import plot_message_distribution


if __name__ == '__main__':

    stack = {'type': 'vaclab',
             'url': 'https://vlselect.vaclab.org/select/logsql/query',
             'start_time': '2025-06-19T09:14:00',
             'end_time': '2025-06-19T09:17:00',
             'reader': 'victoria',
             'stateful_sets': ['pod'],
             'nodes_per_statefulset': [10],
             'container_name': 'container-0',
             'extra_fields': ['kubernetes.pod_name', 'kubernetes.pod_node_name']
             }
    log_analyzer = Nimlibp2pAnalyzer(dump_analysis_dir='local_data/simulations_data/mix_intermediate/',
                                # local_folder_to_analyze='local_data/simulations_data/waku_simu3/log/',
                                **stack)
    log_analyzer.analyze_mix_trace(n_jobs=4)


    """
    kubernetes_container_name:waku AND _time:[2024-08-28T12:51:00, 2024-08-28T12:59:00] | sort by (_time)
    "my_peer_id=16U*3qQbxY" AND _time:[2024-08-05T15:45:00, 2024-08-05T15:49:00] | sort by (_time)
    kubernetes_container_name:waku AND _time:[2024-08-26T17:31:00, 2024-08-26T18:19:00] AND kubernetes_pod_name:nodes-204
    """
