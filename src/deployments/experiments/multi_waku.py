from typing import Any, Iterable, List, Optional

from pydantic import BaseModel

from src.deployments.core.configs.container import Image
from src.deployments.experiments.multi_experiment import Multiple
from src.deployments.experiments.waku import WakuExperiment
from src.deployments.registry import experiment


def shallow_merge(a: BaseModel, b: BaseModel):
    data = {**a.model_dump(), **b.model_dump()}
    return a.__class__.model_validate(data)


def get_num_messages(delay):
    """Returns the typical num_messages given a delay."""
    if delay == 10:
        return 60
    elif delay == 5:
        return 125
    elif delay == 1:
        return 600
    else:
        raise ValueError(f"delay: {delay}")


@experiment(name="multi-waku")
class MultiWaku(Multiple):
    """Run waku multiple times with different parameters."""

    def model_post_init(self, __context: Any) -> None:
        self.config.name = WakuExperiment.name
        super().model_post_init(__context)

    def get_params_paths(self) -> Optional[dict]:
        """Return dict mapping keys to values.yaml paths"""
        return None

    def exp_params(self) -> Iterable[dict]:
        version_list = [
            "soutullostatus/nwaku-jq-curl:v0.33.0-rc.3",
            "soutullostatus/nwaku-jq-curl:v0.34.0-rc1",
            "soutullostatus/nwaku-jq-curl:v0.35.1",
            "pearsonwhite/nwaku:v0.36.0-rc.0",
            "soutullostatus/nwaku-jq-curl:v0.37.0-rc.4",
            "pearsonwhite/nwaku:quic-b778d16",
            "pearsonwhite/nwaku:quic_b778d16_with_order_fix-amd",
        ]

        versions = {Image.from_str(item).tag: Image.from_str(item) for item in version_list}

        quic_supported = [
            "v0.37.0-rc.4",
            "quic-b778d16",
            "abort-fix",
            "c3090fb62febef41a4436eb328944a63486b8e30-linux-amd64",
            "quic_b778d16_with_order_fix-amd",
        ]
        format_changed = [
            "quic-b778d16",
            "abort-fix",
            "c3090fb62febef41a4436eb328944a63486b8e30-linux-amd64",
            "quic_b778d16_with_order_fix-amd",
        ]

        base = {
            "num_bootstrap_nodes": 3,
            "delay_cold_start": 180,
        }

        configs = []
        for num_relay_nodes in [1000]:
            for delay in [1, 5, 10]:
                num_messages = get_num_messages(delay)
                for size in [1, 50]:
                    for version, image in versions.items():
                        # Version dependent config params.
                        if version in quic_supported:
                            muxers = ["default", "quic"]
                            log_level = "DEBUG"
                            cmd_type = "2"
                        else:
                            muxers = ["default"]
                            log_level = "INFO"
                            cmd_type = "1"
                        if version in format_changed:
                            format_json = True
                        else:
                            format_json = False
                        for muxer in muxers:
                            config_params = {
                                **base,
                                "num_relay_nodes": num_relay_nodes,
                                "delay_after_publish": delay,
                                "num_messages": num_messages,
                                "format_json": format_json,
                                "log_level": log_level,
                                "cmd_type": cmd_type,
                                "image": image,
                                "muxer": muxer,
                                "msg_size_kbytes": size,
                            }
                            configs.append(config_params)

        return configs

    def get_params_list(self) -> List[dict]:
        return [item for item in self.exp_params()]

    def get_name_from_params(self, params: dict) -> str:
        version = params["image"].tag
        keys = ["num_nodes", "num_messages"]
        used_keys = filter(lambda item: item in keys, params.items())
        param_list = [f"{key}_{value}" for key, value in used_keys]
        param_list.append(f"version_{version}")
        return "__".join(param_list)
