from src.analysis.metrics.shadow_metrics import (
    RECEIVED_METRIC,
    STABLE_END_SHIFT,
    STABLE_START_SHIFT,
    first_delivery_snapshot,
    last_delivery_snapshot,
    settled_window,
)


def _snap(received: float) -> str:
    return f"# HELP process_info CPU and memory usage\nlibp2p_peers 42.0\n{RECEIVED_METRIC} {received}\n"


def _peer(counts):
    return ("pod-0", [_snap(c) for c in counts])


def test_finds_the_snapshot_where_delivery_starts():
    assert first_delivery_snapshot([_peer([0, 0, 0, 5, 9])]) == 3


def test_takes_the_earliest_peer_to_receive():
    peers = [
        ("pod-0", [_snap(c) for c in [0, 0, 0, 4]]),
        ("pod-1", [_snap(c) for c in [0, 2, 3, 4]]),
    ]
    assert first_delivery_snapshot(peers) == 1


def test_none_when_nothing_is_ever_delivered():
    assert first_delivery_snapshot([_peer([0, 0, 0])]) is None


def test_handles_peers_with_different_snapshot_counts():
    peers = [("pod-0", [_snap(0)]), ("pod-1", [_snap(c) for c in [0, 0, 7]])]
    assert first_delivery_snapshot(peers) == 2


def test_no_peers_at_all():
    assert first_delivery_snapshot([]) is None


def _info(first, start=1000, last=1180):
    return {"start_epoch_s": start, "last_epoch_s": last, "first_delivery_epoch_s": first}


def test_settled_window_when_the_run_is_long_enough():
    assert settled_window(_info(1100, last=1600)) == (1280, 1570)


def test_falls_back_when_the_default_config_is_too_short():
    # publisher at 90s, sim stops at 180s: the settled window would end before it starts.
    assert settled_window(_info(1090)) == (1000, 1180)


def test_falls_back_when_nothing_was_delivered():
    assert settled_window(_info(None)) == (1000, 1180)


def test_settled_window_uses_the_bridge_shifts():
    """The shifts are the bridge's, not a copy: a change there has to move Shadow too."""
    from datetime import timedelta

    from src.analysis.metrics.shadow_metrics import settled_window
    from src.deployments.libp2p.bridge import STABLE_END_SHIFT, STABLE_START_SHIFT

    first, last = 1_000, 10_000
    start, end = settled_window(
        {"first_delivery_epoch_s": first, "last_epoch_s": last, "start_epoch_s": 0}
    )
    assert start == first + STABLE_START_SHIFT.total_seconds()
    assert end == last + STABLE_END_SHIFT.total_seconds()
    # and those shifts are the ones the cluster's stable window actually uses
    from src.deployments.libp2p.bridge import Bridge

    stable = next(w for w in Bridge().event_windows() if w.key == "stable")
    assert stable.start.time_shift == STABLE_START_SHIFT == timedelta(minutes=3)
    assert stable.end.time_shift == STABLE_END_SHIFT == timedelta(seconds=-30)


def _snaps(totals):
    """One peer's snapshots, each carrying the received counter at that point."""
    return [f"{RECEIVED_METRIC} {t}" for t in totals]


def test_last_delivery_is_where_the_counter_stops_rising():
    """Publishing ends when the received counter goes flat; Shadow logs no event for it."""
    per_peer = [("pod-0", _snaps([0, 5, 9, 9, 9])), ("pod-1", _snaps([0, 4, 9, 9, 9]))]
    assert last_delivery_snapshot(per_peer) == 2


def test_last_delivery_is_none_when_nothing_was_ever_delivered():
    assert last_delivery_snapshot([("pod-0", _snaps([0, 0, 0]))]) is None


def test_last_delivery_ignores_a_peer_that_stops_early():
    """A peer with fewer snapshots must not end the window for everyone."""
    per_peer = [("pod-0", _snaps([0, 5])), ("pod-1", _snaps([0, 5, 8, 8]))]
    assert last_delivery_snapshot(per_peer) == 2


def test_window_ends_at_the_last_delivery_not_the_last_sample():
    """The gap between them is the idle tail that made quic report 27 connections."""
    info = {
        "first_delivery_epoch_s": 1_000,
        "last_delivery_epoch_s": 1_600,
        "last_epoch_s": 2_000,
        "start_epoch_s": 0,
    }
    start, end = settled_window(info)
    assert start == 1_000 + STABLE_START_SHIFT.total_seconds()
    assert end == 1_600 + STABLE_END_SHIFT.total_seconds()
    assert end < info["last_epoch_s"], "must not run past the traffic"


def test_window_falls_back_to_the_last_sample_when_the_end_is_unknown():
    """Older runs have no last_delivery_epoch_s recorded; keep working for them."""
    info = {"first_delivery_epoch_s": 1_000, "last_epoch_s": 2_000, "start_epoch_s": 0}
    _, end = settled_window(info)
    assert end == 2_000 + STABLE_END_SHIFT.total_seconds()
