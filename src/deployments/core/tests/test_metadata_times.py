from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from src.deployments.core.metadata_times import (
    add_links,
    format_metadata_timestamps,
    format_timestamp_url,
    format_timestamp_vquery,
    get_valid_shifted_times,
    grafana_link,
    victorialogs_link,
)
from src.utils.dict_utils import KeepNode


def test_format_timestamp_vquery_formats_datetime_for_victoria_queries():
    assert format_timestamp_vquery(datetime(2026, 1, 1, 12, 0, 0)) == "2026-01-01T12:00:00"


def test_format_timestamp_vquery_ignores_non_datetime_values():
    with pytest.raises(KeepNode):
        format_timestamp_vquery("not-a-date")
    with pytest.raises(KeepNode):
        format_timestamp_vquery(None)


def test_format_timestamp_url_formats_datetime_for_urls():
    assert format_timestamp_url(datetime(2026, 1, 1, 12, 0, 0)) == "2026-01-01T12:00:00.000Z"


def test_format_metadata_timestamps_formats_nested_datetime_values():
    metadata = {"stable": {"start": datetime(2026, 1, 1, 12, 0, 0)}}

    assert format_metadata_timestamps(metadata, "vquery") == {
        "stable": {"start": "2026-01-01T12:00:00"}
    }

    assert format_metadata_timestamps(metadata, "url") == {
        "stable": {"start": "2026-01-01T12:00:00.000Z"}
    }


def test_format_metadata_timestamps_rejects_unknown_format():
    with pytest.raises(ValueError, match="Unknown format option"):
        format_metadata_timestamps({}, "unknown")


def test_get_valid_shifted_times_applies_offsets_and_filters_invalid_ranges():
    metadata = {
        "stable": {"start": datetime(2026, 1, 1, 12, 0, 0), "end": datetime(2026, 1, 1, 12, 5, 0)},
        "invalid": {
            "start": datetime(2026, 1, 1, 12, 5, 0),
            "end": datetime(2026, 1, 1, 12, 0, 0),
        },
    }

    shifted = get_valid_shifted_times(
        {
            "stable.start": timedelta(minutes=1),
            "stable.end": timedelta(minutes=-1),
            "invalid.start": timedelta(minutes=0),
            "invalid.end": timedelta(minutes=0),
        },
        metadata,
    )

    assert shifted == {
        "stable": {"start": datetime(2026, 1, 1, 12, 1, 0), "end": datetime(2026, 1, 1, 12, 4, 0)}
    }


def test_get_valid_shifted_times_does_not_mutate_input_metadata():
    metadata = {"stable": {"start": datetime(2026, 1, 1, 12, 0, 0)}}

    get_valid_shifted_times({"stable.start": timedelta(minutes=1)}, metadata)

    assert metadata == {"stable": {"start": datetime(2026, 1, 1, 12, 0, 0)}}


def test_add_links_formats_known_intervals_in_place():
    metadata = {"stable": {"start": "1000", "end": "2000"}, "other": {}}

    add_links(metadata, {"grafana": "https://example.test?from={start}&to={end}"})

    assert metadata["stable"]["grafana"] == "https://example.test?from=1000&to=2000"
    assert metadata["other"] == {}


def test_grafana_link_encodes_from_and_to_from_datetime():
    start = datetime(2026, 1, 1, 12, 0, 0)
    end = datetime(2026, 1, 1, 12, 5, 0)

    url = grafana_link(start, end, namespace="ns")
    params = parse_qs(urlparse(url).query)

    assert params["from"] == [start.isoformat()]
    assert params["to"] == [end.isoformat()]
    assert params["var-namespace"] == ["ns"]


def test_victorialogs_link_encodes_range_and_namespace():
    start = datetime(2026, 1, 1, 12, 0, 0)
    end = datetime(2026, 1, 1, 12, 20, 30)

    url = victorialogs_link(start, end, namespace="ns")

    assert url.startswith("https://vlselect.lab.vac.dev/select/vmui/#/?")
    assert "g0.range_input=20m30s" in url
    assert "kubernetes.pod_namespace%3Ans" in url
