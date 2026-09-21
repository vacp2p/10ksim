from datetime import timedelta

from src.analysis.post_run.partition import partition_table
from src.analysis.post_run.tests.conftest import T0

HEAL = T0 + timedelta(seconds=100)


def test_partition_contained_then_reconverged(deliveries, fanout):
    # split messages reach only side a (0,1); after the heal message 3 reaches all four.
    df = deliveries(fanout(1, [0, 1], 10) + fanout(2, [0, 1], 20) + fanout(3, range(4), 130))
    rows = dict((item, result) for item, _, result in partition_table(df, HEAL, 2, 4, 3))
    assert "0 of 2 messages crossed" in rows["delivery under the split, far half"]
    assert "2 of 2 messages reached their whole half" in rows["delivery under the split, own half"]
    assert "0 reached only part of it" in rows["delivery under the split, own half"]
    assert rows["messages nobody received, whole run"].startswith("0 of 3 published")
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
    rows = dict((item, result) for item, _, result in partition_table(df, HEAL, 2, 4, 4))
    assert rows["time to reconverge after the heal"] == "10s"
    assert "2 of 3 messages reached all 4" in rows["delivery after reconvergence"]


def test_partition_reports_a_leak(deliveries, fanout):
    df = deliveries(fanout(1, range(4), 10) + fanout(2, [0, 1], 20))
    rows = dict((item, result) for item, _, result in partition_table(df, HEAL, 2, 4, 3))
    assert "1 of 2 messages crossed" in rows["delivery under the split, far half"]


def test_partition_says_so_when_it_never_reconverges(deliveries, fanout):
    df = deliveries(fanout(1, [0, 1], 10) + fanout(2, [0, 1], 130))
    rows = dict((item, result) for item, _, result in partition_table(df, HEAL, 2, 4, 3))
    assert rows["time to reconverge after the heal"].startswith("no message reached")


def test_partition_tells_partial_delivery_from_containment(deliveries, fanout):
    """Reaching one node of a two-node half is not the same as reaching the half."""
    df = deliveries(fanout(1, [0], 10) + fanout(2, [0, 1], 20) + fanout(3, range(4), 130))
    rows = dict((item, result) for item, _, result in partition_table(df, HEAL, 2, 4, 3))
    assert "1 of 2 messages reached their whole half" in rows["delivery under the split, own half"]
    assert "1 reached only part of it" in rows["delivery under the split, own half"]
    assert "0 of 2 messages crossed" in rows["delivery under the split, far half"]


def test_partition_counts_a_message_nobody_received(deliveries, fanout):
    """An undelivered message has no delivery row, so it used to be invisible, not contained."""
    df = deliveries(fanout(1, [0, 1], 10) + fanout(3, range(4), 130))
    rows = dict((item, result) for item, _, result in partition_table(df, HEAL, 2, 4, 3))
    assert rows["messages nobody received, whole run"].startswith("1 of 3 published")
    assert "1 of 1 messages reached their whole half" in rows["delivery under the split, own half"]


def test_partition_judges_each_half_by_its_own_size(deliveries, fanout):
    """Side b has two nodes here, so reaching both of them is full delivery for that half."""
    df = deliveries(fanout(1, [2, 3], 10) + fanout(2, [3], 20))
    rows = dict((item, result) for item, _, result in partition_table(df, HEAL, 2, 4, 2))
    assert "1 of 2 messages reached their whole half" in rows["delivery under the split, own half"]
    assert "1 reached only part of it" in rows["delivery under the split, own half"]
