from pathlib import Path

from src.analysis.metrics.config import ScrapeConfig
from src.analysis.metrics.libp2p.plotting import Nimlibp2pScrapePlotData
from src.analysis.metrics.libp2p.scrape import Nimlibp2pScrapeBuilder
from src.analysis.utils.time_utils import TimeRange


def _exp(version: str, muxer: str) -> dict:
    return {
        "params": {
            "muxer": muxer,
            "image": f"soutullostatus/dst-test-node:v{version}-15af9c59",
        },
        "results": {
            "stable": {
                "start": "2026-08-24T23:55:48",
                "end": "2026-08-25T00:02:25",
            }
        },
        "stack": {"namespace": "ns"},
    }


def _scrape(name: str, dump_location: Path, *, exp: dict | None = None) -> ScrapeConfig:
    interval = TimeRange()
    interval.start = "2026-08-24T23:55:48"
    interval.end = "2026-08-25T00:02:25"
    return ScrapeConfig(name=name, dump_location=dump_location, interval=interval, exp=exp)


def test_single_group_uses_version_and_muxer_as_display_name(tmp_path):
    group = Nimlibp2pScrapePlotData.single_group(
        [
            _scrape(
                "mplex",
                tmp_path / "asd_run_0",
                exp={
                    "params": {
                        "muxer": "mplex",
                        "image": "soutullostatus/dst-test-node:v2.3.0-15af9c59",
                    }
                },
            ),
            _scrape(
                "mplex",
                tmp_path / "asd_run_1",
                exp={
                    "params": {
                        "muxer": "mplex",
                        "image": "radiken/dst-test-node-regression:v2.2.0-pingall3",
                    }
                },
            ),
        ]
    )

    assert group.name == "scrapes"
    assert [(path.name, path.path, path.file_name) for path in group.data_paths] == [
        ("2.3.0/mplex", tmp_path / "asd_run_0", "mplex"),
        ("2.2.0/mplex", tmp_path / "asd_run_1", "mplex"),
    ]


def test_groups_by_version_uses_version_as_group_and_muxer_as_display_name(tmp_path):
    groups = Nimlibp2pScrapePlotData.groups_by_version(
        [
            _scrape(
                "mplex",
                tmp_path / "asd_run_0",
                exp={
                    "params": {
                        "muxer": "mplex",
                        "image": "soutullostatus/dst-test-node:v2.3.0-15af9c59",
                    }
                },
            ),
            _scrape(
                "yamux",
                tmp_path / "asd_run_1",
                exp={
                    "params": {
                        "muxer": "yamux",
                        "image": "soutullostatus/dst-test-node:v2.3.0-15af9c59",
                    }
                },
            ),
            _scrape(
                "mplex",
                tmp_path / "asd_run_2",
                exp={
                    "params": {
                        "muxer": "mplex",
                        "image": "radiken/dst-test-node-regression:v2.2.0-pingall3",
                    }
                },
            ),
        ]
    )

    assert [group.name for group in groups] == ["2.3.0", "2.2.0"]
    assert [(path.name, path.path, path.file_name) for path in groups[0].data_paths] == [
        ("mplex", tmp_path / "asd_run_0", "mplex"),
        ("yamux", tmp_path / "asd_run_1", "yamux"),
    ]
    assert [(path.name, path.path, path.file_name) for path in groups[1].data_paths] == [
        ("mplex", tmp_path / "asd_run_2", "mplex"),
    ]


def test_groups_by_version_uses_metadata_from_built_scrape_configs(tmp_path):
    scrapes = [
        (
            Nimlibp2pScrapeBuilder()
            .with_exp(_exp("2.3.0", "mplex"), extract_name=True)
            .with_dump_location(tmp_path / "asd_run_0")
            .build()
        ),
        (
            Nimlibp2pScrapeBuilder()
            .with_exp(_exp("2.3.0", "yamux"), extract_name=True)
            .with_dump_location(tmp_path / "asd_run_1")
            .build()
        ),
        (
            Nimlibp2pScrapeBuilder()
            .with_exp(_exp("2.2.0", "mplex"), extract_name=True)
            .with_dump_location(tmp_path / "asd_run_2")
            .build()
        ),
    ]

    groups = Nimlibp2pScrapePlotData.groups_by_version(scrapes)

    assert [group.name for group in groups] == ["2.3.0", "2.2.0"]
    assert [(path.name, path.path, path.file_name) for path in groups[0].data_paths] == [
        ("mplex", tmp_path / "asd_run_0", "mplex"),
        ("yamux", tmp_path / "asd_run_1", "yamux"),
    ]
    assert [(path.name, path.path, path.file_name) for path in groups[1].data_paths] == [
        ("mplex", tmp_path / "asd_run_2", "mplex"),
    ]
