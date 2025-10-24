from types import SimpleNamespace

from deployment.dict_builders.waku import (
    postgress_container,
    preprocess_values,
    volumes,
    waku_container,
    waku_init_containers,
)


def dict_to_namespace(d: dict):
    if isinstance(d, dict):
        return SimpleNamespace(**{key: dict_to_namespace(value) for key, value in d.items()})
    return d


def waku_node(config_dict: dict, preprocess: bool):
    if preprocess:
        config = preprocess_values(config_dict)
    else:
        config = dict_to_namespace(config_dict)

    waku_pod_spec = {
        **(
            {"dnsConfig": vars(config.dnsConfig)}
            if hasattr(config, "dnsConfig") and config.dnsConfig
            else {}
        ),
        "containers": []
        + ([postgress_container()] if getattr(config, "storeNode", False) else [])
        + [waku_container(config)],
    }

    out_deployment_dict = {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {"name": config.name, "namespace": config.namespace},
        "spec": {
            "replicas": config.numNodes,
            "podManagementPolicy": "Parallel",
            "serviceName": config.serviceName,
            "selector": {
                "matchLabels": {
                    "app": config.app,
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": config.app,
                    },
                },
                "spec": waku_pod_spec,
            },
        },
    }

    container_volumes = volumes(config)
    if container_volumes:
        out_deployment_dict["spec"]["template"]["spec"]["volumes"] = container_volumes

    init_containers = waku_init_containers(config)
    if init_containers:
        out_deployment_dict["spec"]["template"]["spec"]["initContainers"] = init_containers

    return out_deployment_dict


def waku_node_old(config_dict: dict, preprocess: bool):
    if preprocess:
        config = preprocess_values(config_dict)
    else:
        config = dict_to_namespace(config_dict)

    waku_pod_spec = {
        **(
            {"dnsConfig": vars(config.dnsConfig)}
            if hasattr(config, "dnsConfig") and config.dnsConfig
            else {}
        ),
        "containers": []
        + ([postgress_container()] if getattr(config, "storeNode", False) else [])
        + [waku_container(config)],
    }

    out_deployment_dict = {
        "apiVersion": "apps/v1",
        "kind": "StatefulSet",
        "metadata": {"name": config.name, "namespace": config.namespace},
        "spec": {
            "replicas": config.numNodes,
            "podManagementPolicy": "Parallel",
            "serviceName": config.serviceName,
            "selector": {
                "matchLabels": {
                    "app": config.app,
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": config.app,
                    },
                },
                "spec": waku_pod_spec,
            },
        },
    }

    container_volumes = volumes(config)
    if container_volumes:
        out_deployment_dict["spec"]["template"]["spec"]["volumes"] = container_volumes

    init_containers = waku_init_containers(config)
    if init_containers:
        out_deployment_dict["spec"]["template"]["spec"]["initContainers"] = init_containers

    return out_deployment_dict

    # def todo_rm_temp(self):
    #     presets = {
    #         "--relay": True,
    #         "--max-connections": 150,
    #         "--rest": True,
    #         "--rest-admin": True,
    #         "--rest-address": "0.0.0.0",
    #         "--discv5-discovery": True,
    #         "--discv5-enr-auto-update": True,
    #         "--log-level": "INFO",
    #         "--metrics-server": True,
    #         "--metrics-server-address": "0.0.0.0",
    #         "--nat": "extip:${IP}",
    #         "--cluster-id": 2,
    #         "--shard": 0,
    #     }
    #     # presets = [(k, v) for k, v in presets.items()]
    #     # for index in range(1, 3):
    #     #     presets.append(("--discv5-bootstrap-node", f"$ENR{index}"))
    #     builder = WakuContainerCommandBuilder()
    #     builder.with_args()

    #     builder = ContainerCommandBuilder()
    #     builder.add_line("/usr/bin/wakunode", presets)

    #     enr_args = [("--discv5-bootstrap-node", f"$ENR{index}") for index in range(1, 3)]
    #     builder.add_line("/usr/bin/wakunode", presets)

    # def with_readiness_probe(kind : Literal["health", "metrics"]):


# class WakuPodTemplateSpecBuilder_2:
#     _store: bool
#     _bootstrap: bool
#     _enr: bool
#     _addrs: bool
#     readiness_probe: Literal["health", "metrics"] | V1Probe
#     args: List[str]

#     # self._spec = V1PodSpec(containers=[])

#     enr: EnrSettings

#     def build(self) -> V1PodSpec:
#         command_builder = WakuContainerCommandBuilder()
#         init_containers = []
#         volumes = []

#         if self._enr:
#             command_builder.with_enr()
#             init_containers.append(
#                 get_enr_init_container(
#                     self.enr.num,
#                     self.enr._service_names,
#                     init_container_image=self.enr.init_container_image,
#                 )
#             )
#             volumes.append(V1Volume(name="enr-data", emptyDir={}))

#         container_builder = ContainerBuilder()
#         if self._bootstrap:
#             container_builder.with_bootstrap_resources()
#         else:
#             container_builder.with_node_resources()

#         if self._store:
#             volumes.append(V1Volume(name="postgres-data", empty_dir={}))
#             container_builder.with_store_env()
#             command_builder.with_args(
#                 [
#                     ("--store", True),
#                     ("--store-message-db-url", "${POSTGRES_URL}"),
#                 ]
#             )

#         if self.readiness_probe in ["health", "metrics"]:
#             container_builder.with_readiness_probe(self.readiness_probe)
#         else:
#             container_builder.with_custom_readiness_probe(self.readiness_probe)

#         command = command_builder.with_args(self.args).build()
#         container_builder.with_command(command)

#         return V1PodSpec(
#             containers=deepcopy(self._containers),
#             init_containers=deepcopy(self._init_containers),
#             volumes=deepcopy(self._volumes),
#         )

#     # def with_resources()

#     def with_container(self, container: V1Container) -> Self:
#         self._containers.append(container)
#         return self

#     def with_store(self) -> Self:
#         self._store = True
#         return self

#     def with_enr(
#         self,
#         num: PositiveInt,
#         service_names: List[str],
#         *,
#         init_container_image: Optional[str] = None,
#     ) -> Self:
#         self._volumes.append({"name": "enr-data", "emptyDir": {}})
#         self._init_containers.append(
#             get_enr_init_container(num, service_names, init_container_image=init_container_image)
#         )
#         enr_args = [("--discv5-bootstrap-node", f"$ENR{index}") for index in range(1, 3)]
#         self._command_builder.with_args(enr_args)

#         return self

#     def with_addr(
#         self,
#         num: PositiveInt,
#         service_names: List[str],
#         *,
#         init_container_image: Optional[str] = None,
#     ) -> Self:
#         self._volumes.append({"name": "address-data", "emptyDir": {}})
#         self._spec.init_containers.append(
#             get_addr_init_container(num, service_names, init_container_image=init_container_image)
#         )
#         self.waku_container_args["--lightpushnode"] = [f"$addrs{i}" for i in range(1, num + 1)]

#         return self
