import pandas as pd

from src.analysis.post_run.scenario_common import (
    POD_COLUMN,
    load_deliveries,
    load_mesh_peers,
    mesh_peers_row,
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
