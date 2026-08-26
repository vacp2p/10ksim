import re
from typing import Optional

from src.analysis.data.data_file_handler import DataPath
from src.analysis.metrics.config import ScrapeConfig
from src.analysis.plotting.config import DataGroup


class Nimlibp2pScrapePlotData:
    """Convert Nimlibp2p scrape configs into generic plotting groups."""

    @staticmethod
    def version_and_muxer(scrape_config: ScrapeConfig) -> tuple[Optional[str], str]:
        params = scrape_config.exp.get("params", {}) if scrape_config.exp else {}
        muxer = params.get("muxer") or scrape_config.name
        version = params.get("version")
        if not version:
            image = str(params.get("image", ""))
            match = re.search(r"v?(\d+\.\d+\.\d+)", image)
            version = match.group(1) if match else None

        return version, muxer

    @classmethod
    def scrape_display_name(cls, scrape_config: ScrapeConfig) -> str:
        version, muxer = cls.version_and_muxer(scrape_config)
        return f"{version}/{muxer}" if version else scrape_config.name

    @classmethod
    def single_group(
        cls, scrape_configs: list[ScrapeConfig] | ScrapeConfig, *, name: str = "scrapes"
    ) -> DataGroup:
        if isinstance(scrape_configs, ScrapeConfig):
            scrape_configs = [scrape_configs]

        data_paths = [
            DataPath(
                name=cls.scrape_display_name(scrape_config),
                path=scrape_config.dump_location,
                file_name=scrape_config.name,
            )
            for scrape_config in scrape_configs
        ]
        return DataGroup(name=name, data_paths=data_paths)

    @classmethod
    def groups_by_version(cls, scrape_configs: list[ScrapeConfig] | ScrapeConfig) -> list[DataGroup]:
        if isinstance(scrape_configs, ScrapeConfig):
            scrape_configs = [scrape_configs]

        groups: dict[str, list[DataPath]] = {}
        for scrape_config in scrape_configs:
            version, muxer = cls.version_and_muxer(scrape_config)
            group_name = version or scrape_config.name
            groups.setdefault(group_name, []).append(
                DataPath(
                    name=muxer,
                    path=scrape_config.dump_location,
                    file_name=scrape_config.name,
                )
            )

        return [
            DataGroup(name=group_name, data_paths=data_paths)
            for group_name, data_paths in groups.items()
        ]
