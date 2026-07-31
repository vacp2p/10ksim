from src.analysis.metrics.shadow_metrics import RECEIVED_METRIC, first_delivery_snapshot


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
