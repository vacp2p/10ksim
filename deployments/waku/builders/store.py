from core.configs.command import CommandConfig
from core.configs.container import ContainerConfig
from core.configs.pod import PodSpecConfig, PodTemplateSpecConfig
from core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig
from kubernetes.client import V1EnvVar, V1Volume
from waku.builders.helpers import WAKU_COMMAND_STR, find_waku_container_config
from waku.builders.nodes import Nodes


def apply_command_config(config: CommandConfig):
    command = config.find_command(WAKU_COMMAND_STR)
    command.args.extend(
        [
            ("--store", True),
            ("--store-message-db-url", "${POSTGRES_URL}"),
        ]
    )


def apply_container_config(config: ContainerConfig):
    config.with_env_var(
        V1EnvVar(
            name="POSTGRES_URL",
            value="postgres://wakuuser:wakupassword@127.0.0.1:5432/wakumessages",
        )
    )
    config.with_resources(Nodes.create_resources(), overwrite=True)
    apply_command_config(config.command_config)


def apply_pod_spec_config(config: PodSpecConfig):
    config.with_volume(V1Volume(name="postgres-data", empty_dir={}))
    config.with_dns_service("zerotesting-store.zerotesting.svc.cluster.local")
    config.add_container(postgress_container(), order="prepend")
    waku_container = find_waku_container_config(config)
    if waku_container is None:
        raise ValueError(
            "The config should already have a waku container before adding store capability."
        )
    apply_container_config(waku_container)


def apply_pod_template_spec_config(config: PodTemplateSpecConfig):
    config.with_app("zerotenkay-store")
    apply_pod_spec_config(config.pod_spec_config)


def apply_stateful_set_spec_config(config: StatefulSetSpecConfig):
    config.with_app("zerotenkay-store")
    config.service_name = "zerotesting-store"
    apply_pod_template_spec_config(config.pod_template_spec_config)


def apply_stateful_set_config(config: StatefulSetConfig):
    config.name = "store-0"  # TODO: should be store-{shard}
    config.namespace = "zerotesting"  # TODO: overwrite flag: raise, overwrite, ignore
    apply_stateful_set_spec_config(config.stateful_set_spec)


def postgress_container() -> dict:
    prefix = ["sh", "-c"]
    command = prefix + ["\n".join(["pg_isready -U wakuuser -d wakumessages"]) + "\n"]
    return {
        "name": "postgres",
        "image": "postgres:15.1-alpine",
        "imagePullPolicy": "IfNotPresent",
        "volumeMounts": [
            {
                "name": "postgres-data",
                "mountPath": "/var/lib/postgresql/data",
            }
        ],
        "env": [
            {
                "name": "POSTGRES_DB",
                "value": "wakumessages",
            },
            {"name": "POSTGRES_USER", "value": "wakuuser"},
            {
                "name": "POSTGRES_PASSWORD",
                "value": "wakupassword",
            },
        ],
        "ports": [{"containerPort": 5432}],
        "readinessProbe": {
            "exec": {"command": command},
            "initialDelaySeconds": 5,
            "periodSeconds": 2,
            "timeoutSeconds": 5,
        },
    }
