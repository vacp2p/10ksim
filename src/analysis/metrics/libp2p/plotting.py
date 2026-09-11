import re
from typing import Optional

from src.analysis.data.data_file_handler import DataPath
from src.analysis.metrics.config import ScrapeConfig
from src.analysis.plotting.config import DataGroup


class Nimlibp2pScrapePlotData:
    """Convert Nimlibp2p scrape configs into generic plotting groups."""

    @staticmethod
    def _image_tag(image: object) -> Optional[str]:
        if not image:
            return None

        if isinstance(image, dict):
            tag = image.get("tag")
            if tag:
                return str(tag).strip()

        tag = getattr(image, "tag", None)
        if tag:
            return str(tag).strip()

        image_str = str(image).strip()
        if not image_str:
            return None

        match = re.search(r"tag=['\"]([^'\"]+)['\"]", image_str)
        if match:
            return match.group(1).strip()

        image_name = image_str.rsplit("/", 1)[-1]
        if ":" in image_name:
            return image_name.rsplit(":", 1)[-1].strip()

        return image_str

    @staticmethod
    def _version_from_tag(tag: Optional[str]) -> Optional[str]:
        if not tag:
            return None

        match = re.search(r"v?(\d+\.\d+\.\d+)", tag)
        return match.group(1) if match else None

    @classmethod
    def version_and_muxer(cls, scrape_config: ScrapeConfig) -> tuple[Optional[str], str]:
        params = scrape_config.exp.get("params", {}) if scrape_config.exp else {}
        muxer = params.get("muxer") or scrape_config.name
        version = params.get("version")
        if not version:
            version = cls._version_from_tag(cls._image_tag(params.get("image")))

        return str(version) if version else None, str(muxer)

    @classmethod
    def build_label_and_muxer(cls, scrape_config: ScrapeConfig) -> tuple[Optional[str], str]:
        params = scrape_config.exp.get("params", {}) if scrape_config.exp else {}
        version, muxer = cls.version_and_muxer(scrape_config)
        build_label = version or cls._image_tag(params.get("image"))

        return build_label, muxer

    @classmethod
    def scrape_display_name(cls, scrape_config: ScrapeConfig) -> str:
        build_label, muxer = cls.build_label_and_muxer(scrape_config)
        return f"{build_label}/{muxer}" if build_label else scrape_config.name

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
    def groups_by_version(
        cls, scrape_configs: list[ScrapeConfig] | ScrapeConfig
    ) -> list[DataGroup]:
        if isinstance(scrape_configs, ScrapeConfig):
            scrape_configs = [scrape_configs]

        groups: dict[str, list[DataPath]] = {}
        for scrape_config in scrape_configs:
            group_name, muxer = cls.build_label_and_muxer(scrape_config)
            groups.setdefault(group_name or scrape_config.name, []).append(
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
