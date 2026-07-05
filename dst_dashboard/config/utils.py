import yaml
from dst_dashboard.config.constants import Constants
from dst_dashboard.config.data_structures import DashboardFullConfig


def LoadConfig(config_path: str = Constants.DST_CONFIG_PATH) -> DashboardFullConfig:
    with open(config_path, "r", encoding="utf-8") as file:
        config_yaml = yaml.safe_load(file)
    if config_yaml is None:
        raise ValueError(f"Config file '{config_path}' is empty")
    config = DashboardFullConfig.model_validate(config_yaml)
    return config
