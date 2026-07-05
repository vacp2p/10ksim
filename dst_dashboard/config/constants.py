import os
from enum import StrEnum
from pathlib import Path



DEFAULT_CONFIG_PATH = Path.home() / ".cache" / "dst_dashboard" / "config.yaml"
DEFAULT_DB_PATH = Path.home() / ".cache" / "dst_dashboard"
DEFAULT_DATA_PATH = Path.home() / ".cache" / "dst_dashboard" / "data"

class Constants(StrEnum):
    """Constants used in DST dashboard application."""

    DST_CONFIG_PATH = os.environ.get(
        "DST_CONFIG_PATH",
        str(DEFAULT_CONFIG_PATH),
    )
    DST_DB_PATH = os.environ.get(
        "DST_DB_PATH",
        str(DEFAULT_DB_PATH),
    )
    DST_DATA_PATH = os.environ.get(
        "DST_DATA_PATH",
        str(DEFAULT_DATA_PATH),
    )
