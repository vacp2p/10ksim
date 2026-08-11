import logging
from datetime import datetime, timezone

from result import Err, Ok

from src.analysis.post_run import delivery_cross_check as dcc
from src.analysis.post_run.delivery_cross_check import counter_deliveries, cross_check, report
from src.analysis.post_run.nimlibp2p import _log_derived_deliveries


def test_agreement_confirms_the_log_number():
    assert cross_check(600_000, 600_000).verdict == "confirmed"


def test_rounding_sized_gaps_are_not_reported_as_loss():
    assert cross_check(599_950, 600_000).verdict == "confirmed"


def test_a_real_shortfall_is_named_as_collection_loss():
    """The nodes counted receives the logs never showed, so the logs are the floor."""
    result = cross_check(548_000, 600_000)
    assert result.verdict == "collection_loss"
    assert "52000 more receives" in result.detail


def test_more_in_the_logs_than_the_counters_is_not_loss():
    """Counters freeze at teardown, so the logs legitimately run ahead."""
    assert cross_check(600_000, 599_000).verdict == "confirmed"


def test_a_missing_counter_leaves_the_number_unverified_rather_than_confirmed():
    result = cross_check(548_000, None)
    assert result.verdict == "unverified"
    assert result.from_counters is None


def test_collection_loss_is_warned_about_not_just_logged(caplog):
    with caplog.at_level(logging.WARNING):
        report(cross_check(548_000, 600_000))
    assert "Delivery cross-check" in caplog.text
    assert caplog.records[0].levelno == logging.WARNING


def test_agreement_does_not_warn(caplog):
    with caplog.at_level(logging.WARNING):
        report(cross_check(600_000, 600_000))
    assert not caplog.records


class TestCounterQuery:
    def _window(self):
        return datetime(2026, 8, 10, tzinfo=timezone.utc), datetime(
            2026, 8, 10, 1, tzinfo=timezone.utc
        )

    def test_takes_the_peak_of_the_summed_counter(self, mocker):
        mocker.patch.object(
            dcc.scrape_utils,
            "get_query_data",
            return_value=Ok({"data": {"result": [{"values": [[1, "10"], [2, "600000"]]}]}}),
        )
        assert counter_deliveries("http://vm/", "ns", *self._window()) == 600_000

    def test_an_unavailable_metric_is_none_not_zero(self, mocker, caplog):
        """Zero would read as total collection loss and flag every run."""
        mocker.patch.object(
            dcc.scrape_utils, "get_query_data", return_value=Err("Returned data is empty.")
        )
        with caplog.at_level(logging.WARNING):
            assert counter_deliveries("http://vm/", "ns", *self._window()) is None
        assert "Could not read" in caplog.text


class TestLogDerivedCount:
    def test_a_clean_run_counts_every_expected_delivery(self):
        reliability = {
            "expected_num_peers": 1000,
            "expected_num_messages": 600,
            "missing_messages": [],
        }
        assert _log_derived_deliveries(reliability) == 600_000

    def test_what_each_node_missed_is_subtracted(self):
        reliability = {
            "expected_num_peers": 1000,
            "expected_num_messages": 600,
            "missing_messages": [
                {
                    "messages": ["m1", "m2"],
                    "nodes": [{"name": "pod-0", "missing": 2}, {"name": "pod-1", "missing": 1}],
                }
            ],
        }
        assert _log_derived_deliveries(reliability) == 600_000 - 3

    def test_the_two_marginals_are_not_multiplied(self):
        """43 nodes each missing a different message is 43 lost deliveries, not 43x43."""
        reliability = {
            "expected_num_peers": 1000,
            "expected_num_messages": 600,
            "missing_messages": [
                {
                    "messages": [f"m{i}" for i in range(43)],
                    "nodes": [{"name": f"pod-{i}", "missing": 1} for i in range(43)],
                }
            ],
        }
        assert _log_derived_deliveries(reliability) == 600_000 - 43

    def test_a_node_without_a_count_does_not_break_the_sum(self):
        reliability = {
            "expected_num_peers": 10,
            "expected_num_messages": 10,
            "missing_messages": [{"messages": ["m1"], "nodes": [{"name": "pod-0"}]}],
        }
        assert _log_derived_deliveries(reliability) == 100


class TestWindowTypes:
    """The metadata stack carries the window as ISO strings, not datetimes. Passing those
    straight to the query builder raised `'str' object has no attribute 'tzinfo'` on the
    first real run, because the tests until now only fed it datetimes."""

    def _ok(self, mocker):
        mocker.patch.object(
            dcc.scrape_utils,
            "get_query_data",
            return_value=Ok({"data": {"result": [{"values": [[1, "600000"]]}]}}),
        )

    def test_accepts_the_iso_strings_the_metadata_actually_holds(self, mocker):
        self._ok(mocker)
        assert (
            counter_deliveries("http://vm/", "ns", "2026-08-11T15:52:06", "2026-08-11T16:26:10")
            == 600_000
        )

    def test_still_accepts_datetimes(self, mocker):
        self._ok(mocker)
        assert (
            counter_deliveries(
                "http://vm/",
                "ns",
                datetime(2026, 8, 11, 15, 52, 6, tzinfo=timezone.utc),
                datetime(2026, 8, 11, 16, 26, 10, tzinfo=timezone.utc),
            )
            == 600_000
        )
