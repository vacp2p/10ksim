from pathlib import Path

import pandas as pd

from src.analysis.metrics.libp2p.gossipsub_summary import GOSSIPSUB_DETAIL, summarize
from src.analysis.metrics.libp2p.metrics import (
    connections,
    gossipsub_mesh_peers,
    gossipsub_topic_peers,
    libp2p_metrics,
)


def _write_gauge_csv(metrics_dir: Path, folder: str, name: str, columns: dict) -> None:
    d = metrics_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"Time": ["2026-07-18 04:40:00", "2026-07-18 04:45:00"], **columns})
    df.to_csv(d / name, index=False)


# --------------------------------------------------------------------------- #
# mesh-health gauges
# --------------------------------------------------------------------------- #
class TestMeshMetrics:
    def test_gauges_are_pod_keyed_in_the_namespace(self):
        for m in (
            gossipsub_mesh_peers("zerotesting"),
            gossipsub_topic_peers("zerotesting"),
            connections("zerotesting"),
        ):
            assert m.query.startswith("sum by (pod) (")
            assert "namespace='zerotesting'" in m.query
            assert m.extract_field == "pod"

    def test_gauge_sources_and_folders(self):
        assert "libp2p_gossipsub_peers_per_topic_mesh" in gossipsub_mesh_peers("ns").query
        assert "libp2p_gossipsub_peers_per_topic_gossipsub" in gossipsub_topic_peers("ns").query
        assert "libp2p_peers" in connections("ns").query
        assert gossipsub_mesh_peers("ns").folder_name == "mesh-peers/"
        assert gossipsub_topic_peers("ns").folder_name == "topic-peers/"
        assert connections("ns").folder_name == "connections/"

    def test_gauges_are_part_of_the_standard_libp2p_set(self):
        folders = {m.folder_name for m in libp2p_metrics("ns")}
        assert {"mesh-peers/", "topic-peers/", "connections/"} <= folders


# --------------------------------------------------------------------------- #
# summary integration: gauges reduce by last value
# --------------------------------------------------------------------------- #
class TestMeshSummary:
    def test_summarize_reports_end_of_run_state(self, tmp_path):
        # unlike counters, gauges can fall: pod-0 goes 8 -> 2
        _write_gauge_csv(tmp_path, "mesh-peers", "mplex", {"pod-0": [8, 2], "pod-1": [8, 8]})
        _write_gauge_csv(tmp_path, "connections", "mplex", {"pod-0": [250, 20], "pod-1": [250, 24]})
        summary = summarize(tmp_path, "mplex")
        assert summary["mesh peers"] == 5.0  # median(2, 8)
        assert summary["connections"] == 22.0  # median(20, 24)

    def test_mesh_health_leads_the_table_order(self):
        labels = list(GOSSIPSUB_DETAIL.values())
        assert labels[:3] == ["mesh peers", "topic peers", "connections"]
