import logging
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
    tracer = Nimlibp2pTracer().with_received_pattern_group(log_format="TEXT")
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
    tracer = Nimlibp2pTracer().with_received_pattern_group(log_format="TEXT")
    df = tracer._trace_received_in_logs(
        [("2759438560592407784", "1785892519584947712", "1785892519583493632", "-1")]
    )
    assert len(df) == 1
    assert df.iloc[0]["delayMs"] == "-1"


class TestNegativeDelayWarning:
    """Negative delays are kept, but they are not silent: the clocks were skewed."""

    def _rows(self, delays):
        return [
            [str(i), "1754000000000000000", "1754000000100000000", d] for i, d in enumerate(delays)
        ]

    def test_a_negative_delay_is_warned_about(self, caplog):
        tracer = Nimlibp2pTracer().with_extra_fields([])
        with caplog.at_level(logging.WARNING):
            tracer._trace_received_in_logs(self._rows(["10", "-3", "7", "-11"]))
        assert "2 of 4 deliveries (50.00%)" in caplog.text
        assert "-11ms" in caplog.text

    def test_clean_timing_does_not_warn(self, caplog):
        tracer = Nimlibp2pTracer().with_extra_fields([])
        with caplog.at_level(logging.WARNING):
            tracer._trace_received_in_logs(self._rows(["10", "7"]))
        assert not caplog.records

    def test_the_deliveries_are_still_kept(self):
        tracer = Nimlibp2pTracer().with_extra_fields([])
        df = tracer._trace_received_in_logs(self._rows(["10", "-3"]))
        assert len(df) == 2


def test_received_json():
    tracer = Nimlibp2pTracer().with_received_pattern_group(log_format="JSON")
    (group,) = tracer.patterns
    (pair,) = group.trace_pairs

    assert group.name == "received"
    assert group.fields == [
        "log.msgId",
        "log.sentAt",
        "log.timestamp",
        "log.delayMs",
    ]
    assert pair.regex is None

    parsed_logs = [
        [
            [
                [
                    "13647046878266911",
                    "1785892519584947712",
                    "1785892519585947712",
                    "1",
                ]
            ]
        ]
    ]

    dfs = tracer.trace(parsed_logs)
    received_df = dfs["received"][0]

    assert list(received_df.columns) == [
        "msgId",
        "sentAt",
        "timestamp",
        "delayMs",
    ]
    assert received_df.loc[0, "msgId"] == 13647046878266911
    assert received_df.loc[0, "sentAt"].value == 1785892519584947712
    assert received_df.loc[0, "timestamp"].value == 1785892519585947712
    assert received_df.loc[0, "delayMs"] == "1"
    assert str(received_df["sentAt"].dtype) == "datetime64[ns]"
    assert str(received_df["timestamp"].dtype) == "datetime64[ns]"


def test_sent_json():
    tracer = Nimlibp2pTracer().with_sent_pattern_group(log_format="JSON")
    (group,) = tracer.patterns
    (pair,) = group.trace_pairs

    assert group.name == "sent"
    assert group.fields == [
        "log.msgId",
        "log.timestamp",
    ]
    assert pair.regex is None

    parsed_logs = [
        [
            [
                [
                    "13647046878266911",
                    "1785892519584947712",
                ]
            ]
        ]
    ]

    dfs = tracer.trace(parsed_logs)
    sent_df = dfs["sent"][0]

    assert list(sent_df.columns) == [
        "msgId",
        "timestamp",
    ]
    assert sent_df.loc[0, "msgId"] == 13647046878266911
    assert sent_df.loc[0, "timestamp"].value == 1785892519584947712
    assert str(sent_df["timestamp"].dtype) == "datetime64[ns]"
