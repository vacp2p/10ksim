import re

from src.analysis.mesh_analysis.readers.tracers.nimlibp2p_tracer import Nimlibp2pTracer

POSITIVE = (
    "INF 2026-08-05 01:15:19.582+00:00 Received message   tid=1 "
    "msgId=13647046878266911 sentAt=1785892519584947712 current=1785892519585947712 delayMs=1"
)
NEGATIVE = (
    "INF 2026-08-05 01:15:19.582+00:00 Received message   tid=1 "
    "msgId=2759438560592407784 sentAt=1785892519584947712 current=1785892519583493632 delayMs=-1"
)


def _received_regex():
    tracer = Nimlibp2pTracer().with_received_pattern_group()
    (group,) = [p for p in tracer.patterns if p.name == "received"]
    (pair,) = group.trace_pairs
    return re.compile(pair.regex)


def test_received_line_is_parsed():
    m = _received_regex().search(POSITIVE)
    assert m.groups() == ("13647046878266911", "1785892519584947712", "1785892519585947712", "1")


def test_negative_delay_is_parsed():
    """A sender clock ahead of the receiver's yields delayMs=-N; dropping those under-reports
    delivery, and it lands on whichever hosts are skewed."""
    m = _received_regex().search(NEGATIVE)
    assert m is not None, "negative delayMs must still match, or the delivery is lost"
    assert m.group(1) == "2759438560592407784"
    assert m.group(4) == "-1"


def test_negative_delay_survives_conversion():
    tracer = Nimlibp2pTracer().with_received_pattern_group()
    df = tracer._trace_received_in_logs(
        [("2759438560592407784", "1785892519584947712", "1785892519583493632", "-1")]
    )
    assert len(df) == 1
    assert df.iloc[0]["delayMs"] == "-1"
