from pathlib import Path

import pandas as pd

from src.analysis.metrics.libp2p.gossipsub_summary import (
    GOSSIPSUB_DETAIL,
    summarize,
    summary_table,
)
from src.analysis.metrics.libp2p.metrics import gossipsub_detail_metrics
from src.analysis.metrics.libp2p.scrape import Nimlibp2pScrapeBuilder


def _write_counter_csv(metrics_dir: Path, folder: str, name: str, columns: dict) -> None:
    """One dumped counter CSV: a Time column + one cumulative-counter column per pod."""
    d = metrics_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame({"Time": ["2026-07-18 04:40:00", "2026-07-18 04:45:00"], **columns})
    df.to_csv(d / name, index=False)


# --------------------------------------------------------------------------- #
# summarize  (per-node totals -> across-node medians + duplicate ratio)
# --------------------------------------------------------------------------- #
class TestSummarize:
    def _fixture(self, tmp_path: Path) -> Path:
        _write_counter_csv(
            tmp_path,
            "gossipsub/received",
            "mplex",
            {
                "pod-0": [100, 600],
                "pod-1": [90, 590],
                # not relays: must not affect the medians
                "bootstrap-0": [5000, 9999],
                "pod-api-requester-0": [1, 1],
            },
        )
        _write_counter_csv(
            tmp_path, "gossipsub/duplicate", "mplex", {"pod-0": [0, 1500], "pod-1": [0, 1180]}
        )
        # pod-1's last sample is missing -> the previous value is its total
        _write_counter_csv(
            tmp_path, "gossipsub/graft-sent", "mplex", {"pod-0": [10, 50], "pod-1": [40, None]}
        )
        return tmp_path

    def test_median_of_per_node_last_values(self, tmp_path):
        summary = summarize(self._fixture(tmp_path), "mplex")
        assert summary["messages received"] == 595.0  # median(600, 590)
        assert summary["duplicate messages"] == 1340.0  # median(1500, 1180)

    def test_non_relay_columns_are_excluded(self, tmp_path):
        # bootstrap-0 / pod-api-requester-0 values would drag the median far off 595
        summary = summarize(self._fixture(tmp_path), "mplex")
        assert summary["messages received"] == 595.0

    def test_missing_last_sample_falls_back_to_previous_value(self, tmp_path):
        summary = summarize(self._fixture(tmp_path), "mplex")
        assert summary["GRAFT sent"] == 45.0  # median(50, ffilled 40)

    def test_duplicate_ratio_is_median_of_per_node_ratios(self, tmp_path):
        summary = summarize(self._fixture(tmp_path), "mplex")
        assert summary["duplicate ratio"] == 2.25  # median(1500/600, 1180/590)

    def test_missing_metric_folders_are_skipped(self, tmp_path):
        summary = summarize(self._fixture(tmp_path), "mplex")
        assert "IWANT sent" not in summary  # folder never written
        assert "IHAVE received" not in summary

    def test_empty_dir_gives_empty_summary(self, tmp_path):
        assert summarize(tmp_path, "mplex") == {}

    def test_zero_received_nodes_are_excluded_from_the_ratio(self, tmp_path):
        _write_counter_csv(
            tmp_path, "gossipsub/received", "mplex", {"pod-0": [0, 0], "pod-1": [0, 100]}
        )
        _write_counter_csv(
            tmp_path, "gossipsub/duplicate", "mplex", {"pod-0": [0, 50], "pod-1": [0, 300]}
        )
        summary = summarize(tmp_path, "mplex")
        assert summary["duplicate ratio"] == 3.0  # only pod-1 counts (pod-0 received nothing)


# --------------------------------------------------------------------------- #
# summary_table  (muxer-by-metric medians)
# --------------------------------------------------------------------------- #
class TestSummaryTable:
    def test_muxer_columns_and_canonical_row_order(self, tmp_path):
        for muxer, received in [("mplex", [10, 100]), ("yamux", [20, 200])]:
            _write_counter_csv(
                tmp_path, "gossipsub/received", muxer, {"pod-0": received, "pod-1": received}
            )
        table = summary_table(tmp_path, ["mplex", "yamux"])
        assert list(table.columns) == ["mplex", "yamux"]
        assert list(table.index) == list(GOSSIPSUB_DETAIL.values()) + ["duplicate ratio"]
        assert table.loc["messages received", "mplex"] == 100.0
        assert table.loc["messages received", "yamux"] == 200.0
        # metrics with no dumped CSV stay empty rather than erroring
        assert table.loc["IWANT sent"].isna().all()


# --------------------------------------------------------------------------- #
# gossipsub_detail_metrics + the scrape-builder flag
# --------------------------------------------------------------------------- #
class TestGossipsubDetailMetrics:
    def test_counters_are_summed_by_pod_in_the_namespace(self):
        metrics = list(gossipsub_detail_metrics("zerotesting"))
        assert len(metrics) == 10
        for m in metrics:
            assert m.query.startswith("sum by (pod) (")
            assert "namespace='zerotesting'" in m.query
            assert m.extract_field == "pod"
            assert m.folder_name.startswith("gossipsub/")
        assert len({m.folder_name for m in metrics}) == 10  # one folder per counter

    def test_received_and_duplicate_counters_present(self):
        queries = [m.query for m in gossipsub_detail_metrics("ns")]
        assert any("libp2p_gossipsub_received_total" in q for q in queries)
        assert any("libp2p_gossipsub_duplicate_total" in q for q in queries)

    def test_builder_flag_adds_the_detail_metrics(self):
        def build(with_detail: bool):
            builder = Nimlibp2pScrapeBuilder(namespace="zerotesting").with_interval(
                "2026-07-18T04:38:57", "2026-07-18T04:45:28", "mplex"
            )
            if with_detail:
                builder = builder.with_gossipsub_detail_metrics()
            return builder.build()

        detail_folders = {m.folder_name for m in gossipsub_detail_metrics("zerotesting")}
        assert {m.folder_name for m in build(True).metrics_to_scrape} == detail_folders
        assert not {m.folder_name for m in build(False).metrics_to_scrape} & detail_folders
