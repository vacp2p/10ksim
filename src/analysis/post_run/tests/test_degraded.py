from src.analysis.post_run.degraded import degraded_table


def test_degraded_reports_full_delivery(deliveries, fanout):
    df = deliveries(fanout(1, range(4), 0) + fanout(2, range(4), 1))
    rows = dict((item, result) for item, _, result in degraded_table(df, 2, 4))
    assert "8 of 8 (100.0%)" in rows["delivery"]


def test_degraded_flags_a_shortfall(deliveries, fanout):
    df = deliveries(fanout(1, range(4), 0) + fanout(2, range(3), 1))
    rows = dict((item, result) for item, _, result in degraded_table(df, 2, 4))
    assert "7 of 8 (87.5%)" in rows["delivery"]


def test_degraded_reports_latency_percentiles(deliveries):
    df = deliveries([(1, o, 0, o * 100) for o in range(1, 5)])
    rows = dict((item, result) for item, _, result in degraded_table(df, 1, 4))
    assert rows["median latency"] == "p50 250 / p99 397 / max 400 ms"
    assert rows["latency tail"] == "max 400 ms"
