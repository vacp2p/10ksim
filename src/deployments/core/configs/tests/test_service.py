from __future__ import annotations

import pytest
from kubernetes.client import V1Service, V1ServicePort

from src.deployments.core.builders import ServiceBuilder
from src.deployments.core.configs.service import ServiceConfig, ServiceSpecConfig, build_service


def test_with_selector_adds_selector():
    config = ServiceSpecConfig()
    config.with_selector("app", "demo")
    assert config.selector == {"app": "demo"}


def test_with_port_appends_new_port():
    config = ServiceSpecConfig()
    port = V1ServicePort(port=80, name="http")
    config.with_port(port)
    assert config.ports == [port]


def test_with_port_replaces_existing_when_overwrite_true():
    config = ServiceSpecConfig()
    p1 = V1ServicePort(port=80, name="http")
    p2 = V1ServicePort(port=80, name="http")
    config.with_port(p1)
    config.with_port(p2, overwrite=True)
    assert config.ports == [p2]


def test_with_port_raises_on_duplicate_without_overwrite():
    config = ServiceSpecConfig()
    port = V1ServicePort(port=80, name="http")
    config.with_port(port)
    with pytest.raises(ValueError):
        config.with_port(port)


def test_with_port_uses_service_spec_helper():
    builder = ServiceBuilder()
    port = V1ServicePort(port=80, name="http")
    builder.with_port(port)
    assert builder.config.service_spec.ports == [port]


def test_with_type_sets_service_type():
    builder = ServiceBuilder()
    builder.with_type("NodePort")
    assert builder.config.service_spec.spec_type == "NodePort"


def test_build_returns_service_with_type_and_port():
    config = ServiceConfig(name="svc", namespace="ns")
    config.service_spec.spec_type = "NodePort"
    config.service_spec.with_selector("app", "demo")
    config.service_spec.with_port(V1ServicePort(port=80, name="http"))
    service = build_service(config)
    assert isinstance(service, V1Service)
    assert service.spec.type == "NodePort"
    assert service.spec.selector == {"app": "demo"}
    assert service.spec.ports[0].port == 80


def test_build_service_sets_publish_not_ready_addresses():
    config = ServiceConfig(name="svc", namespace="ns")
    config.service_spec.publish_not_ready_addresses = True
    service = build_service(config)
    assert service.spec.publish_not_ready_addresses is True
