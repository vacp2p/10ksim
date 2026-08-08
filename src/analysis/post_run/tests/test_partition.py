from datetime import timedelta

from src.analysis.post_run.partition import partition_table
from src.analysis.post_run.tests.conftest import T0

HEAL = T0 + timedelta(seconds=100)


def test_partition_contained_then_reconverged(deliveries, fanout):
    # split messages reach only side a (0,1); after the heal message 3 reaches all four.
    df = deliveries(fanout(1, [0, 1], 10) + fanout(2, [0, 1], 20) + fanout(3, range(4), 130))
    rows = dict((item, result) for item, _, result in partition_table(df, HEAL, 2, 4))
    assert "0 of 2 messages crossed" in rows["delivery under the split, far half"]
    assert "mean reach 2.0 over 2 messages" in rows["delivery under the split, own half"]
    assert "2 contained to one side" in rows["delivery under the split, own half"]
    assert rows["time to reconverge after the heal"] == "30s"
    assert "1 of 1 messages reached all 4" in rows["delivery after reconvergence"]


def test_partition_reconvergence_uses_the_earliest_full_message(deliveries, fanout):
    """A groupby orders by msgId, so the row must be picked by publish time, not by id."""
    # the earliest full-reach message has the largest msgId, and one message still lags.
    df = deliveries(
        fanout(1, [0, 1], 10)
        + fanout(900, range(4), 110)
        + fanout(5, [0, 1], 105)
        + fanout(7, range(4), 200)
    )
    rows = dict((item, result) for item, _, result in partition_table(df, HEAL, 2, 4))
    assert rows["time to reconverge after the heal"] == "10s"
    assert "2 of 3 messages reached all 4" in rows["delivery after reconvergence"]


def test_partition_reports_a_leak(deliveries, fanout):
    df = deliveries(fanout(1, range(4), 10) + fanout(2, [0, 1], 20))
    rows = dict((item, result) for item, _, result in partition_table(df, HEAL, 2, 4))
    assert "1 of 2 messages crossed" in rows["delivery under the split, far half"]


def test_partition_says_so_when_it_never_reconverges(deliveries, fanout):
    df = deliveries(fanout(1, [0, 1], 10) + fanout(2, [0, 1], 130))
    rows = dict((item, result) for item, _, result in partition_table(df, HEAL, 2, 4))
    assert rows["time to reconverge after the heal"].startswith("no message reached")
