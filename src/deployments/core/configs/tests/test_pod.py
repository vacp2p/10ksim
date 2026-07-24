from __future__ import annotations

import pytest
from kubernetes.client import V1PodSecurityContext, V1Volume

from src.deployments.core.configs.container import ContainerConfig, Image
from src.deployments.core.configs.pod import (
    PodConfig,
    PodSpecConfig,
    PodTemplateSpecConfig,
    build_pod,
    build_pod_spec,
    build_pod_template_spec,
)


def test_with_dns_search_reorders_existing_search():
    config = PodSpecConfig(dns_config=None)
    config.with_dns_search("a.example")
    config.with_dns_search("b.example")
    config.with_dns_search("a.example", overwrite=True)
    assert config.dns_config.searches == ["b.example", "a.example"]


def test_with_dns_search_raises_on_duplicate_without_overwrite():
    config = PodSpecConfig(dns_config=None)
    config.with_dns_search("a.example")
    with pytest.raises(ValueError):
        config.with_dns_search("a.example")


def test_remove_dns_search_missing_ok():
    config = PodSpecConfig(dns_config=None)
    config.remove_dns_search("missing", missing_ok=True)
    assert config.dns_config is None


def test_remove_dns_search_raises_when_missing_and_missing_ok_false():
    config = PodSpecConfig(dns_config=None)
    with pytest.raises(ValueError):
        config.remove_dns_search("missing", missing_ok=False)


def test_with_volume_adds_volume():
    config = PodSpecConfig()
    volume = V1Volume(name="data")
    config.with_volume(volume)
    assert config.volumes == [volume]


def test_with_volume_replaces_existing_when_overwrite_true():
    config = PodSpecConfig()
    volume1 = V1Volume(name="data")
    volume2 = V1Volume(name="data", empty_dir={})
    config.with_volume(volume1)
    config.with_volume(volume2, overwrite=True)
    assert config.volumes == [volume2]


def test_with_volume_raises_on_duplicate_without_overwrite():
    config = PodSpecConfig()
    volume = V1Volume(name="data")
    config.with_volume(volume)
    with pytest.raises(ValueError):
        config.with_volume(volume)


def test_add_init_container_adds_container():
    config = PodSpecConfig()
    init_container = ContainerConfig(
        name="init",
        image=Image(repo="busybox", tag="latest"),
        image_pull_policy="IfNotPresent",
    )
    config.add_init_container(init_container)
    assert len(config.init_containers) == 1
    assert config.init_containers[0].name == "init"


def test_add_init_container_raises_on_duplicate_without_overwrite():
    config = PodSpecConfig()
    init_container = ContainerConfig(
        name="init",
        image=Image(repo="busybox", tag="latest"),
        image_pull_policy="IfNotPresent",
    )
    config.add_init_container(init_container)
    with pytest.raises(ValueError):
        config.add_init_container(init_container)


def test_add_container_appends_and_prepends():
    config = PodSpecConfig()
    c1 = ContainerConfig(
        name="c1",
        image=Image(repo="busybox", tag="latest"),
        image_pull_policy="IfNotPresent",
    )
    c2 = ContainerConfig(
        name="c2",
        image=Image(repo="busybox", tag="latest"),
        image_pull_policy="IfNotPresent",
    )
    config.add_container(c1)
    config.add_container(c2, order="prepend")
    assert [c.name for c in config.container_configs] == ["c2", "c1"]


def test_add_container_raises_on_duplicate_without_overwrite():
    config = PodSpecConfig()
    c = ContainerConfig(
        name="c",
        image=Image(repo="busybox", tag="latest"),
        image_pull_policy="IfNotPresent",
    )
    config.add_container(c)
    with pytest.raises(ValueError):
        config.add_container(c)


def test_with_service_account_name_sets_value():
    config = PodSpecConfig()
    config.with_service_account_name("default")
    assert config.service_account_name == "default"


def test_with_security_context_sets_value():
    config = PodSpecConfig()
    context = V1PodSecurityContext(run_as_user=0)
    config.with_security_context(context)
    assert config.security_context == context


def test_build_pod_spec_uses_config_values():
    config = PodSpecConfig()
    config.with_dns_search("a.example")
    spec = build_pod_spec(config)
    assert spec.dns_config.searches == ["a.example"]


def test_build_pod_template_spec_maps_metadata_and_spec():
    pod_spec = PodSpecConfig()
    tmpl = PodTemplateSpecConfig(
        name="n",
        namespace="ns",
        labels={"app": "x"},
        annotations={"a": "b"},
        pod_spec_config=pod_spec,
    )
    result = build_pod_template_spec(tmpl)
    assert result.metadata.name == "n"
    assert result.metadata.namespace == "ns"
    assert result.metadata.labels == {"app": "x"}
    assert result.metadata.annotations == {"a": "b"}


def test_build_pod_maps_config():
    pod_config = PodConfig(name="n", namespace="ns", labels={"app": "x"})
    result = build_pod(pod_config)
    assert result.metadata.name == "n"
    assert result.metadata.namespace == "ns"
    assert result.metadata.labels == {"app": "x"}
