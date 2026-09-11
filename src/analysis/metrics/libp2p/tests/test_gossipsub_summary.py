import logging

import pandas as pd
import pytest

from src.analysis.metrics.libp2p import gossipsub_summary as gs


def _write(metrics_dir, folder, muxer, rows):
    """rows: list of per-pod value lists, one per snapshot."""
    path = metrics_dir / folder
    path.mkdir(parents=True, exist_ok=True)
    times = pd.to_datetime([f"2026-08-08 01:{m:02d}:00" for m in range(len(rows))])
    pd.DataFrame(rows, index=times, columns=["pod-0", "pod-1"]).rename_axis("Time").to_csv(
        path / f"{muxer}.csv"
    )


def test_counter_uses_the_last_value(tmp_path):
    """Counters only accumulate, so the total over the run is the final sample."""
    _write(tmp_path, "gossipsub/graft-sent", "mux", [[1, 1], [7, 9], [12, 20]])
    assert gs._per_node_values(tmp_path, "gossipsub/graft-sent", "mux").tolist() == [12, 20]


def test_gauge_uses_the_median_not_the_last_value(tmp_path):
    """A gauge falls back after traffic stops; the last sample is the idle value, which
    is how quic came to be reported at 27 connections instead of 250."""
    _write(tmp_path, "connections", "mux", [[250, 250], [250, 250], [250, 250], [28, 28]])
    assert gs._per_node_values(tmp_path, "connections", "mux").tolist() == [250, 250]


@pytest.mark.parametrize("folder", ["mesh-peers", "topic-peers", "connections"])
def test_every_gauge_is_treated_as_one(folder, tmp_path):
    _write(tmp_path, folder, "mux", [[8, 8], [8, 8], [0, 0]])
    assert gs._per_node_values(tmp_path, folder, "mux").tolist() == [8, 8]


def test_warns_when_the_window_runs_well_past_the_traffic(tmp_path, caplog):
    """Half the window idle drags the median below the value under load, and the result
    still looks plausible, so it has to say so."""
    _write(tmp_path, "connections", "mux", [[250, 250], [250, 250], [20, 20], [20, 20]])
    with caplog.at_level(logging.WARNING):
        gs._per_node_values(tmp_path, "connections", "mux")
    assert "runs past the traffic" in caplog.text


def test_quiet_when_the_window_is_mostly_traffic(tmp_path, caplog):
    _write(tmp_path, "connections", "mux", [[250, 250]] * 9 + [[20, 20]])
    with caplog.at_level(logging.WARNING):
        gs._per_node_values(tmp_path, "connections", "mux")
    assert "runs past the traffic" not in caplog.text


def test_counters_never_warn_even_though_they_jump(tmp_path, caplog):
    """A counter starting at zero is not a collapsed gauge."""
    _write(tmp_path, "gossipsub/ihave-recv", "mux", [[0, 0], [0, 0], [900, 900]])
    with caplog.at_level(logging.WARNING):
        gs._per_node_values(tmp_path, "gossipsub/ihave-recv", "mux")
    assert "runs past the traffic" not in caplog.text


def test_missing_metric_is_skipped_not_fatal(tmp_path):
    assert gs._per_node_values(tmp_path, "connections", "mux") is None


def test_summary_reports_gauges_and_counters_together(tmp_path):
    _write(tmp_path, "connections", "mux", [[250, 250], [250, 250], [28, 28]])
    _write(tmp_path, "gossipsub/graft-sent", "mux", [[10, 10], [20, 20], [30, 30]])
    summary = gs.summarize(tmp_path, "mux")
    assert summary["connections"] == 250.0
    assert summary["GRAFT sent"] == 30.0
