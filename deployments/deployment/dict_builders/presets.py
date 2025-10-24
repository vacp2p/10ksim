from typing import List, Literal, Optional

from kubernetes.client import (
    V1ContainerPort,
    V1EnvVar,
    V1EnvVarSource,
    V1ObjectFieldSelector,
    V1PodDNSConfig,
    V1ResourceRequirements,
    V1Volume,
)
from pydantic import PositiveInt

from deployment.dict_builders.configs import (
    ContainerConfig,
    Image,
    PodSpecConfig,
    PodTemplateSpecConfig,
    StatefulSetConfig,
    StatefulSetSpecConfig,
)
from deployment.dict_builders.waku import Command, CommandConfig, postgress_container
from deployment.dict_builders.helpers import (
    WAKU_COMMAND_STR,
    find_waku_command,
    find_waku_container_config,
    readiness_probe_health,
    readiness_probe_metrics,
)

# TODO: rename everything apply_ or create_


class WakuNode:
    @staticmethod
    def create_command() -> Command:
        return Command(command=WAKU_COMMAND_STR, multiline=True)

    # @staticmethod
    # def command_config(config : CommandConfig, args):
    #     command = config.find_command(WAKU_COMMAND_STR)
    #     command.args.extend()

    @staticmethod
    def standard_args() -> dict:
        """Standard args for a generic Waku node"""
        return {
            "--cluster-id": 2,
            "--discv5-discovery": True,
            "--discv5-enr-auto-update": True,
            "--log-level": "INFO",
            "--max-connections": 150,
            "--metrics-server-address": "0.0.0.0",
            "--metrics-server": True,
            "--nat": "extip:${IP}",
            "--relay": True,
            "--rest-address": "0.0.0.0",
            "--rest-admin": True,
            "--rest": True,
            "--shard": 0,
        }

    @staticmethod
    def create_command_config() -> CommandConfig:
        return CommandConfig(commands=[WakuNode.create_command()])

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
        config.env.append(
            V1EnvVar(
                name="IP",
                value_from=V1EnvVarSource(
                    field_ref=V1ObjectFieldSelector(field_path="status.podIP")
                ),
            )
        )
        config.with_readines_probe(readiness_probe_metrics())
        config.command_config = WakuNode.create_command_config()
        return config

    @staticmethod
    def create_pod_spec_config() -> PodSpecConfig:
        return PodSpecConfig(
            container_configs=[WakuNode.create_container_config()],
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
        config = PodTemplateSpecConfig(pod_spec_config=WakuNode.create_pod_spec_config())
        config.with_app("zerotenkay")
        return config

    @staticmethod
    def create_stateful_set_spec_config() -> StatefulSetSpecConfig:
        config = StatefulSetSpecConfig(
            replicas=0,
            service_name="zerotesting-service",
            pod_template_spec_config=WakuNode.create_pod_template_spec_config(),
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
            stateful_set_spec=WakuNode.create_stateful_set_spec_config(),
        )


class WakuBootstrapNode:
    @staticmethod
    def command(config: CommandConfig):
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
    def pod_spec(config: PodSpecConfig):
        config.dns_config.searches.append(
            "zerotesting-bootstrap.zerotesting.svc.cluster.local",
        )
        container_config = find_waku_container_config(config.container_configs)
        WakuBootstrapNode.container(container_config)

    @staticmethod
    def stateful_set(config: StatefulSetConfig):
        config.with_app("zerotenkay-bootstrap")
        config.name = "bootstrap"
        config.service_name = "zerotesting-bootstrap"
        WakuBootstrapNode.pod_spec(config.pod_spec_config)

    @staticmethod
    def container(config: ContainerConfig):
        config.with_readines_probe(readiness_probe_health(), overwrite=True)

    @staticmethod
    def pod_spec(config: PodSpecConfig):
        waku_container = find_waku_container_config(config)
        if waku_container is None:
            raise ValueError(
                "The config should already have a waku container before adding bootstrap capability."
            )
        WakuBootstrapNode.container(config)

    @staticmethod
    def create_resources() -> V1ResourceRequirements:
        return V1ResourceRequirements(
            requests={"memory": "64Mi", "cpu": "150m"}, limits={"memory": "600Mi", "cpu": "400m"}
        )


class StoreNodes:

    @staticmethod
    def command(config: CommandConfig):
        command = config.find_command(WAKU_COMMAND_STR)
        command.args.extend(
            [
                ("--store", True),
                ("--store-message-db-url", "${POSTGRES_URL}"),
            ]
        )

    @staticmethod
    def container(config: ContainerConfig):
        config.with_env_var(
            V1EnvVar(
                name="POSTGRES_URL",
                value="postgres://wakuuser:wakupassword@127.0.0.1:5432/wakumessages",
            )
        )
        config.with_resources(WakuNode.create_resources(), overwrite=True)
        StoreNodes.command(config.command_config)

    @staticmethod
    def pod_spec(config: PodSpecConfig):
        config.volumes.append(V1Volume(name="postgres-data", empty_dir={}))
        config.add_container(postgress_container(), order="prepend")
        waku_container = find_waku_container_config(config)
        if waku_container is None:
            raise ValueError(
                "The config should already have a waku container before adding store capability."
            )
        StoreNodes.container(waku_container)

    @staticmethod
    def pod_template_spec(config: PodTemplateSpecConfig):
        config.with_app("zerotenkay-store")
        StoreNodes.pod_spec(config.pod_spec_config)

    @staticmethod
    def stateful_set_spec(config: StatefulSetSpecConfig):
        config.with_app("zerotenkay-store")
        config.service_name = "zerotesting-store"
        StoreNodes.pod_template_spec(config.pod_template_spec_config)

    @staticmethod
    def stateful_set(config: StatefulSetConfig):
        config.name = "store-0"  # TODO: should be store-{shard}
        config.namespace = "zerotesting"  # TODO: don't overwrite if already exists?
        StoreNodes.stateful_set_spec(config.stateful_set_spec)


# --- ENR / addrs presets ----


def getEnrOrAddress_initContainer_dict(
    type_: Literal["enr", "address"],
    num: PositiveInt,
    service_names: List[str],
    *,
    init_container_image,
) -> dict:
    defaults = (
        {
            "shortname": "addrs",
            "version": "v0.1.0",
            "repo": "soutullostatus/getaddress",
        }
        if type_ == "address"
        else {
            "shortname": "enr",
            "version": "v0.5.0",
            "repo": "soutullostatus/getenr",
        }
    )

    image = (
        init_container_image
        if init_container_image is not None
        else f"{defaults['repo']}:{defaults['version']}"
    )
    return {
        "name": f"grab{type_}",
        "image": image,
        "imagePullPolicy": "IfNotPresent",
        "volumeMounts": [
            {
                "name": f"{type_}-data",
                "mountPath": f"/etc/{defaults['shortname']}",
            }
        ],
        "command": [f"/app/get{type_}.sh"],
        "args": [str(num)] + service_names,
    }


class BaseFeature:
    command_arg_key: str  # To be overridden by subclasses, e.g. "--discv5-bootstrap-node"
    volume_name: str  # Example: "enr-data"
    init_container_type: str  # Examples: "enr" or "address"
    env_vars: str  # Examples: "ENR" or "addrs"
    source_file: str  # Examples: "/etc/enr/enr.env", "/etc/addrs/addrs.env"

    @classmethod
    def command_config(cls, config: CommandConfig, num: PositiveInt):
        # TODO: add source ENRs file
        # config.with_source(cls.source_file)

        args = [(cls.command_arg_key, f"${cls.env_vars}{index}") for index in range(1, num + 1)]
        command = find_waku_command(config)
        command.add_args(args)

    @classmethod
    def container(
        cls,
        config: ContainerConfig,
        num: PositiveInt,

    ):
        cls.command_config(config.command_config, num)

    @classmethod
    def pod_spec(
        cls,
        config: PodSpecConfig,
        num: PositiveInt,
        service_names: List[str],
        *,
        init_container_image: Optional[Image] = None,
    ):
        config.volumes.append({"name": cls.volume_name, "emptyDir": {}})
        config.add_init_container(
            getEnrOrAddress_initContainer_dict(
                cls.init_container_type,
                num,
                service_names,
                init_container_image=init_container_image,
            )
        )
        waku_container_config = find_waku_container_config(config)
        cls.container(waku_container_config, num)


class Enr(BaseFeature):
    command_arg_key = "--discv5-bootstrap-node"
    volume_name = "enr-data"
    init_container_type = "enr"
    env_vars = "ENR"
    source_file = "/etc/enr/enr.env"


class Addrs(BaseFeature):
    command_arg_key = "--lightpushnode"
    volume_name = "enr-data"
    init_container_type = "address"
    env_vars = "addrs"
    source_file = "/etc/addrs/addrs.env"
