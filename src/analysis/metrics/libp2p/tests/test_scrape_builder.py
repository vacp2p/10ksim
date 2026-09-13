import logging

import pytest

from src.analysis.metrics.libp2p.scrape import Nimlibp2pScrapeBuilder


def _exp(*, stable: dict, complete: dict) -> dict:
    return {
        "params": {"muxer": "quic"},
        "stack": {"namespace": "zerotesting"},
        "results": {
            "stable": stable,
            "complete": complete,
        },
    }


def test_with_exp_uses_stable_interval_when_it_is_valid():
    exp = _exp(
        stable={
            "start": "2026-08-24T23:59:35",
            "end": "2026-08-25T00:01:55",
        },
        complete={
            "start": "2026-08-24T23:55:48",
            "end": "2026-08-25T00:02:25",
        },
    )

    builder = Nimlibp2pScrapeBuilder().with_exp(exp)

    assert builder.interval.start.isoformat() == "2026-08-24T23:59:35+00:00"
    assert builder.interval.end.isoformat() == "2026-08-25T00:01:55+00:00"
    assert builder.build().exp == exp


def test_with_exp_falls_back_to_complete_when_stable_interval_is_invalid(caplog):
    exp = _exp(
        stable={
            "start": "2026-08-24T23:59:35",
            "end": "2026-08-24T23:56:26",
        },
        complete={
            "start": "2026-08-24T23:55:48",
            "end": "2026-08-25T00:02:25",
        },
    )

    with caplog.at_level(logging.WARNING):
        builder = Nimlibp2pScrapeBuilder().with_exp(exp)

    assert builder.interval.start.isoformat() == "2026-08-24T23:55:48+00:00"
    assert builder.interval.end.isoformat() == "2026-08-25T00:02:25+00:00"
    assert "Ignoring invalid stable interval" in caplog.text


def test_with_exp_raises_when_no_valid_interval_exists():
    exp = _exp(
        stable={
            "start": "2026-08-24T23:59:35",
            "end": "2026-08-24T23:56:26",
        },
        complete={
            "start": "2026-08-24T23:55:48",
            "end": "2026-08-24T23:52:25",
        },
    )

    with pytest.raises(ValueError, match="valid stable or complete interval"):
        Nimlibp2pScrapeBuilder().with_exp(exp)
