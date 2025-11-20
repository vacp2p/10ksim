from kubernetes.client import (
    V1ContainerPort,
    V1EnvVar,
    V1EnvVarSource,
    V1ObjectFieldSelector,
    V1PodDNSConfig,
    V1ResourceRequirements,
)

from builders.configs.command import (
    Command,
    CommandConfig,
)
from builders.configs.container import (
    ContainerConfig,
    Image,
)
from builders.configs.pod import (
    PodSpecConfig,
    PodTemplateSpecConfig,
)
from builders.configs.statefulset import (
    StatefulSetConfig,
    StatefulSetSpecConfig,
)
from builders.helpers import get_container_command
from builders.libp2p.helpers import readiness_probe_metrics
from builders.waku.helpers import WAKU_COMMAND_STR, WAKU_CONTAINER_NAME


class Nodes:
    @staticmethod
    def create_command() -> Command:
        return Command(command=WAKU_COMMAND_STR, multiline=True)

    def apply_nice_command(
        config: StatefulSetSpecConfig | StatefulSetConfig | PodTemplateSpecConfig | PodSpecConfig,
        increment: int,
    ):
        command = get_container_command(config, WAKU_CONTAINER_NAME, WAKU_COMMAND_STR)
        command.with_pre_command(f"nice -n {increment}")

    @staticmethod
    def create_command_config() -> CommandConfig:
        return CommandConfig(commands=[Nodes.create_command()])

    @staticmethod
    def create_container_config() -> ContainerConfig:
        config = ContainerConfig(
            name="waku",
            image=Image(repo="soutullostatus/nwaku-jq-curl", tag="v0.34.0-rc1"),
            image_pull_policy="IfNotPresent",
        )
        config.ports = [
            V1ContainerPort(8645),
            V1ContainerPort(8008),
        ]
        config.with_env_var(
            V1EnvVar(
                name="IP",
                value_from=V1EnvVarSource(
                    field_ref=V1ObjectFieldSelector(field_path="status.podIP")
                ),
            )
        )
        config.with_readiness_probe(readiness_probe_metrics())
        config.command_config = Nodes.create_command_config()
        return config

    @staticmethod
    def create_pod_spec_config() -> PodSpecConfig:
        return PodSpecConfig(
            container_configs=[Nodes.create_container_config()],
            dns_config=V1PodDNSConfig(
                searches=["zerotesting-service.zerotesting.svc.cluster.local"]
            ),
        )

    @staticmethod
    def create_resources() -> V1ResourceRequirements:
        return V1ResourceRequirements(
            requests={
                "memory": "64Mi",
                "cpu": "150m",
            },
            limits={
                "memory": "600Mi",
                "cpu": "400m",
            },
        )

    @staticmethod
    def create_pod_template_spec_config() -> PodTemplateSpecConfig:
        config = PodTemplateSpecConfig(pod_spec_config=Nodes.create_pod_spec_config())
        config.with_app("zerotenkay")
        return config

    @staticmethod
    def create_stateful_set_spec_config() -> StatefulSetSpecConfig:
        config = StatefulSetSpecConfig(
            replicas=0,
            service_name="zerotesting-service",
            pod_template_spec_config=Nodes.create_pod_template_spec_config(),
        )
        config.with_app("zerotenkay")
        return config

    @staticmethod
    def create_statefulset_config() -> StatefulSetConfig:
        return StatefulSetConfig(
            name="nodes",
            namespace="zerotesting",
            apiVersion="apps/v1",
            kind="StatefulSet",
            pod_management_policy="Parallel",
            stateful_set_spec=Nodes.create_stateful_set_spec_config(),
        )
