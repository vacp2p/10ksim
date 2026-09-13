# Python Imports
from kubernetes.client import V1ResourceRequirements

# Project Imports
from src.deployments.core.builders import default_readiness_probe_health
from src.deployments.core.configs.container import ContainerConfig
from src.deployments.core.configs.pod import PodSpecConfig, PodTemplateSpecConfig
from src.deployments.core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig
from src.deployments.waku.builders.helpers import find_waku_container_config


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
    apply_stateful_set_spec_config(config.stateful_set_spec, namespace, overwrite=overwrite)


def create_resources() -> V1ResourceRequirements:
    return V1ResourceRequirements(
        requests={"memory": "64Mi", "cpu": "50m"}, limits={"memory": "768Mi", "cpu": "400m"}
    )


def create_args(cmd_type: int) -> dict:
    base = {
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
    if cmd_type == 1:
        return {
            **base,
            "--cluster-id": 2,
            "--shard": 0,
        }
    elif cmd_type == 2:
        return {
            **base,
            "--num-shards-in-network": 1,
            "--shard": 0,
        }

    raise ValueError(f"Invalid cmd_type: `{cmd_type}`")
