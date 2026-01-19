from typing import Optional, Self

from kubernetes.client import V1EnvVar, V1PersistentVolumeClaim, V1ResourceRequirements
from pydantic import PositiveInt

from core.builders import StatefulSetBuilder
from core.configs.container import Image
from core.configs.statefulset import StatefulSetConfig
from libp2p.builders import mix as Mix
from libp2p.builders import network_delay as NetworkDelay
from libp2p.builders.helpers import find_libp2p_container_config
from libp2p.builders.nodes import Libp2pEnvConfig, Nodes


class Libp2pStatefulSetBuilder(StatefulSetBuilder):
    """
    Only explicitly set values will be passed to the containers.
    Unset values will use libp2p test node's internal defaults.

    Usage:
        statefulset = (
            Libp2pStatefulSetBuilder(StatefulSetConfig())
            .with_libp2p_config(name="pod", namespace="refactortesting-libp2p", num_nodes=50)
            .with_network_delay(delay_ms=100, jitter_ms=30)
            .build()
        )

        # With mix protocol
        statefulset = (
            Libp2pStatefulSetBuilder(StatefulSetConfig())
            .with_libp2p_config(name="pod", namespace="refactortesting-libp2p", num_nodes=50)
            .with_mix(num_mix=50, mix_d=3)
            .build()
        )
    """

    def build(self):
        if not self.config.name:
            raise ValueError(f"Must configure node first. Config: `{self.config}`")
        return super().build()

    def with_libp2p_config(
        self,
        name: str,
        namespace: str,
        num_nodes: PositiveInt,
        peers: Optional[int] = None,
        connect_to: Optional[int] = None,
        max_connections: Optional[int] = None,
        service: Optional[str] = None,
        muxer: Optional[str] = None,
        fragments: Optional[int] = None,
        self_trigger: Optional[bool] = None,
    ) -> Self:

        env_config = Libp2pEnvConfig(
            peers=peers,
            connect_to=connect_to,
            max_connections=max_connections,
            service=service,
            muxer=muxer,
            fragments=fragments,
            self_trigger=self_trigger,
            # Mix defaults (set using with_mix())
            mounts_mix=None,
            uses_mix=None,
            num_mix=None,
            mix_d=None,
            file_path=None,
        )

        self.config.name = name
        self.config.namespace = namespace
        self.config.apiVersion = "apps/v1"
        self.config.kind = "StatefulSet"
        self.config.pod_management_policy = "Parallel"
        self.config.stateful_set_spec = Nodes.create_stateful_set_spec_config(
            replicas=num_nodes,
            env_config=env_config,
            namespace=namespace,
        )
        return self

    def with_network_delay(
        self,
        delay_ms: int = 100,
        jitter_ms: int = 30,
        distribution: str = "normal",
    ) -> Self:

        NetworkDelay.apply_network_delay_statefulset(
            self.config, delay_ms, jitter_ms, distribution
        )
        return self

    def with_mix(
        self,
        num_mix: int = 50,
        mix_d: int = 3,
        uses_mix: bool = True,
        pvc_name: str = Mix.DEFAULT_PVC_NAME,
        mount_path: str = Mix.DEFAULT_MOUNT_PATH,
    ) -> Self:

        #Mix requires PVC to be deployed separately first. Set using create_mix_pvc()
        Mix.apply_mix_statefulset(
            self.config, num_mix, mix_d, uses_mix, pvc_name, mount_path
        )
        return self

    def with_env_var(self, name: str, value: str, overwrite: bool = False) -> Self:
        """Add or update environment variable in libp2p container."""
        container = find_libp2p_container_config(self.config)
        container.with_env_var(V1EnvVar(name=name, value=value), overwrite=overwrite)
        return self

    def with_image(self, image: Image | str) -> Self:
        """Override the default container image."""
        if isinstance(image, str):
            image = Image.from_str(image)

        container = find_libp2p_container_config(self.config)
        container.image = image
        return self

    def with_resources(
        self,
        memory_request: str = "64Mi",
        memory_limit: str = "600Mi",
        cpu_request: str = "150m",
        cpu_limit: str = "400m",
    ) -> Self:
        """Override resource requirements."""
        container = find_libp2p_container_config(self.config)
        container.with_resources(
            V1ResourceRequirements(
                requests={"memory": memory_request, "cpu": cpu_request},
                limits={"memory": memory_limit, "cpu": cpu_limit},
            ),
            overwrite=True,
        )
        return self

def create_mix_pvc(
    namespace: str = "refactortesting-libp2p",
    name: str = Mix.DEFAULT_PVC_NAME,
    storage_size: str = "1Gi",
    storage_class: str = "moosefs-storage",
) -> V1PersistentVolumeClaim:

    return Mix.create_mix_pvc(name, namespace, storage_size, storage_class)
