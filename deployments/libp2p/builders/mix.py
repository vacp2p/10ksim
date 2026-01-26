from kubernetes.client import (
    V1EnvVar,
    V1PersistentVolumeClaim,
    V1PersistentVolumeClaimSpec,
    V1PersistentVolumeClaimVolumeSource,
    V1ResourceRequirements,
    V1Volume,
    V1VolumeMount,
    V1ObjectMeta,
)

from core.configs.container import ContainerConfig
from core.configs.pod import PodSpecConfig, PodTemplateSpecConfig
from core.configs.statefulset import StatefulSetConfig, StatefulSetSpecConfig
from libp2p.builders.helpers import find_libp2p_container_config


DEFAULT_PVC_NAME = "mix-shared-pvc"
DEFAULT_MOUNT_PATH = "/shared"
DEFAULT_STORAGE_CLASS = "moosefs-storage"
DEFAULT_STORAGE_SIZE = "1Gi"


def create_mix_pvc(
    name: str = DEFAULT_PVC_NAME,
    namespace: str = "zerotesting-nimlibp2p",
    storage_size: str = DEFAULT_STORAGE_SIZE,
    storage_class: str = DEFAULT_STORAGE_CLASS,
) -> V1PersistentVolumeClaim:
    """
    PersistentVolumeClaim for mix protocol shared storage.
    Needs to be deployed separately before the StatefulSet.
    """
    return V1PersistentVolumeClaim(
        api_version="v1",
        kind="PersistentVolumeClaim",
        metadata=V1ObjectMeta(name=name, namespace=namespace),
        spec=V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteMany"],
            resources=V1ResourceRequirements(requests={"storage": storage_size}),
            storage_class_name=storage_class,
        ),
    )

def create_mix_env_vars(
    num_mix: int = 50,
    mix_d: int = 3,
    uses_mix: bool = True,
    file_path: str = DEFAULT_MOUNT_PATH,
) -> list:
    """Create environment variables for mix protocol."""
    return [
        V1EnvVar(name="MOUNTSMIX", value="1"),
        V1EnvVar(name="USESMIX", value=str(uses_mix).lower()),
        V1EnvVar(name="NUMMIX", value=str(num_mix)),
        V1EnvVar(name="MIXD", value=str(mix_d)),
        V1EnvVar(name="FILEPATH", value=file_path),
    ]

def apply_mix_container_config(
    config: ContainerConfig,
    num_mix: int = 50,
    mix_d: int = 3,
    uses_mix: bool = True,
    pvc_name: str = DEFAULT_PVC_NAME,
    mount_path: str = DEFAULT_MOUNT_PATH,
):
    """Add mix protocol configuration to container."""
    # Update environment defaults
    for env_var in create_mix_env_vars(num_mix, mix_d, uses_mix, mount_path):
        config.with_env_var(env_var, overwrite=True)

    # Add volume mount
    config.with_volume_mount(V1VolumeMount(name="shared-files", mount_path=mount_path))


def apply_mix_pod_spec(
    config: PodSpecConfig,
    num_mix: int = 50,
    mix_d: int = 3,
    uses_mix: bool = True,
    pvc_name: str = DEFAULT_PVC_NAME,
    mount_path: str = DEFAULT_MOUNT_PATH,
):
    config.with_volume(
        V1Volume(
            name="shared-files",
            persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
                claim_name=pvc_name
            ),
        )
    )

    # Configure container
    container = find_libp2p_container_config(config)
    if container is None:
        raise ValueError("libp2p container must exist before adding mix configuration")
    apply_mix_container_config(container, num_mix, mix_d, uses_mix, pvc_name, mount_path)


def apply_mix_pod_template(
    config: PodTemplateSpecConfig,
    num_mix: int = 50,
    mix_d: int = 3,
    uses_mix: bool = True,
    pvc_name: str = DEFAULT_PVC_NAME,
    mount_path: str = DEFAULT_MOUNT_PATH,
):
    apply_mix_pod_spec(config.pod_spec_config, num_mix, mix_d, uses_mix, pvc_name, mount_path)


def apply_mix_statefulset_spec(
    config: StatefulSetSpecConfig,
    num_mix: int = 50,
    mix_d: int = 3,
    uses_mix: bool = True,
    pvc_name: str = DEFAULT_PVC_NAME,
    mount_path: str = DEFAULT_MOUNT_PATH,
):
    apply_mix_pod_template(
        config.pod_template_spec_config, num_mix, mix_d, uses_mix, pvc_name, mount_path
    )

def apply_mix_statefulset(
    config: StatefulSetConfig,
    num_mix: int = 50,
    mix_d: int = 3,
    uses_mix: bool = True,
    pvc_name: str = DEFAULT_PVC_NAME,
    mount_path: str = DEFAULT_MOUNT_PATH,
):
    apply_mix_statefulset_spec(
        config.stateful_set_spec, num_mix, mix_d, uses_mix, pvc_name, mount_path
    )
