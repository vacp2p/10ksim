from src.analysis.post_run.churn import churn_outages, churn_table, longest_run
from src.analysis.post_run.scenario_common import POD_COLUMN


def test_longest_run_picks_the_biggest_stretch():
    assert longest_run([False, True, False, True, True, True, False]) == (3, 5, 3)
    assert longest_run([True, True, False]) == (0, 1, 2)
    assert longest_run([False, False]) == (None, None, 0)
    assert longest_run([True]) == (0, 0, 1)


def test_churn_puts_every_miss_inside_one_contiguous_outage(deliveries, fanout):
    # pods 2 and 3 miss messages 2 and 3, then are back for message 4.
    df = deliveries(
        fanout(1, range(4), 0)
        + fanout(2, [0, 1], 30)
        + fanout(3, [0, 1], 50)
        + fanout(4, range(4), 90)
    )
    rows = dict((i, r) for i, _, r in churn_table(df, ["pod-2", "pod-3"], 4, 4))
    assert "12 of 16" in rows["delivery, whole run"]
    assert "4 to 4 of 4" in rows["delivery, nodes that stayed up"]
    assert "missed 2.0 of 4" in rows["delivery, churned nodes"]
    assert "2.0 in one stretch" in rows["delivery, churned nodes"]
    assert rows["clean recovery"].startswith("0 of 2 nodes keep dropping")
    # the outage spans the publish times of messages 2 and 3
    assert rows["observed outage per churned node"] == "20s median, 20s worst"


def test_churn_flags_a_node_that_keeps_dropping_after_its_outage(deliveries, fanout):
    """The real churn failure is a ragged recovery, not one clean gap."""
    # both share an outage over messages 2 and 3; pod-3 then drops 5 after returning for 4.
    df = deliveries(
        fanout(1, range(4), 0)
        + fanout(2, [0, 1], 30)
        + fanout(3, [0, 1], 50)
        + fanout(4, range(4), 90)
        + fanout(5, [0, 1, 2], 110)
    )
    rows = dict((i, r) for i, _, r in churn_table(df, ["pod-2", "pod-3"], 5, 4))
    assert (
        rows["clean recovery"]
        == "1 of 2 nodes keep dropping after their outage, worst 1 messages over 60s"
    )


def test_churn_flags_a_miss_on_either_side_of_the_outage(deliveries, fanout):
    """A miss before the outage counts too: the tail alone only looks to the right of it."""
    # pod-2 misses message 1, then 3 and 4; pod-3 misses 2 and 3, then 6.
    df = deliveries(
        fanout(1, [0, 1, 3], 0)
        + fanout(2, [0, 1, 2], 30)
        + fanout(3, [0, 1], 60)
        + fanout(4, [0, 1, 3], 90)
        + fanout(5, range(4), 120)
        + fanout(6, [0, 1, 2], 150)
    )
    rows = dict((i, r) for i, _, r in churn_table(df, ["pod-2", "pod-3"], 6, 4))

    assert "2 of 2 nodes missed anything outside it (worst 1)" in rows["delivery, churned nodes"]
    # only pod-3 trails after its outage, so the tail on its own misses pod-2 entirely
    assert rows["clean recovery"].startswith("1 of 2 nodes keep dropping")


def test_churn_reads_each_nodes_outage_off_its_own_miss_run(deliveries, fanout):
    """Pods come back staggered, so the outage cannot come from a shared window."""
    df = deliveries(
        fanout(1, range(4), 0)
        + fanout(2, [0, 1], 30)
        + fanout(3, [0, 1, 2], 60)
        + fanout(4, range(4), 90)
    )
    rows = dict((i, r) for i, _, r in churn_table(df, ["pod-2", "pod-3"], 4, 4))
    # pod-2 missed only message 2; pod-3 missed 2 and 3, spanning 30s
    assert rows["observed outage per churned node"] == "15s median, 30s worst"
    assert rows["clean recovery"].startswith("0 of 2 nodes keep dropping")


def test_churn_handles_a_node_that_never_comes_back(deliveries, fanout):
    df = deliveries(fanout(1, range(4), 0) + fanout(2, [0, 1], 30) + fanout(3, [0, 1], 60))
    rows = dict((i, r) for i, _, r in churn_table(df, ["pod-2", "pod-3"], 3, 4))
    assert "missed 2.0 of 3" in rows["delivery, churned nodes"]
    assert rows["clean recovery"].startswith("0 of 2 nodes keep dropping")


def test_a_churned_node_that_received_nothing_is_still_reported(deliveries, fanout):
    """The worst outcome must not vanish: absent from the pivot means absent from the table."""
    df = deliveries(fanout(1, [0, 1], 0) + fanout(2, [0, 1], 30))
    out = churn_outages(df, ["pod-2", "pod-3"])

    assert list(out[POD_COLUMN]) == ["pod-2", "pod-3"]
    assert list(out["missed"]) == [2, 2], "each missed every message"


def test_the_recovery_denominator_covers_every_churned_node(deliveries, fanout):
    """Dropping absent nodes shrank the denominator with the numerator, so a total
    failure read as a clean run."""
    df = deliveries(fanout(1, [0, 1, 2], 0) + fanout(2, [0, 1, 2], 30))
    rows = dict((i, r) for i, _, r in churn_table(df, ["pod-2", "pod-3", "pod-4"], 2, 5))

    assert rows["clean recovery"].startswith("0 of 3 nodes keep dropping")
