import json
import logging
from types import SimpleNamespace

import pandas as pd
import pytest

from src.analysis.post_run.scenario_common import (
    POD_COLUMN,
    NoDeliveries,
    load_deliveries,
    load_mesh_peers,
    mesh_peers_row,
    prepare,
    published_messages,
    write_table,
)


def _mesh(rows, pods):
    """rows: list of per-pod value lists, one per snapshot."""
    return pd.DataFrame(
        rows,
        index=pd.to_datetime([f"2026-07-30 05:{15 + i}:00" for i in range(len(rows))]),
        columns=pods,
    )


def test_mesh_row_reports_the_last_snapshot():
    mesh = _mesh([[6, 6], [8, 4]], ["pod-0", "pod-1"])
    assert mesh_peers_row(mesh, "mesh peers")[2] == "median 6, range 4 to 8"


def test_mesh_row_skips_snapshots_taken_after_teardown():
    mesh = _mesh([[6, 6], [8, 4], [float("nan"), float("nan")]], ["pod-0", "pod-1"])
    assert mesh_peers_row(mesh, "mesh peers")[2] == "median 6, range 4 to 8"


def test_mesh_row_restricts_to_the_named_pods():
    mesh = _mesh([[1, 9]], ["pod-0", "pod-1"])
    assert mesh_peers_row(mesh, "mesh peers", pods=["pod-1"])[2] == "median 9, range 9 to 9"


def test_mesh_row_says_when_there_are_no_metrics():
    assert "no mesh-peers metrics in the run folder" in mesh_peers_row(None, "mesh peers")[2]
    mesh = _mesh([[6]], ["pod-0"])
    assert "no mesh-peers metrics for those pods" in mesh_peers_row(mesh, "m", pods=["pod-9"])[2]


def test_load_mesh_peers_returns_none_without_a_metrics_folder(tmp_path):
    assert load_mesh_peers(tmp_path) is None


def test_write_table_round_trips(tmp_path):
    out = write_table(tmp_path, "demo", [("delivery", "100%", "8 of 8")])
    assert out.exists()
    back = pd.read_csv(out)
    assert list(back.columns) == ["item", "expectation", "result"]
    assert back.iloc[0]["result"] == "8 of 8"


def test_load_deliveries_resolves_ordinal_and_publish_time(tmp_path):
    summary = tmp_path / "summary"
    summary.mkdir()
    pd.DataFrame(
        [
            {
                "msgId": 1,
                "sentAt": "2026-07-30 03:07:19.873477632",
                "delayMs": 7,
                POD_COLUMN: "pod-42",
            }
        ]
    ).to_csv(summary / "received.csv", index=False)
    df = load_deliveries(tmp_path)
    assert df.iloc[0]["ordinal"] == 42
    assert df.iloc[0]["sent"] == pd.Timestamp("2026-07-30 03:07:19.873477632")


class TestPublishedMessages:
    """Delivery must be scored against what left the publisher, not what we asked for."""

    def _experiment(self, tmp_path, events, configured=600):
        log = tmp_path / "events.log"
        log.write_text("".join(json.dumps(e) + "\n" for e in events))
        return SimpleNamespace(events_log_path=log, config=SimpleNamespace(num_messages=configured))

    def test_uses_what_the_publisher_actually_sent(self, tmp_path):
        exp = self._experiment(
            tmp_path, [{"event": "publish_summary", "attempted": 600, "failed": 3}]
        )
        assert published_messages(exp) == 597

    def test_a_clean_run_matches_the_configured_count(self, tmp_path):
        exp = self._experiment(
            tmp_path, [{"event": "publish_summary", "attempted": 600, "failed": 0}]
        )
        assert published_messages(exp) == 600

    def test_a_lost_publish_is_warned_about(self, tmp_path, caplog):
        exp = self._experiment(
            tmp_path, [{"event": "publish_summary", "attempted": 600, "failed": 3}]
        )
        with caplog.at_level(logging.WARNING):
            published_messages(exp)
        assert "3 of 600 publishes failed" in caplog.text

    def test_an_older_run_without_the_event_falls_back_and_says_so(self, tmp_path, caplog):
        exp = self._experiment(tmp_path, [{"event": "run_start"}])
        with caplog.at_level(logging.WARNING):
            assert published_messages(exp) == 600
        assert "No publish_summary event" in caplog.text


def test_prepare_refuses_a_run_with_no_deliveries(tmp_path, mocker):
    """An empty frame used to reach the tables and raise KeyError on a missing column."""
    mocker.patch("src.analysis.post_run.scenario_common.run_nimlibp2p_analysis")
    mocker.patch(
        "src.analysis.post_run.scenario_common.load_deliveries", return_value=pd.DataFrame()
    )
    exp = SimpleNamespace(output_folder=tmp_path, config=SimpleNamespace())
    with pytest.raises(NoDeliveries, match="No deliveries"):
        prepare(exp)
