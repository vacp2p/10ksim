from kubernetes.client import (
    V1ResourceRequirements,
)

from builders.configs.command import (
    CommandConfig,
)
from builders.configs.container import (
    ContainerConfig,
)
from builders.configs.pod import (
    PodSpecConfig,
    PodTemplateSpecConfig,
)
from builders.configs.statefulset import (
    StatefulSetConfig,
    StatefulSetSpecConfig,
)
from builders.helpers import default_readiness_probe_health
from builders.waku.helpers import (
    WAKU_COMMAND_STR,
    find_waku_container_config,
)


class WakuBootstrapNode:
    @staticmethod
    def apply_command_config(config: CommandConfig):
        command = config.find_command(WAKU_COMMAND_STR)
        if command is None:
            raise ValueError(f"Waku command not found. CommandConfig: `{config}`")
        command.args.extend(
            [
                ("--relay", False),
                ("--rest", True),
                ("--rest-address", "0.0.0.0"),
                ("--max-connections", 1000),
                ("--discv5-discovery", True),
                ("--discv5-enr-auto-update", True),
                ("--log-level", "INFO"),
                ("--metrics-server", True),
                ("--metrics-server-address", "0.0.0.0"),
                ("--nat", "extip:$IP"),
                ("--cluster-id", 2),
            ]
        )

    @staticmethod
    def apply_container_config(config: ContainerConfig, *, overwrite: bool = False):
        config.with_readiness_probe(default_readiness_probe_health(), overwrite=overwrite)
        config.with_resources(WakuBootstrapNode.create_resources())

    @staticmethod
    def apply_pod_spec_config(config: PodSpecConfig):
        config.dns_config.searches.append(
            "zerotesting-bootstrap.zerotesting.svc.cluster.local",
        )
        container_config = find_waku_container_config(config)
        WakuBootstrapNode.apply_container_config(container_config)

    @staticmethod
    def apply_pod_template_spec_config(config: PodTemplateSpecConfig):
        config.with_app("zerotenkay-bootstrap")
        WakuBootstrapNode.apply_pod_spec_config(config.pod_spec_config)

    @staticmethod
    def apply_stateful_set_spec_config(config: StatefulSetSpecConfig, *, overwrite: bool = False):
        config.with_app("zerotenkay-bootstrap")
        config.with_service_name("zerotesting-bootstrap", overwrite=overwrite)
        WakuBootstrapNode.apply_pod_template_spec_config(config.pod_template_spec_config)

    @staticmethod
    def apply_stateful_set_config(config: StatefulSetConfig, *, overwrite: bool = False):
        config.name = "bootstrap"
        WakuBootstrapNode.apply_stateful_set_spec_config(
            config.stateful_set_spec, overwrite=overwrite
        )

    @staticmethod
    def create_resources() -> V1ResourceRequirements:
        return V1ResourceRequirements(
            requests={"memory": "64Mi", "cpu": "50m"}, limits={"memory": "768Mi", "cpu": "400m"}
        )

    @staticmethod
    def create_args() -> dict:
        return {
            "--cluster-id": 2,
            "--discv5-discovery": True,
            "--discv5-enr-auto-update": True,
            "--log-level": "INFO",
            "--max-connections": 1000,
            "--metrics-server-address": "0.0.0.0",
            "--metrics-server": True,
            "--nat": "extip:$IP",
            "--relay": False,
            "--rest-address": "0.0.0.0",
            "--rest": True,
        }
