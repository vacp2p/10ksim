import pytest
from kubernetes.client import (
    V1ContainerPort,
    V1EnvVar,
    V1Probe,
    V1ResourceRequirements,
    V1VolumeMount,
)

from src.deployments.core.configs.container import ContainerConfig, Image, build_container


def test_with_image_sets_image():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    img = Image(repo="repo", tag="tag")
    config.with_image(img)
    assert config.image == img


def test_with_image_raises_on_duplicate_without_overwrite():
    config = ContainerConfig(
        name="c",
        image=Image(repo="repo1", tag="tag1"),
        image_pull_policy="Always",
    )
    with pytest.raises(ValueError):
        config.with_image(Image(repo="repo2", tag="tag2"))


def test_with_image_overwrite_replaces_existing_image():
    config = ContainerConfig(
        name="c",
        image=Image(repo="repo1", tag="tag1"),
        image_pull_policy="Always",
    )
    config.with_image(Image(repo="repo2", tag="tag2"), overwrite=True)
    assert config.image == Image(repo="repo2", tag="tag2")


def test_with_port_adds_port():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    port = V1ContainerPort(container_port=8080)
    config.with_port(port)
    assert config.ports == [port]


def test_with_port_replaces_existing_when_overwrite_true():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    port1 = V1ContainerPort(container_port=8080)
    port2 = V1ContainerPort(container_port=8080, name="http")
    config.with_port(port1)
    config.with_port(port2, overwrite=True)
    assert config.ports == [port2]


def test_with_port_raises_on_duplicate_without_overwrite():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    port = V1ContainerPort(container_port=8080)
    config.with_port(port)
    with pytest.raises(ValueError):
        config.with_port(port)


def test_with_resources_sets_resources():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    resources = V1ResourceRequirements(requests={"cpu": "100m"})
    config.with_resources(resources)
    assert config.resources == resources


def test_with_resources_raises_on_duplicate_without_overwrite():
    config = ContainerConfig(
        name="c",
        image_pull_policy="Always",
        resources=V1ResourceRequirements(requests={"cpu": "100m"}),
    )
    with pytest.raises(ValueError):
        config.with_resources(V1ResourceRequirements(requests={"cpu": "200m"}))


def test_with_resources_overwrite_replaces_existing():
    config = ContainerConfig(
        name="c",
        image_pull_policy="Always",
        resources=V1ResourceRequirements(requests={"cpu": "100m"}),
    )
    new_resources = V1ResourceRequirements(requests={"cpu": "200m"})
    config.with_resources(new_resources, overwrite=True)
    assert config.resources == new_resources


def test_with_volume_mount_adds_mount():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    mount = V1VolumeMount(name="data", mount_path="/data")
    config.with_volume_mount(mount)
    assert config.volume_mounts == [mount]


def test_with_volume_mount_replaces_existing_when_overwrite_true():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    mount1 = V1VolumeMount(name="data", mount_path="/data")
    mount2 = V1VolumeMount(name="data", mount_path="/mnt/data")
    config.with_volume_mount(mount1)
    config.with_volume_mount(mount2, overwrite=True)
    assert config.volume_mounts == [mount2]


def test_with_volume_mount_raises_on_duplicate_without_overwrite():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    mount = V1VolumeMount(name="data", mount_path="/data")
    config.with_volume_mount(mount)
    with pytest.raises(ValueError):
        config.with_volume_mount(mount)


def test_with_env_var_adds_new_env():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    env = V1EnvVar(name="A", value="1")
    config.with_env_var(env)
    assert config.env == [env]


def test_env_var_at_index_zero_can_be_overwritten():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    config.with_env_var(V1EnvVar(name="A", value="1"))
    config.with_env_var(V1EnvVar(name="A", value="2"), overwrite=True)
    assert config.env[0].value == "2"


def test_with_env_var_raises_on_duplicate_without_overwrite():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    config.with_env_var(V1EnvVar(name="A", value="1"))
    with pytest.raises(ValueError):
        config.with_env_var(V1EnvVar(name="A", value="2"))


def test_with_readiness_probe_accepts_dict():
    config = ContainerConfig(name="c", image_pull_policy="Always")
    probe_dict = {
        "httpGet": {"path": "/health", "port": 8008},
        "initialDelaySeconds": 1,
    }
    config.with_readiness_probe(probe_dict)
    assert isinstance(config.readiness_probe, V1Probe)


def test_with_readiness_probe_raises_on_duplicate_without_overwrite():
    config = ContainerConfig(
        name="c",
        image_pull_policy="Always",
        readiness_probe=V1Probe(),
    )
    with pytest.raises(ValueError):
        config.with_readiness_probe(V1Probe())


def test_build_container_maps_fields():
    config = ContainerConfig(
        name="c",
        image=Image(repo="repo", tag="tag"),
        image_pull_policy="Always",
    )
    config.with_env_var(V1EnvVar(name="A", value="1"))
    config.with_port(V1ContainerPort(container_port=8080))
    container = build_container(config)
    assert container.name == "c"
    assert container.image == "repo:tag"
    assert container.env[0].name == "A"
    assert container.ports[0].container_port == 8080
