from typing import List, Literal, Optional, TypeVar

from kubernetes.client import (
    V1ContainerPort,
    V1EnvVar,
    V1Probe,
    V1ResourceRequirements,
    V1VolumeMount,
)
from pydantic import BaseModel, ConfigDict

from builders.configs.command import CommandConfig

T = TypeVar("T")


class Image(BaseModel):
    repo: str
    tag: str

    @staticmethod
    def from_str(image: str):
        repo, tag = image.split(":")
        return Image(repo=repo, tag=tag)

    def __str__(self):
        return f"{self.repo}:{self.tag}"


class ContainerConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    command_config: CommandConfig = CommandConfig()
    readiness_probe: Optional[V1Probe] = None
    # Optional fields default to None to avoid inclusion in the deployment yaml
    # when we pass them to the constructor of Kubernetes objects.
    # These fields are set to `[]` before `.append` is called if needed.
    volume_mounts: Optional[List[V1VolumeMount]] = None
    resources: Optional[V1ResourceRequirements] = None
    env: Optional[List[V1EnvVar]] = None
    name: str
    image: Optional[Image] = None
    ports: Optional[List[V1ContainerPort]] = None
    image_pull_policy: Literal["IfNotPresent", "Always", "Never"]

    def with_resources(self, resources: V1ResourceRequirements, *, overwrite: bool = False):
        if self.resources is not None and not overwrite:
            raise ValueError("Resources already exist for container.")
        self.resources = resources

    def with_volume_mount(self, mount: V1VolumeMount, *, overwrite: bool = False):
        if self.volume_mounts is None:
            self.volume_mounts = []

        if not overwrite and mount.name in [item.name for item in self.volume_mounts]:
            raise ValueError(
                f"Volume mount already exists in {type(self)}. "
                f"volume mount: `{mount}` config: `{self}`"
            )

        self.volume_mounts.append(mount)

    def with_env_var(self, var: V1EnvVar, *, overwrite: bool = False):
        if self.env is None:
            self.env = []
        index = next([index for index, item in enumerate(self.env) if item.name == var.name], None)
        if index:
            if not overwrite:
                raise ValueError(
                    f"Attempt to add duplicate environment variable to {type(self)}. "
                    f"var: `{var}` config: {self}"
                )
            self.env[index] = var
        else:
            self.env.append(var)

    def with_readiness_probe(self, readiness_probe: V1Probe | dict, *, overwrite=False):
        from builders.helpers import dict_to_v1probe

        if self.readiness_probe is not None and not overwrite:
            raise ValueError("ContainerConfig already has readiness probe.")
        if isinstance(readiness_probe, dict):
            readiness_probe = dict_to_v1probe(readiness_probe)
        self.readiness_probe = readiness_probe
