from dataclasses import dataclass
from typing import List, Optional

from kubernetes.client import (
    V1ContainerPort,
    V1EnvVar,
    V1PodDNSConfig,
    V1ResourceRequirements,
)

from core.configs.container import ContainerConfig, Image
from core.configs.pod import PodSpecConfig, PodTemplateSpecConfig
from core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig
from libp2p.builders.helpers import LIBP2P_CONTAINER_NAME


@dataclass
class Libp2pEnvConfig:
    """
    Environment variable configuration for libp2p nodes.    
    All parameters are Optional. Only explicitly set values will be passed.
    """
    peers: Optional[int] = None
    connect_to: Optional[int] = None
    max_connections: Optional[int] = None
    service: Optional[str] = None
    muxer: Optional[str] = None
    fragments: Optional[int] = None
    self_trigger: Optional[bool] = None
    shadow_env: Optional[bool] = None

    # Mix protocol configuration
    mounts_mix: Optional[bool] = None
    uses_mix: Optional[bool] = None
    num_mix: Optional[int] = None
    mix_d: Optional[int] = None
    file_path: Optional[str] = None
    
    def to_env_vars(self) -> List[V1EnvVar]:

        # Convert configuration to list of V1EnvVar.     
        env_vars = []
        
        if self.peers is not None:
            env_vars.append(V1EnvVar(name="PEERS", value=str(self.peers)))
        if self.connect_to is not None:
            env_vars.append(V1EnvVar(name="CONNECTTO", value=str(self.connect_to)))
        if self.muxer is not None:
            env_vars.append(V1EnvVar(name="MUXER", value=self.muxer))
        if self.fragments is not None:
            env_vars.append(V1EnvVar(name="FRAGMENTS", value=str(self.fragments)))
        if self.self_trigger is not None:
            env_vars.append(V1EnvVar(name="SELFTRIGGER", value=str(self.self_trigger).lower()))
        if self.service is not None:
            env_vars.append(V1EnvVar(name="SERVICE", value=self.service))
        if self.max_connections is not None:
            env_vars.append(V1EnvVar(name="MAXCONNECTIONS", value=str(self.max_connections)))
        if self.shadow_env is not None:
            env_vars.append(V1EnvVar(name="SHADOWENV", value=str(self.shadow_env).lower()))
        if self.mounts_mix is not None:
            env_vars.append(V1EnvVar(name="MOUNTSMIX", value="1" if self.mounts_mix else "0"))
        if self.uses_mix is not None:
            env_vars.append(V1EnvVar(name="USESMIX", value=str(self.uses_mix).lower()))
        if self.num_mix is not None:
            env_vars.append(V1EnvVar(name="NUMMIX", value=str(self.num_mix)))
        if self.mix_d is not None:
            env_vars.append(V1EnvVar(name="MIXD", value=str(self.mix_d)))
        if self.file_path is not None:
            env_vars.append(V1EnvVar(name="FILEPATH", value=self.file_path))
        
        return env_vars
    
    def get_service_name(self) -> str:
        """Get service name. use default (nimp2p-service) if not set."""
        return self.service if self.service is not None else "nimp2p-service"


class Nodes:
    """Base configuration for libp2p nodes."""
    # Default values
    DEFAULT_NAMESPACE = "refactortesting-libp2p"
    DEFAULT_SERVICE_NAME = "nimp2p-service"
    DEFAULT_IMAGE = Image(repo="ufarooqstatus/refactored-test-node", tag="v1.0")


    @staticmethod
    def create_container_config(
        env_config: Optional[Libp2pEnvConfig] = None,
    ) -> ContainerConfig:
        """Create base container configuration for libp2p node."""
        if env_config is None:
            env_config = Libp2pEnvConfig()
        
        config = ContainerConfig(
            name=LIBP2P_CONTAINER_NAME,
            image=Nodes.DEFAULT_IMAGE,
            image_pull_policy="IfNotPresent",
        )

        config.ports = [
            V1ContainerPort(container_port=5000),
            V1ContainerPort(container_port=8008),
            V1ContainerPort(container_port=8645),
        ]

        # Environment variables (only those explicitly set)
        for env_var in env_config.to_env_vars():
            config.with_env_var(env_var)

        config.with_resources(Nodes.create_resources())

        return config


    @staticmethod
    def create_resources() -> V1ResourceRequirements:
        return V1ResourceRequirements(
            requests={"memory": "64Mi", "cpu": "150m"},
            limits={"memory": "600Mi", "cpu": "400m"},
        )

    @staticmethod
    def create_pod_spec_config(
        env_config: Optional[Libp2pEnvConfig] = None,
        namespace: Optional[str] = None,
    ) -> PodSpecConfig:
        
        #Create pod spec with DNS configuration
        if env_config is None:
            env_config = Libp2pEnvConfig()
        if namespace is None:
            namespace = Nodes.DEFAULT_NAMESPACE
        
        service_name = env_config.get_service_name()
        service_dns = f"{service_name}.{namespace}.svc.cluster.local"
        
        return PodSpecConfig(
            container_configs=[Nodes.create_container_config(env_config)],
            dns_config=V1PodDNSConfig(searches=[service_dns]),
        )


    @staticmethod
    def create_pod_template_spec_config(
        env_config: Optional[Libp2pEnvConfig] = None,
        namespace: Optional[str] = None,
    ) -> PodTemplateSpecConfig:

        if env_config is None:
            env_config = Libp2pEnvConfig()
        if namespace is None:
            namespace = Nodes.DEFAULT_NAMESPACE
        
        config = PodTemplateSpecConfig(
            pod_spec_config=Nodes.create_pod_spec_config(env_config, namespace)
        )
        config.with_app("zerotenkay")
        return config


    @staticmethod
    def create_stateful_set_spec_config(
        replicas: int = 50,
        env_config: Optional[Libp2pEnvConfig] = None,
        namespace: Optional[str] = None,
    ) -> StatefulSetSpecConfig:

        if env_config is None:
            env_config = Libp2pEnvConfig()
        if namespace is None:
            namespace = Nodes.DEFAULT_NAMESPACE
        
        service_name = env_config.get_service_name()
        
        config = StatefulSetSpecConfig(
            replicas=replicas,
            service_name=service_name,
            pod_template_spec_config=Nodes.create_pod_template_spec_config(
                env_config, namespace
            ),
        )
        config.with_app("zerotenkay")
        return config


    @staticmethod
    def create_statefulset_config(
        name: str = "pod",
        namespace: Optional[str] = None,
        replicas: int = 50,
        env_config: Optional[Libp2pEnvConfig] = None,
    ) -> StatefulSetConfig:
        """Create complete statefulset configuration."""
        if env_config is None:
            env_config = Libp2pEnvConfig()
        if namespace is None:
            namespace = Nodes.DEFAULT_NAMESPACE
        
        return StatefulSetConfig(
            name=name,
            namespace=namespace,
            apiVersion="apps/v1",
            kind="StatefulSet",
            pod_management_policy="Parallel",
            stateful_set_spec=Nodes.create_stateful_set_spec_config(
                replicas, env_config, namespace
            ),
        )
