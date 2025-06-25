# Python Imports
import logging
import os
from pathlib import Path

# Project Imports
import src.logger.logger
from src.mesh_analysis.analyzers.nimlibp2p_analyzer import Nimlibp2pAnalyzer
from src.mesh_analysis.analyzers.waku import waku_plots
from src.mesh_analysis.analyzers.waku.waku_analyzer import WakuAnalyzer


if __name__ == "__main__":
    stack = {
        "type": "vaclab",
        "url": "https://vlselect.vaclab.org/select/logsql/query",
        "start_time": "2025-06-23T18:36:44",
        "end_time": "2025-06-23T18:59:09",
        #  'start_time': '2025-06-22T18:36:44',
        #  'end_time': '2025-06-24T23:59:09',
        "reader": "victoria",
        "stateful_sets": ["nodes-0"],
        "nodes_per_statefulset": [1000],
        "container_name": "waku",
        "extra_fields": ["kubernetes.pod_name", "kubernetes.pod_node_name"],
    }

    data = [

        ("2025-06-23T18:36:44", "2025-06-23T18:59:09", "local_data/simulations_data/1k_1s_1KB/v0.36.0-rc.0/", 1000),
        ("2025-06-23T19:01:04", "2025-06-23T20:21:38", "local_data/simulations_data/1k_5s_1KB/v0.36.0-rc.0/", 1000),
        ("2025-06-23T20:22:57", "2025-06-23T22:32:38", "local_data/simulations_data/1k_10s_1KB/v0.36.0-rc.0/", 1000),
        ("2025-06-23T22:35:15", "2025-06-23T23:09:16", "local_data/simulations_data/2k_1s_1KB/v0.36.0-rc.0/", 2000),
        ("2025-06-23T23:08:20", "2025-06-24T00:21:30", "local_data/simulations_data/2k_5s_1KB/v0.36.0-rc.0/", 2000),
        ("2025-06-24T00:19:33", "2025-06-24T02:29:44", "local_data/simulations_data/2k_10s_1KB/v0.36.0-rc.0/", 2000),
        ("2025-06-25T09:48:46", "2025-06-25T10:19:22", "local_data/simulations_data/3k_1s_1KB/v0.36.0-rc.0/", 3000),
        ("2025-06-25T10:21:04", "2025-06-25T11:31:33", "local_data/simulations_data/3k_5s_1KB/v0.36.0-rc.0/", 3000),
        ("2025-06-25T11:32:09", "2025-06-25T13:35:01", "local_data/simulations_data/3k_10s_1KB/v0.36.0-rc.0/", 3000),

    ]

    for start, end, path, num_nodes in data:
        if not os.path.exists(os.path.join(path, "summary")):
            print("data summary DNE. create it.")
            stack["start_time"] = start
            stack["end_time"] = end
            stack["nodes_per_statefulset"] = [num_nodes]
            print(f"gen: [{start}, {end}] {path}")
            log_analyzer = WakuAnalyzer(dump_analysis_dir=path,
                                        **stack)
            log_analyzer.analyze_reliability(n_jobs=6)

    for start, end, path in data:
        waku_plots.plot_message_distribution(
            Path(path) / "summary" / "received.csv",
            "Title",
            Path(path) / "plot.png",
        )


    # log_analyzer = WakuAnalyzer(dump_analysis_dir='local_data/simulations_data/refactor_nimlibp2p/',
    #                             local_folder_to_analyze='local_data/simulations_data/refactor_nimlibp2p/',
    #                             # local_folder_to_analyze='local_data/simulations_data/waku_simu3/log/',
    #                             **stack)
    # log_analyzer.analyze_reliability(n_jobs=6)
    # log_analyzer.check_store_messages()
    # log_analyzer.check_filter_messages()

    # waku_plots.plot_message_distribution(
    #     Path("local_data/simulations_data/refactor_nimlibp2p/summary/received.csv"),
    #     "Title",
    #     Path("local_data/simulations_data/refactor_nimlibp2p/plot.png"),
    # )

    # stack = {'type': 'vaclab',
    #          'url': 'https://vmselect.riff.cc/select/logsql/query',
    #          'start_time': '2025-06-04T17:10:00',
    #          'end_time': '2025-06-04T17:30:00',
    #          'reader': 'victoria',
    #          'stateful_sets': ['pod'],
    #          'nodes_per_statefulset': [10],
    #          'container_name': 'container-0',
    #          'extra_fields': ['kubernetes.pod_name', 'kubernetes.pod_node_name']
    #          }
    # log_analyzer = Nimlibp2pAnalyzer(dump_analysis_dir='local_data/simulations_data/refactor_nimlibp2p/',
    #                             # local_folder_to_analyze='local_data/simulations_data/waku_simu3/log/',
    #                             **stack)
    # log_analyzer.analyze_reliability(n_jobs=4)
    # waku_plots.plot_message_distribution_libp2pmix(Path('local_data/simulations_data/refactor_nimlibp2p/summary/received.csv'),
    #                                      'Title',
    #                                      Path('local_data/simulations_data/refactor_nimlibp2p/plot.png'))
