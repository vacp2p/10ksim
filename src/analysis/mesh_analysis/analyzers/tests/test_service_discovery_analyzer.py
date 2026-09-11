import pandas as pd

from src.analysis.mesh_analysis.analyzers.service_discovery_analyzer import ServiceDiscoveryAnalyzer


class FakeDataPuller:
    kwargs = {
        "extra_fields": ["kubernetes.pod_name", "kubernetes.pod_node_name"],
        "stateful_sets": ["rare-discoverer"],
        "nodes_per_statefulset": [1],
    }

    def __init__(self, dfs):
        self.dfs = dfs

    def get_all_node_dataframes(self, tracer, stateful_sets, nodes_per_statefulset):
        return self.dfs


def test_discovery_analysis_returns_skipped_result_for_empty_data(tmp_path):
    raw_dfs = [
        {
            "start_discovery": [
                pd.DataFrame(
                    columns=[
                        "starting_time",
                        "serviceId",
                        "kubernetes.pod_name",
                        "kubernetes.pod_node_name",
                    ]
                )
            ],
            "found_advertiser": [
                pd.DataFrame(
                    columns=[
                        "found_time",
                        "peerId",
                        "serviceId",
                        "kubernetes.pod_name",
                        "kubernetes.pod_node_name",
                    ]
                )
            ],
        }
    ]

    results = (
        ServiceDiscoveryAnalyzer(dump_analysis_dir=tmp_path)
        .with_data_puller(FakeDataPuller(raw_dfs))
        .with_discovery_analysis()
        .run()
    )

    assert len(results) == 1
    assert results[0].name == "service_discovery"
    assert results[0].status == "skipped"
    assert results[0].intermediates["raw_dfs"] == raw_dfs


def test_get_trace_df_combines_all_dataframes_for_key(tmp_path):
    first_df = pd.DataFrame([{"serviceId": "chat1", "count": 1}])
    second_df = pd.DataFrame([{"serviceId": "chat2", "count": 2}])
    third_df = pd.DataFrame([{"serviceId": "chat3", "count": 3}])
    raw_dfs = [
        {"start_discovery": [first_df]},
        {"other_trace": [pd.DataFrame([{"serviceId": "ignored"}])]},
        {"start_discovery": [second_df, third_df]},
    ]

    result = ServiceDiscoveryAnalyzer(dump_analysis_dir=tmp_path)._get_trace_df(
        raw_dfs,
        "start_discovery",
    )

    assert result.to_dict("records") == [
        {"serviceId": "chat1", "count": 1},
        {"serviceId": "chat2", "count": 2},
        {"serviceId": "chat3", "count": 3},
    ]


def test_discovery_analysis_returns_latency_result(tmp_path, monkeypatch):
    start_df = pd.DataFrame(
        [
            {
                "starting_time": "2026-07-02 15:51:34.010+00:00",
                "serviceId": "chat1",
                "kubernetes.pod_name": "rare-discoverer-0",
                "kubernetes.pod_node_name": "node-a",
            }
        ]
    )
    found_df = pd.DataFrame(
        [
            {
                "found_time": "2026-07-02 15:51:34.015+00:00",
                "peerId": "12D3KooW",
                "serviceId": "chat1",
                "kubernetes.pod_name": "rare-discoverer-0",
                "kubernetes.pod_node_name": "node-a",
            }
        ]
    )
    raw_dfs = [{"start_discovery": [start_df], "found_advertiser": [found_df]}]
    monkeypatch.setattr(ServiceDiscoveryAnalyzer, "_plot_discovery_latency", lambda self, df: None)

    results = (
        ServiceDiscoveryAnalyzer(dump_analysis_dir=tmp_path)
        .with_data_puller(FakeDataPuller(raw_dfs))
        .with_discovery_analysis()
        .run()
    )

    assert len(results) == 1
    assert results[0].name == "service_discovery"
    assert results[0].status == "passed"
    discovery_df = results[0].intermediates["discovery_df"]
    assert discovery_df["elapsed_time"].tolist() == [5.0]
