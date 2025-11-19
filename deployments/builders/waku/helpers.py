from builders.configs.command import (
    Command,
    CommandConfig,
)
from builders.configs.container import (
    ContainerConfig,
)
from builders.configs.pod import (
    PodSpecConfig,
)
from builders.helpers import HigherConfigTypes, find_container_config, get_config

WAKU_COMMAND_STR = "/usr/bin/wakunode"
WAKU_CONTAINER_NAME = "waku"


def find_waku_command(config: CommandConfig) -> Command | None:
    return config.find_command(WAKU_COMMAND_STR)


def find_waku_container_config(config: HigherConfigTypes) -> ContainerConfig | None:
    """Finds the ContainerConfig for Waku from a PodSpecConfig"""
    pod_spec_config = get_config(config, PodSpecConfig)
    return find_container_config(pod_spec_config, "waku")
