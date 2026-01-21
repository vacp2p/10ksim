from kubernetes.client import V1ResourceRequirements

from core.builders import default_readiness_probe_health
from core.configs.command import CommandConfig
from core.configs.container import ContainerConfig
from core.configs.pod import PodSpecConfig, PodTemplateSpecConfig
from core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig
from waku.builders.helpers import WAKU_COMMAND_STR, find_waku_container_config


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


def apply_container_config(config: ContainerConfig, *, overwrite: bool = False):
    config.with_readiness_probe(default_readiness_probe_health(), overwrite=overwrite)
    config.with_resources(create_resources())


def apply_pod_spec_config(config: PodSpecConfig, namespace: str, *, overwrite: bool = False):
    config.dns_config.searches.append(
        f"zerotesting-bootstrap.{namespace}.svc.cluster.local",
    )
    container_config = find_waku_container_config(config)
    apply_container_config(container_config, overwrite=overwrite)


def apply_pod_template_spec_config(
    config: PodTemplateSpecConfig, namespace: str, *, overwrite: bool = False
):
    config.with_app("zerotenkay-bootstrap")
    apply_pod_spec_config(config.pod_spec_config, namespace, overwrite=overwrite)


def apply_stateful_set_spec_config(
    config: StatefulSetSpecConfig, namespace: str, *, overwrite: bool = False
):
    config.with_app("zerotenkay-bootstrap")
    config.with_service_name("zerotesting-bootstrap", overwrite=overwrite)
    apply_pod_template_spec_config(config.pod_template_spec_config, namespace, overwrite=overwrite)


def apply_stateful_set_config(
    config: StatefulSetConfig, namespace: str, *, overwrite: bool = False
):
    config.name = "bootstrap"
    apply_stateful_set_spec_config(config.stateful_set_spec, namespace, overwrite=overwrite)


def create_resources() -> V1ResourceRequirements:
    return V1ResourceRequirements(
        requests={"memory": "64Mi", "cpu": "50m"}, limits={"memory": "768Mi", "cpu": "400m"}
    )


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
